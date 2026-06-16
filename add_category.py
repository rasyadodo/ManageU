import sqlite3
import os

db_path = os.path.join('c:\\Users\\LENOVO\\OneDrive\\ドキュメント\\Project pemograman lanjut', 'instance', 'database.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE `transaction` ADD COLUMN category VARCHAR(50)")
    conn.commit()
    print("Successfully added 'category' column to 'transaction' table.")
except Exception as e:
    print(f"Skipped adding column: {e}")

conn.close()
