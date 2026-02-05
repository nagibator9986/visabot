import sqlite3

# Путь к вашей базе данных
db_path = r"C:\Users\Cassian Comp\Desktop\projects\automated\leads.db"

# Подключаемся к базе
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Получаем список всех таблиц
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

print("Таблицы в базе данных:")
for table_name_tuple in tables:
    table_name = table_name_tuple[0]
    print(f"\nТаблица: {table_name}")

    # Получаем список колонок для таблицы
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = cursor.fetchall()
    for col in columns:
        # col = (cid, name, type, notnull, dflt_value, pk)
        print(f"  - {col[1]} ({col[2]}) {'PK' if col[5] else ''}")

# Закрываем соединение
conn.close()
