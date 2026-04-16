# -*- coding: utf-8 -*-
"""
Created on Thu Apr 16 19:44:54 2026

@author: fkk
"""

from flask import Flask, render_template, request, jsonify
from datetime import datetime, timedelta
import sqlite3
import os

app = Flask(__name__)

# 確保在 Render 雲端環境也能正確找到資料庫路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "land_data.db")

def parse_roc_date(date_str):
    year = int(date_str[:-4]) + 1911
    month = int(date_str[-4:-2])
    day = int(date_str[-2:])
    return datetime(year, month, day)

def query_price(city, dist, section, land_num, year):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT price FROM prices 
        WHERE city=? AND district=? AND section=? AND land_number=? AND year=?
    """, (city, dist, section, land_num, year))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "" # 查不到就回傳空白，讓使用者手動填

# 1. 負責把網頁呈現給使用者
@app.route('/')
def index():
    return render_template('index.html')

# 2. 負責接收前端資料並回傳地價
@app.route('/api/get_calc_data', methods=['POST'])
def get_calc_data():
    data = request.json
    end_str = data.get('endDate')
    start_str = data.get('startDate')

    if not end_str:
        return jsonify({"error": "請輸入迄日"}), 400

    end_date = parse_roc_date(end_str)
    start_date = parse_roc_date(start_str) if start_str else (end_date - timedelta(days=5*365))

    start_year_roc = start_date.year - 1911
    end_year_roc = end_date.year - 1911
    
    # 找出奇數年並去資料庫查價錢
    years_data = []
    for y in range(start_year_roc, end_year_roc + 1):
        if y % 2 != 0:
            price = query_price(data['city'], data['district'], data['section'], data['landNumber'], y)
            years_data.append({"year": y, "price": price})
            
    return jsonify({"yearsData": years_data})

if __name__ == '__main__':
    app.run(debug=True)