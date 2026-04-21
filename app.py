from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import requests

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "land_data.db")

# 🔥 你的 Google Drive 檔案 ID
FILE_ID = "1_fgR7PPXrtcaFhe9baK_tdqx7Cp0KtK5"

# ==========================================
# Google Drive 下載（支援大檔）
# ==========================================
def download_db():
    if os.path.exists(DB_PATH):
        return

    print("📥 開始下載 DB...")

    session = requests.Session()
    URL = "https://drive.google.com/uc?export=download"

    response = session.get(URL, params={"id": FILE_ID}, stream=True)

    def get_confirm_token(res):
        for key, value in res.cookies.items():
            if key.startswith('download_warning'):
                return value
        return None

    token = get_confirm_token(response)

    if token:
        response = session.get(URL, params={
            "id": FILE_ID,
            "confirm": token
        }, stream=True)

    with open(DB_PATH, "wb") as f:
        for chunk in response.iter_content(8192):
            if chunk:
                f.write(chunk)

    print("✅ DB 下載完成")

download_db()

# ==========================================
# DB 連線（優化）
# ==========================================
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    # 啟用 WAL 模式，大幅提升併發讀取效能
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def get_json():
    return request.get_json(silent=True) or {}

def success(data):
    # 配合前端期望的扁平化 JSON 結構，不額外包裝 {"data": ...}
    return jsonify(data)

def error(msg, code=400):
    # 配合前端的 if (data.error) 攔截機制
    return jsonify({"error": msg}), code

# ==========================================
# 頁面
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')

# ==========================================
# API 1: 取得段名
# ==========================================
@app.route('/api/get_sections', methods=['POST'])
def get_sections():
    data = get_json()
    city = data.get('city')
    dist = data.get('district')

    if not city or not dist:
        return error("缺少 city 或 district")

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
        conn.close()

# ==========================================
# API 1.5: 子地段
# ==========================================
@app.route('/api/get_subsections', methods=['POST'])
def get_subsections():
    data = get_json()
    city = data.get('city')
    dist = data.get('district')
    sec = data.get('section')

    if not all([city, dist, sec]):
        return error("缺少參數")

    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT sub_section FROM prices
            WHERE city=? AND district=? AND section=?
            AND sub_section IS NOT NULL AND sub_section != ''
            ORDER BY sub_section
        """, (city, dist, sec))

        # 修正變數名稱以符合前端期待的 CamelCase
        sub_sections = [
            row[0] for row in cursor.fetchall()
            if isinstance(row[0], str) and row[0].strip()
        ]

        return success({"subSections": sub_sections})

    except Exception as e:
        return error(str(e), 500)
    finally:
        conn.close()

# ==========================================
# API 2: 查地價
# ==========================================
@app.route('/api/get_calc_data', methods=['POST'])
def get_calc_data():
    data = get_json()

    city = data.get('city')
    dist = data.get('district')
    section = data.get('section')
    # 修正空值邏輯：如果前端傳來 ""，就保持 ""，不要轉成 None
    sub_section = data.get('subSection', '').strip() 
    land_number = data.get('landNumber')

    if not all([city, dist, section, land_number]):
        return error("缺少必要查詢參數")

    clean_land = str(land_number).replace('-', '').replace(' ', '')

    if not clean_land.isdigit() or len(clean_land) != 8:
        return error("地號格式錯誤 (必須為8碼數字)")

    q_main = clean_land[:4]
    q_sub = clean_land[4:]

    try:
        conn = get_conn()
        cursor = conn.cursor()

        # 修正 SQL：直接精準比對 sub_section (包含空字串的情況)
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
        
        # 修正變數名稱以符合前端期待的 CamelCase
        years_data = [
            {"year": int(r[0]), "price": float(r[1] or 0)}
            for r in rows
        ]

        return success({
            "yearsData": years_data,
            "area": area
        })

    except Exception as e:
        return error(str(e), 500)
    finally:
        conn.close()

# ==========================================
# 健康檢查
# ==========================================
@app.route('/health')
def health():
    return {"status": "ok"}

# ==========================================
# 啟動
# ==========================================
if __name__ == '__main__':
    # 關閉 reloader 避免在雲端重複觸發 Google Drive 下載
    app.run(debug=True, use_reloader=False)
