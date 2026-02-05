import sqlite3

conn = sqlite3.connect("leads.db")
cur = conn.cursor()

# Все проблемные значения со старым форматом обнулим
cur.execute("UPDATE leads SET next_reminder_at = NULL WHERE next_reminder_at LIKE '%T%'")
conn.commit()
conn.close()

print("Done")
