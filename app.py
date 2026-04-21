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

# 🔥 你的 Google Drive 資料夾 ID
FOLDER_ID = "1PnX-VjKsMGwWWLpcSLfQEd30FJ2f5Ln2"

# ==========================================
# Google Drive 資料夾全自動同步與轉換引擎
# ==========================================
def setup_database_from_drive():
    # 建立暫存資料夾
    if os.path.exists(TEMP_FOLDER):
        shutil.rmtree(TEMP_FOLDER)
    os.makedirs(TEMP_FOLDER)

    print(f"📂 開始從 Google Drive 資料夾同步資料: {FOLDER_ID}")
    
    try:
        # 1. 下載整個資料夾內的所有檔案
        # use_cookies=False 避免在雲端環境因權限問題卡住
        gdown.download_folder(id=FOLDER_ID, output=TEMP_FOLDER, quiet=False, use_cookies=False)
        
        # 2. 獲取所有 CSV 檔案路徑
        csv_files = glob.glob(os.path.join(TEMP_FOLDER, "**", "*.csv"), recursive=True)
        
        if not csv_files:
            print("⚠️ 警告：資料夾內沒有發現任何 CSV 檔案。")
            return

        print(f"📦 偵測到 {len(csv_files)} 個檔案，開始執行批次合併...")
        
        df_list = []
        for file in csv_files:
            try:
                # 確保地號與段名讀取為字串，防止 0 被吃掉
                df = pd.read_csv(file, dtype={
                    'land_main': str, 
                    'land_sub': str, 
                    'section': str,
                    'sub_section': str,
                    'city': str,
                    'district': str
                })
                df_list.append(df)
                print(f"✅ 已讀取: {os.path.basename(file)}")
            except Exception as e:
                print(f"❌ 讀取檔案失敗 {file}: {e}")

        # 3. 合併所有資料並清洗
        if df_list:
            combined_df = pd.concat(df_list, ignore_index=True)
            combined_df.fillna('', inplace=True) # 處理空值

            # 4. 寫入 SQLite
            conn = sqlite3.connect(DB_PATH)
            combined_df.to_sql('prices', conn, if_exists='replace', index=False)
            conn.close()
            print("🚀 所有 CSV 已成功合併並轉換為 SQLite 資料庫！")
        
        # 5. 清理暫存資料夾
        shutil.rmtree(TEMP_FOLDER)

    except Exception as e:
        print(f"💥 同步過程中發生嚴重錯誤: {e}")

# 伺服器啟動時同步一次
setup_database_from_drive()

# ==========================================
# 資料庫連線工具 (WAL 高效能模式)
# ==========================================
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
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
        cursor.execute("""
            SELECT DISTINCT section FROM prices 
            WHERE city LIKE ? AND district LIKE ?
            AND section IS NOT NULL AND section != ''
            ORDER BY section
        """, (f"%{city}%", f"%{dist}%"))
        sections = [row[0] for row in cursor.fetchall()]
        return jsonify({"sections": sections})
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
        cursor.execute("""
            SELECT DISTINCT sub_section FROM prices
            WHERE city LIKE ? AND district LIKE ? AND section = ?
            AND sub_section IS NOT NULL AND sub_section != ''
        """, (f"%{city}%", f"%{dist}%", sec))
        sub_sections = [row[0] for row in cursor.fetchall()]
        return jsonify({"subSections": sub_sections})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/get_calc_data', methods=['POST'])
def get_calc_data():
    data = get_json()
    city, dist, section = data.get('city'), data.get('district'), data.get('section')
    sub_section = data.get('subSection', '').strip()
    land_number = data.get('landNumber', '').replace('-', '')

    if len(land_number) != 8:
        return jsonify({"error": "地號格式錯誤 (需為8碼)"}), 400

    q_main, q_sub = land_number[:4], land_number[4:]
    q_main_int, q_sub_int = str(int(q_main)), str(int(q_sub))

    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT year, price, area FROM prices
            WHERE city LIKE ? AND district LIKE ? AND section = ? 
            AND (sub_section = ? OR (sub_section IS NULL AND ? = ''))
            AND (land_main IN (?, ?)) AND (land_sub IN (?, ?))
            ORDER BY year DESC
        """, (f"%{city}%", f"%{dist}%", section, sub_section, sub_section, q_main, q_main_int, q_sub, q_sub_int))
        
        rows = cursor.fetchall()
        if not rows:
            return jsonify({"yearsData": [], "area": 0})

        area = rows[0][2] if len(rows[0]) > 2 else 0
        years_data = [{"year": int(r[0]), "price": float(r[1] or 0)} for r in rows]
        return jsonify({"yearsData": years_data, "area": area})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
