# -*- coding: utf-8 -*-
"""
Created on Thu Apr 16 19:44:04 2026

@author: fkk
"""

import sqlite3

def setup_test_db():
    # 這會自動在同一個資料夾產生 land_data.db 檔案
    conn = sqlite3.connect('land_data.db')
    cursor = conn.cursor()
    
    # 建立資料表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prices (
            city TEXT,
            district TEXT,
            section TEXT,
            land_number TEXT,
            year INTEGER,
            price REAL
        )
    ''')
    
    # 清空舊資料（避免重複執行產生重複資料）
    cursor.execute('DELETE FROM prices')
    
    # 插入測試資料 (新北市 板橋區 文化段 05000000)
    test_data = [
        ('新北市', '板橋區', '文化段', '05000000', 109, 50000),
        ('新北市', '板橋區', '文化段', '05000000', 111, 52000),
        ('新北市', '板橋區', '文化段', '05000000', 113, 55000),
        ('新北市', '板橋區', '文化段', '05000000', 115, 56000)
    ]
    cursor.executemany('INSERT INTO prices VALUES (?,?,?,?,?,?)', test_data)
    
    conn.commit()
    conn.close()
    print("測試用資料庫 (land_data.db) 建立完成！")

if __name__ == '__main__':
    setup_test_db()