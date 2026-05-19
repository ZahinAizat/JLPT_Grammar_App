import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "jlpt_app.db"


conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
SELECT name, tbl_name
FROM sqlite_master
WHERE type = 'index'
ORDER BY tbl_name, name
""")

rows = cursor.fetchall()

print("=" * 50)
print("Indexes in database")
print("=" * 50)

if not rows:
    print("No indexes found.")
else:
    for row in rows:
        print(row)

conn.close()