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
    """從 Google Drive 下載資料夾內所有 CSV 並清洗、轉換為 SQLite"""
    # 建立或清空暫存區
    if os.path.exists(TEMP_FOLDER): shutil.rmtree(TEMP_FOLDER)
    os.makedirs(TEMP_FOLDER)

    try:
        print(f"📂 同步雲端資料夾: {FOLDER_ID}")
        # 下載整個資料夾
        gdown.download_folder(id=FOLDER_ID, output=TEMP_FOLDER, quiet=False, use_cookies=False)
        
        csv_files = glob.glob(os.path.join(TEMP_FOLDER, "**", "*.csv"), recursive=True)
        if not csv_files:
            print("⚠️ 警告：資料夾內查無 CSV 檔案")
            return

        df_list = []
        for file in csv_files:
            try:
                # 讀取 CSV 並執行「淨水器」清洗
                df = pd.read_csv(file, dtype=str)
                df.columns = df.columns.str.strip() # 清除標題空白
                df = df.map(lambda x: x.strip() if isinstance(x, str) else x) # 清除內容空白
                df_list.append(df)
                print(f"✅ 已讀取並清洗: {os.path.basename(file)}")
            except Exception as e:
                print(f"❌ 讀取失敗 {file}: {e}")

        if df_list:
            combined_df = pd.concat(df_list, ignore_index=True)
            
            # 💡 欄位補正：若缺少 area 欄位則自動補 0
            if 'area' not in combined_df.columns:
                combined_df['area'] = 0
            
            # 💡 欄位補正：若缺少 sub_section 欄位則自動補空字串
            if 'sub_section' not in combined_df.columns:
                combined_df['sub_section'] = ''

            combined_df.fillna('', inplace=True)
            
            # 轉換為 SQLite 儲存
            conn = sqlite3.connect(DB_PATH)
            combined_df.to_sql('prices', conn, if_exists='replace', index=False)
            conn.close()
            print("🚀 資料庫轉換完成，WAL 模式啟動。")
        
        shutil.rmtree(TEMP_FOLDER)
    except Exception as e:
        print(f"💥 啟動同步失敗: {e}")

# 伺服器啟動時同步
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
        # 修正欄位名稱與查詢邏輯
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
    
    if len(land_num) != 8: return jsonify({"error": "地號需為 8 碼數字"}), 400
    q_m, q_s = land_num[:4], land_num[4:]
    qm_i, qs_i = str(int(q_m)), str(int(q_s))

    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        # 同時比對補零與不補零的地號格式
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
