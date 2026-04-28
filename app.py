from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 💡 直接指向你專案資料夾內的 DB 檔
DB_PATH = os.path.join(BASE_DIR, "land_data.db")

# ==========================================
# 資料庫連線工具
# ==========================================
def get_conn():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError("找不到 land_data.db 檔案，請確認已上傳至專案根目錄！")
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")  # 啟用 WAL 加速讀取
    return conn

def get_json():
    return request.get_json(silent=True) or {}

# ==========================================
# 頁面與 API 路由
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/get_sections', methods=['POST'])
def get_sections():
    data = get_json()
    city, dist = data.get('city'), data.get('district')
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT section FROM prices WHERE city=? AND district=? AND section IS NOT NULL AND section!='' ORDER BY section", (city, dist))
        return jsonify({"sections": [r[0] for r in cursor.fetchall()]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/get_subsections', methods=['POST'])
def get_subsections():
    data = get_json()
    city, dist, sec = data.get('city'), data.get('district'), data.get('section')
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        
        # 💡 防呆：檢查資料庫到底有沒有 sub_section 欄位
        cursor.execute("PRAGMA table_info(prices)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'sub_section' not in columns:
            return jsonify({"subSections": []}) # 沒有這欄位就直接回傳空陣列

        cursor.execute("SELECT DISTINCT sub_section FROM prices WHERE city=? AND district=? AND section=? AND sub_section IS NOT NULL AND sub_section!='' ORDER BY sub_section", (city, dist, sec))
        return jsonify({"subSections": [r[0] for r in cursor.fetchall()]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/get_calc_data', methods=['POST'])
def get_calc_data():
    data = get_json()
    city, dist, sec = data.get('city'), data.get('district'), data.get('section')
    sub_sec = data.get('subSection', '').strip()
    land_num = data.get('landNumber', '').replace('-', '')
    
    if len(land_num) != 8: return jsonify({"error": "地號需為 8 碼數字"}), 400
    q_m, q_s = land_num[:4], land_num[4:]
    qm_i, qs_i = str(int(q_m)), str(int(q_s))

    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()

        # 💡 防呆：自動偵測你的 DB 裡有哪些欄位
        cursor.execute("PRAGMA table_info(prices)")
        columns = [info[1] for info in cursor.fetchall()]
        has_area = 'area' in columns
        has_sub = 'sub_section' in columns

        # 動態組合 SQL 語法，避免 "no such column" 錯誤
        select_cols = "year, price, area" if has_area else "year, price, 0 as area"
        
        if has_sub:
            sub_sql = "AND (sub_section=? OR (sub_section IS NULL AND ?=''))"
            sub_params = [sub_sec, sub_sec]
        else:
            sub_sql = ""
            sub_params = []

        query = f"""
            SELECT {select_cols} FROM prices 
            WHERE city=? AND district=? AND section=? {sub_sql}
            AND (land_main IN (?,?) OR land_main IS NULL) 
            AND (land_sub IN (?,?) OR land_sub IS NULL)
            ORDER BY year DESC
        """
        
        params = [city, dist, sec] + sub_params + [q_m, qm_i, q_s, qs_i]
        cursor.execute(query, params)
        
        rows = cursor.fetchall()
        if not rows: return jsonify({"yearsData": [], "area": 0})
        
        return jsonify({
            "yearsData": [{"year": int(r[0]), "price": float(r[1] or 0)} for r in rows],
            "area": rows[0][2] if len(rows[0]) > 2 else 0
        })
    except Exception as e:
        print(f"查詢錯誤: {e}")
        return jsonify({"error": f"資料庫錯誤: {str(e)}"}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
