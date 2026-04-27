from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import pandas as pd
import glob
import shutil
import gc
import zipfile  # 💡 新增：用來解壓縮本機端的 ZIP 檔

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "land_data.db")
ZIP_PATH = os.path.join(BASE_DIR, "land_data.zip")  # 💡 指向你上傳的 ZIP 檔
TEMP_FOLDER = os.path.join(BASE_DIR, "zip_extracted_temp")

# ==========================================
# 本機 ZIP 解壓縮與低記憶體轉換引擎
# ==========================================
def setup_database_from_zip():
    # 如果已經轉換過資料庫，就不重複執行，加快啟動速度
    if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 10000:
        print("✅ 資料庫已存在，跳過重建。")
        return

    if not os.path.exists(ZIP_PATH):
        print(f"⚠️ 找不到檔案: {ZIP_PATH}，請確認 land_data.zip 已上傳。")
        return

    # 建立或清空暫存解壓縮區
    if os.path.exists(TEMP_FOLDER): shutil.rmtree(TEMP_FOLDER)
    os.makedirs(TEMP_FOLDER)

    try:
        print(f"📦 開始解壓縮 {ZIP_PATH} ...")
        # 1. 解壓縮 ZIP 檔
        with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
            zip_ref.extractall(TEMP_FOLDER)
        
        # 2. 找出裡面所有的 CSV 檔案
        csv_files = glob.glob(os.path.join(TEMP_FOLDER, "**", "*.csv"), recursive=True)
        if not csv_files:
            print("⚠️ 警告：ZIP 檔案內查無 CSV 檔案！")
            return

        conn = sqlite3.connect(DB_PATH)
        is_first_chunk = True

        # 3. 分塊讀取並寫入資料庫
        for file in csv_files:
            print(f"⏳ 處理檔案: {os.path.basename(file)}")
            try:
                chunk_iterator = pd.read_csv(file, dtype=str, chunksize=10000)
                
                for chunk in chunk_iterator:
                    # 淨水器：清除隱形空白
                    chunk.columns = chunk.columns.str.strip() 
                    chunk = chunk.map(lambda x: x.strip() if isinstance(x, str) else x)
                    
                    # 防呆補正
                    if 'area' not in chunk.columns: chunk['area'] = 0
                    if 'sub_section' not in chunk.columns: chunk['sub_section'] = ''
                    chunk.fillna('', inplace=True)
                    
                    # 寫入 SQLite
                    mode = 'replace' if is_first_chunk else 'append'
                    chunk.to_sql('prices', conn, if_exists=mode, index=False)
                    is_first_chunk = False

                    del chunk
                    gc.collect()

                print(f"✅ 已成功轉入: {os.path.basename(file)}")
            except Exception as e:
                print(f"❌ 讀取失敗 {file}: {e}")

        conn.close()
        # 4. 清理暫存解壓縮出來的檔案，節省伺服器空間
        shutil.rmtree(TEMP_FOLDER)
        print("🚀 ZIP 資料庫分塊轉換完成！")
        
    except Exception as e:
        print(f"💥 解壓縮或轉換失敗: {e}")

# 伺服器啟動時執行轉換
setup_database_from_zip()

# ==========================================
# 資料庫連線工具
# ==========================================
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def get_json():
    return request.get_json(silent=True) or {}

# ==========================================
# 頁面與 API 路由 (邏輯完全不變)
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
        cursor.execute("SELECT DISTINCT section FROM prices WHERE city=? AND district=? AND section!='' ORDER BY section", (city, dist))
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
        cursor.execute("SELECT DISTINCT sub_section FROM prices WHERE city=? AND district=? AND section=? AND sub_section!='' ORDER BY sub_section", (city, dist, sec))
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
