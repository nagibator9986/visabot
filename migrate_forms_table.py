import os
import sqlite3

DB_PATH = 'C:/Users/Cassian Comp/Desktop/projects/automated/bot/leads.db'
def main():
    print(f"Использую БД: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Показать существующие таблицы
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r["name"] for r in cur.fetchall()]
    print("Существующие таблицы:", tables)

    if "visa_applications" not in tables:
        print("Таблицы visa_applications нет — ОШИБКА. Проверяй путь к БД.")
        conn.close()
        return

    # Создаём уникальный индекс, если его ещё нет
    print("Создаю UNIQUE INDEX для (visa_type, google_response_id), если его ещё нет...")
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_visa_applications_visa_type_google_response
        ON visa_applications(visa_type, google_response_id)
        """
    )
    conn.commit()

    # Посмотрим все индексы по этой таблице
    cur.execute("PRAGMA index_list('visa_applications')")
    idxs = cur.fetchall()
    print("Индексы visa_applications:")
    for idx in idxs:
        print(" -", dict(idx))

    conn.close()
    print("Готово. Теперь ON CONFLICT(visa_type, google_response_id) будет работать.")

if __name__ == "__main__":
    main()