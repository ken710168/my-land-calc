from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import os
import re
import zipfile  # 👉 新增了這個內建的解壓縮工具

app = Flask(__name__)
CORS(app)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "land_data.db")
ZIP_PATH = os.path.join(BASE_DIR, "land_data.zip")

# ==========================================
# 🚀 雲端自動解壓縮機制
# ==========================================
def auto_unzip_db():
    # 如果資料庫不存在，但是發現了 ZIP 檔，就自動解壓縮！
    if not os.path.exists(DB_PATH) and os.path.exists(ZIP_PATH):
        print("📦 發現壓縮的資料庫，正在自動解壓縮...")
        with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
            # 將檔案解壓縮到當前目錄
            zip_ref.extractall(BASE_DIR)
        print("✅ 解壓縮完成！準備啟動伺服器。")

# 在 Flask 啟動前，強制執行一次檢查
auto_unzip_db()

# ==========================================
# 工具：解析使用者輸入的段名與小段
# ==========================================
def parse_segment(text):
    text = str(text).strip()
    if not text:
        return "", ""

    sec_name = ""
    subsec_name = ""
    text = re.sub(r'^[A-Za-z0-9_-]+', '', text).strip()

    if '段' in text:
        parts = text.split('段', 1)
        sec_name = parts[0] + '段'
        subsec_name = parts[1].strip()
    else:
        sec_name = text

    if subsec_name:
        subsec_name = re.sub(r'^[A-Za-z0-9_-]+', '', subsec_name).strip()
        if subsec_name and not subsec_name.endswith('小段'):
            if subsec_name.endswith('小'): subsec_name += '段'
            elif subsec_name != "": subsec_name += '小段'

    return sec_name, subsec_name

def parse_roc_date(date_str):
    year = int(date_str[:-4]) + 1911
    month = int(date_str[-4:-2])
    day = int(date_str[-2:])
    return datetime(year, month, day)

# ==========================================
# 資料庫查詢邏輯
# ==========================================
def query_price(city, dist, raw_section_input, raw_land_input, year):
    if not os.path.exists(DB_PATH):
        print("⚠️ 找不到資料庫！")
        return ""

    q_sec, q_subsec = parse_segment(raw_section_input)

    clean_land = str(raw_land_input).replace('-', '').replace(' ', '').zfill(8)
    q_main = clean_land[:4]
    q_sub = clean_land[4:]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT price FROM prices 
        WHERE city=? AND district=? AND section=? AND sub_section=? AND land_main=? AND land_sub=? AND year=?
    """, (city, dist, q_sec, q_subsec, q_main, q_sub, str(year)))
    
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result else ""

# ==========================================
# 網頁路由
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')

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
    
    years_data = []
    for y in range(start_year_roc, end_year_roc + 1):
        if y % 2 != 0:
            price = query_price(
                data['city'], 
                data['district'], 
                data['section'], 
                data['landNumber'], 
                y
            )
            years_data.append({"year": y, "price": price})
            
    return jsonify({"yearsData": years_data})

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
