from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import zipfile
import glob
import shutil

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ZIP_PATH = os.path.join(BASE_DIR, "land_data.zip")
DB_PATH = os.path.join(BASE_DIR, "land_data.db")
TEMP_FOLDER = os.path.join(BASE_DIR, "zip_extracted_temp")

# ==========================================
# 自動解壓縮並取出 DB 引擎
# ==========================================
def setup_database_from_zip():
    # 如果已經拿出來過了，就不用再解壓縮，秒速開機！
    if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0:
        print("✅ 資料庫已就緒，跳過解壓縮。")
        return

    if not os.path.exists(ZIP_PATH):
        print(f"⚠️ 找不到壓縮檔: {ZIP_PATH}，請確認檔案已上傳。")
        return

    if os.path.exists(TEMP_FOLDER): shutil.rmtree(TEMP_FOLDER)
    os.makedirs(TEMP_FOLDER)

    try:
        print(f"📦 開始解壓縮 {ZIP_PATH} ...")
        with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
            zip_ref.extractall(TEMP_FOLDER)

        # 🔍 在解壓縮出來的資料夾裡尋找 .db 結尾的檔案
        db_files = glob.glob(os.path.join(TEMP_FOLDER, "**", "*.db"), recursive=True)
        
        if not db_files:
            print("❌ 警告：在 ZIP 壓縮檔內找不到任何 .db 檔案！")
            return

        # 把找到的第一個 db 檔案，移動到根目錄並改名為 land_data.db
        shutil.move(db_files[0], DB_PATH)
        print("🚀 成功從 ZIP 中取出資料庫！")

    except Exception as e:
        print(f"💥 解壓縮過程發生錯誤: {e}")
    finally:
        # 清理暫存資料夾
        if os.path.exists(TEMP_FOLDER):
            shutil.rmtree(TEMP_FOLDER)

# 伺服器啟動時自動執行
setup_database_from_zip()

# ==========================================
# 資料庫連線工具
# ==========================================
def get_conn():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError("資料庫檔案未就緒！")
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")  # 啟用 WAL 加速讀取
    return conn

def get_json():
    return request.get_json(silent=True) or {}

# ==========================================
# 頁面與 API 路由 (內建動態欄位防呆)
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
        
        # 防呆：檢查資料庫到底有沒有 sub_section 欄位
        cursor.execute("PRAGMA table_info(prices)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'sub_section' not in columns:
            return jsonify({"subSections": []})

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

        # 防呆：自動偵測 DB 裡有哪些欄位
        cursor.execute("PRAGMA table_info(prices)")
        columns = [info[1] for info in cursor.fetchall()]
        has_area = 'area' in columns
        has_sub = 'sub_section' in columns

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
        return jsonify({"error": f"資料庫查詢錯誤: {str(e)}"}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
