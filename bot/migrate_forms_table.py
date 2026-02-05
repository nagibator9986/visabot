import os
import sqlite3

DB_PATH = os.getenv("LEADS_DB_PATH")

if not DB_PATH:
    raise SystemExit("LEADS_DB_PATH is not set in environment")

print(f"Использую БД: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Показываем текущие колонки
cur.execute("PRAGMA table_info(form_responses)")
cols = cur.fetchall()
print("Текущие колонки form_responses:")
for c in cols:
    # c: (cid, name, type, notnull, dflt_value, pk)
    print(f" - {c[1]} {c[2]}")

col_names = {c[1] for c in cols}

if "raw_json" not in col_names:
    print("Добавляю колонку raw_json...")
    cur.execute("ALTER TABLE form_responses ADD COLUMN raw_json TEXT")
    conn.commit()
    print("Готово. Колонка raw_json добавлена.")
else:
    print("Колонка raw_json уже есть, ничего делать не нужно.")

conn.close()
