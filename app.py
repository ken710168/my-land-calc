from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import gdown
import pandas as pd
import glob
import shutil

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "land_data.db")
TEMP_FOLDER = os.path.join(BASE_DIR, "drive_data_temp")

# 🔥 Google Drive 資料夾 ID
FOLDER_ID = "1PnX-VjKsMGwWWLpcSLfQEd30FJ2f5Ln2"

def setup_database_from_drive():
    """從 Google Drive 下載 CSV 並轉換為高效能 SQLite 資料庫"""
    if os.path.exists(TEMP_FOLDER): shutil.rmtree(TEMP_FOLDER)
    os.makedirs(TEMP_FOLDER)

    try:
        # 下載資料夾
        gdown.download_folder(id=FOLDER_ID, output=TEMP_FOLDER, quiet=False, use_cookies=False)
        csv_files = glob.glob(os.path.join(TEMP_FOLDER, "**", "*.csv"), recursive=True)
        
        if not csv_files: return

        df_list = []
        for file in csv_files:
            try:
                # 讀取並清洗欄位
                df = pd.read_csv(file, dtype=str)
                df.columns = df.columns.str.strip() # 清除標題空白
                df = df.map(lambda x: x.strip() if isinstance(x, str) else x) # 清除資料空白
                df_list.append(df)
            except Exception as e:
                print(f"跳過錯誤檔案 {file}: {e}")

        if df_list:
            combined_df = pd.concat(df_list, ignore_index=True)
            combined_df.fillna('', inplace=True)
            
            # 轉換為 SQLite
            conn = sqlite3.connect(DB_PATH)
            combined_df.to_sql('prices', conn, if_exists='replace', index=False)
            conn.close()
        
        shutil.rmtree(TEMP_FOLDER)
    except Exception as e:
        print(f"資料庫建立失敗: {e}")

# 啟動時同步
setup_database_from_drive()

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/get_sections', methods=['POST'])
def get_sections():
    data = request.get_json() or {}
    city, dist = data.get('city'), data.get('district')
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT section FROM prices WHERE city=? AND district=? AND section!='' ORDER BY section", (city, dist))
        return jsonify({"sections": [r[0] for r in cursor.fetchall()]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/get_subsections', methods=['POST'])
def get_subsections():
    data = request.get_json() or {}
    city, dist, sec = data.get('city'), data.get('district'), data.get('section')
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT sub_section FROM prices WHERE city=? AND district=? AND section=? AND sub_section!='' ORDER BY sub_section", (city, dist, sec))
        return jsonify({"subSections": [r[0] for r in cursor.fetchall()]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/get_calc_data', methods=['POST'])
def get_calc_data():
    data = request.get_json() or {}
    city, dist, sec = data.get('city'), data.get('district'), data.get('section')
    sub_sec = data.get('subSection', '').strip()
    land_num = data.get('landNumber', '').replace('-', '')
    
    if len(land_num) != 8: return jsonify({"error": "地號需為8碼"}), 400
    q_m, q_s = land_num[:4], land_num[4:]
    qm_i, qs_i = str(int(q_m)), str(int(q_s))

    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        # SQL 防呆：處理 sub_section 為空字串或 NULL 的情況
        cursor.execute("""
            SELECT year, price, area FROM prices 
            WHERE city=? AND district=? AND section=? AND (sub_section=? OR (sub_section='' AND ?=''))
            AND (land_main IN (?,?)) AND (land_sub IN (?,?))
            ORDER BY year DESC
        """, (city, dist, sec, sub_sec, sub_sec, q_m, qm_i, q_s, qs_i))
        rows = cursor.fetchall()
        if not rows: return jsonify({"yearsData": [], "area": 0})
        return jsonify({
            "yearsData": [{"year": int(r[0]), "price": float(r[1] or 0)} for r in rows],
            "area": rows[0][2] if len(rows[0]) > 2 else 0
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
