from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Product(BaseModel):
    sku: str
    product_name: str
    unit_price: float
    quantity_in_stock: int
    min_threshold: int # Added structure requirement

class Deduction(BaseModel):
    quantity: int

@app.get("/products")
def get_products():
    conn = sqlite3.connect("inventory.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/products")
def add_product(product: Product):
    conn = sqlite3.connect("inventory.db")
    cursor = conn.cursor()
    try:
        # Added min_threshold mapping to the database execution step
        cursor.execute(
            "INSERT INTO products (sku, product_name, unit_price, quantity_in_stock, min_threshold) VALUES (?, ?, ?, ?, ?)",
            (product.sku, product.product_name, product.unit_price, product.quantity_in_stock, product.min_threshold)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="SKU already exists")
    conn.close()
    return {"message": "Product added successfully"}

@app.post("/products/{sku}/deduct")
def deduct_product(sku: str, deduction: Deduction):
    conn = sqlite3.connect("inventory.db")
    cursor = conn.cursor()
    cursor.execute("SELECT product_name, quantity_in_stock FROM products WHERE sku = ?", (sku,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found")
        
    p_name, current_stock = row
    if current_stock < deduction.quantity:
        conn.close()
        raise HTTPException(status_code=400, detail="Not enough stock available")
    
    cursor.execute("UPDATE products SET quantity_in_stock = quantity_in_stock - ? WHERE sku = ?", (deduction.quantity, sku))
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO sales_log (sku, quantity_sold, sale_date) VALUES (?, ?, ?)", (sku, deduction.quantity, now_str))
    conn.commit()
    conn.close()
    return {"message": "Stock deducted successfully"}

@app.post("/products/{sku}/add")
def add_stock(sku: str, deduction: Deduction):
    conn = sqlite3.connect("inventory.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET quantity_in_stock = quantity_in_stock + ? WHERE sku = ?", (deduction.quantity, sku))
    conn.commit()
    conn.close()
    return {"message": "Stock restocked successfully"}

@app.get("/sales-summary")
def get_sales_summary(range: str = Query("all")):
    conn = sqlite3.connect("inventory.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    query = "SELECT p.product_name, SUM(s.quantity_sold) as total_sold FROM sales_log s JOIN products p ON s.sku = p.sku"
    if range == "today":
        today_start = datetime.now().strftime("%Y-%m-%d 00:00:00")
        query += f" WHERE s.sale_date >= '{today_start}'"
    query += " GROUP BY p.sku"
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# NEW FEATURE 2 ROUTE: Mathematical 80/20 Analyzer Engine
@app.get("/analytics/pareto")
def get_pareto_analysis():
    conn = sqlite3.connect("inventory.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT product_name, unit_price, quantity_in_stock FROM products")
    rows = cursor.fetchall()
    products = [dict(row) for row in rows]
    conn.close()
    
    if not products:
        return {"message": "Add items to generate analysis charts.", "vip_products": []}
        
    # Calculate stock value for each item
    total_inventory_value = 0
    for p in products:
        p["item_total_value"] = p["unit_price"] * p["quantity_in_stock"]
        total_inventory_value += p["item_total_value"]
        
    if total_inventory_value == 0:
        return {"message": "All stock amounts are currently at 0.", "vip_products": []}
        
    # Sort items from richest valuation down to lowest
    products.sort(key=lambda x: x["item_total_value"], reverse=True)
    
    running_sum = 0
    vip_products = []
    unique_count = len(products)
    
    for index, p in enumerate(products):
        running_sum += p["item_total_value"]
        cumulative_percentage = (running_sum / total_inventory_value) * 100
        item_rank_percentage = ((index + 1) / unique_count) * 100
        
        # Group items making up the top revenue brackets
        if cumulative_percentage <= 81 or len(vip_products) == 0:
            vip_products.append(p["product_name"])
            
    # Calculate the dynamic percentages for display text
    vip_item_ratio = round((len(vip_products) / unique_count) * 100)
    vip_revenue_ratio = round((running_sum / total_inventory_value) * 100) if len(vip_products) == unique_count else 80
    
    return {
        "item_ratio": vip_item_ratio,
        "revenue_ratio": vip_revenue_ratio,
        "vip_list": vip_products,
        "summary": f"Your data shows that {vip_item_ratio}% of your unique products ({', '.join(vip_products)}) account for roughly {vip_revenue_ratio}% of your total asset valuation value!"
    }

@app.delete("/products/{sku}")
def delete_product(sku: str):
    conn = sqlite3.connect("inventory.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE sku = ?", (sku,))
    conn.commit()
    conn.close()
    return {"message": "Product deleted successfully"}