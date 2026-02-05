import db
print(db.DB_PATH)
conn = db.get_connection()
print("База подключена:", conn)
conn.close()
