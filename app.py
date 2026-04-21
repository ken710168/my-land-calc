from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import gdown

app = Flask(__name__)
# 允許跨網域請求
CORS(app)

# 設定絕對路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "land_data.db")

# 🔥 你的 Google Drive 檔案 ID
FILE_ID = "1_fgR7PPXrtcaFhe9baK_tdqx7Cp0KtK5"

# ==========================================
# Google Drive 終極保證下載機制 (使用 gdown)
# ==========================================
def download_db():
    # 檢查檔案是否存在且大於 500KB，避免抓到 Google 的 HTML 警告網頁
    if os.path.exists(DB_PATH):
        if os.path.getsize(DB_PATH) > 500000: 
            return
        else:
            print("🗑️ 發現容量異常的假檔案，強制刪除重載...")
            os.remove(DB_PATH)

    print("📥 使用 gdown 開始下載真實 DB 檔...")
    url = f'https://drive.google.com/uc?id={FILE_ID}'
    
    try:
        gdown.download(url, DB_PATH, quiet=False, fuzzy=True)
        print("✅ DB 真實原始檔下載完成！")
    except Exception as e:
        print(f"❌ gdown 下載失敗: {e}")

download_db()

# ==========================================
# DB 連線（啟用 WAL 高效能模式）
# ==========================================
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception as e:
        print("❌ 資料庫格式錯誤，請確認檔案是否正確。")
        raise e
    return conn

def get_json():
    return request.get_json(silent=True) or {}

def success(data):
    return jsonify(data)

def error(msg, code=400):
    return jsonify({"error": msg}), code

# ==========================================
# 網頁路由 (首頁)
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')

# ==========================================
# API 1: 取得段名 (母地段)
# ==========================================
@app.route('/api/get_sections', methods=['POST'])
def get_sections():
    data = get_json()
    city = data.get('city')
    dist = data.get('district')

    if not city or not dist:
        return error("缺少 city 或 district")

    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT section FROM prices
            WHERE city=? AND district=?
            AND section IS NOT NULL AND section != ''
            ORDER BY section
        """, (city, dist))

        sections = [row[0] for row in cursor.fetchall()]
        return success({"sections": sections})

    except Exception as e:
        return error(str(e), 500)
    finally:
        if conn:
            conn.close()

# ==========================================
# API 1.5: 取得小段名 (子地段)
# ==========================================
@app.route('/api/get_subsections', methods=['POST'])
def get_subsections():
    data = get_json()
    city = data.get('city')
    dist = data.get('district')
    sec = data.get('section')

    if not all([city, dist, sec]):
        return error("缺少參數")

    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT sub_section FROM prices
            WHERE city=? AND district=? AND section=?
            AND sub_section IS NOT NULL AND sub_section != ''
            ORDER BY sub_section
        """, (city, dist, sec))

        sub_sections = [
            row[0] for row in cursor.fetchall()
            if isinstance(row[0], str) and row[0].strip()
        ]
        return success({"subSections": sub_sections})

    except Exception as e:
        return error(str(e), 500)
    finally:
        if conn:
            conn.close()

# ==========================================
# API 2: 取得地價與面積
# ==========================================
@app.route('/api/get_calc_data', methods=['POST'])
def get_calc_data():
    data = get_json()

    city = data.get('city')
    dist = data.get('district')
    section = data.get('section')
    sub_section = data.get('subSection', '').strip() 
    land_number = data.get('landNumber')

    if not all([city, dist, section, land_number]):
        return error("缺少必要查詢參數")

    clean_land = str(land_number).replace('-', '').replace(' ', '')
    if not clean_land.isdigit() or len(clean_land) != 8:
        return error("地號格式錯誤 (必須為8碼數字)")

    q_main = clean_land[:4]
    q_sub = clean_land[4:]

    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT year, price, area FROM prices
            WHERE city=? AND district=? AND section=? AND sub_section=?
            AND land_main=? AND land_sub=?
            ORDER BY year DESC
        """, (city, dist, section, sub_section, q_main, q_sub))

        rows = cursor.fetchall()

        if not rows:
            return success({"yearsData": [], "area": 0})

        area = rows[0][2] if len(rows[0]) > 2 else 0
        years_data = [{"year": int(r[0]), "price": float(r[1] or 0)} for r in rows]

        return success({
            "yearsData": years_data,
            "area": area
        })

    except Exception as e:
        return error(str(e), 500)
    finally:
        if conn:
            conn.close()

# ==========================================
# 健康檢查
# ==========================================
@app.route('/health')
def health():
    return {"status": "ok"}

if __name__ == '__main__':
    # 關閉 reloader 避免重複下載
    app.run(debug=True, use_reloader=False)
