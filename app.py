from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import zipfile

app = Flask(__name__)
# 允許跨網域請求，確保 API 連線順暢
CORS(app)  

# 設定路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "land_data.db")
ZIP_PATH = os.path.join(BASE_DIR, "land_data.zip")

# ==========================================
# 🚀 雲端自動解壓縮機制
# ==========================================
def auto_unzip_db():
    if not os.path.exists(DB_PATH) and os.path.exists(ZIP_PATH):
        print("📦 發現壓縮的資料庫，正在自動解壓縮...")
        try:
            with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
                zip_ref.extractall(BASE_DIR)
            print("✅ 解壓縮完成！")
        except Exception as e:
            print(f"❌ 解壓縮失敗: {e}")

# 在 Flask 啟動前，強制執行一次檢查
auto_unzip_db()

# ==========================================
# 網頁路由 (首頁)
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')

# ==========================================
# API 1: 動態取得地段選單
# ==========================================
@app.route('/api/get_sections', methods=['POST'])
def get_sections():
    data = request.json
    city = data.get('city')
    dist = data.get('district')

    if not os.path.exists(DB_PATH):
        return jsonify({"sections": []})

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # 撈出該區不重複的地段名稱，並排序
        cursor.execute("""
            SELECT DISTINCT section FROM prices 
            WHERE city=? AND district=? AND section != '' AND section IS NOT NULL
            ORDER BY section
        """, (city, dist))
        
        sections = [row[0] for row in cursor.fetchall()]
        conn.close()
        return jsonify({"sections": sections})
    except Exception as e:
        print("獲取地段失敗:", e)
        return jsonify({"error": "資料庫讀取異常"}), 500

# ==========================================
# API 2: 取得該地號「所有歷年」地價
# ==========================================
@app.route('/api/get_calc_data', methods=['POST'])
def get_calc_data():
    data = request.json
    city = data.get('city')
    dist = data.get('district')
    section = data.get('section')
    land_number = data.get('landNumber') # 組合好的 8 碼

    # 基礎參數防呆
    if not all([city, dist, section, land_number]):
        return jsonify({"error": "缺少必要查詢參數"}), 400

    if not os.path.exists(DB_PATH):
        return jsonify({"error": "伺服器找不到資料庫檔案 (land_data.db)"}), 500

    try:
        # 切割地號 (前4母號，後4子號)
        clean_land = str(land_number).replace('-', '').replace(' ', '').zfill(8)
        q_main = clean_land[:4]
        q_sub = clean_land[4:]

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 核心優化：不再篩選年份，直接把這塊地「所有」的地價撈出來，照年份排好
        cursor.execute("""
            SELECT year, price FROM prices 
            WHERE city=? AND district=? AND section=? AND land_main=? AND land_sub=?
            ORDER BY year DESC
        """, (city, dist, section, q_main, q_sub))
        
        rows = cursor.fetchall()
        conn.close()

        # 整理成前端要的 JSON 格式
        years_data = []
        for row in rows:
            years_data.append({
                "year": int(row[0]),
                "price": float(row[1]) if row[1] else 0
            })

        return jsonify({"yearsData": years_data})

    except Exception as e:
        print("查詢地價失敗:", e)
        return jsonify({"error": f"資料庫查詢錯誤: {str(e)}"}), 500

# ==========================================
# 啟動伺服器
# ==========================================
if __name__ == '__main__':
    # 關閉 reloader 避免在雲端重複執行解壓縮
    app.run(debug=True, use_reloader=False)
