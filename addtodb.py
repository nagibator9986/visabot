#!/usr/bin/env python3
import os
import sqlite3

# Если у тебя уже есть db.py с get_connection, можно использовать его:
try:
    import db  # твой модуль работы с БД
    USE_DB_MODULE = True
except ImportError:
    USE_DB_MODULE = False

# Путь к БД: используем ту же переменную, что и в проекте
DB_PATH = os.getenv("LEADS_DB_PATH", "leads.db")


def get_conn() -> sqlite3.Connection:
    if USE_DB_MODULE and hasattr(db, "get_connection"):
        return db.get_connection()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def clear_data():
    print(f"Подключаемся к БД: {DB_PATH}")
    conn = get_conn()
    cur = conn.cursor()

    # Список таблиц, которые хотим очистить
    # Добавь сюда другие, если нужны (например, если у тебя есть ещё что-то)
    tables_to_clear = [
        "leads",
        "form_responses",
        "audit_log",
    ]

    for table in tables_to_clear:
        try:
            print(f"Очищаем таблицу {table} ...")
            cur.execute(f"DELETE FROM {table}")
        except sqlite3.Error as e:
            print(f"⚠ Не удалось очистить {table}: {e}")

    # Сброс автоинкремента (чтобы id снова шли с 1)
    try:
        cur.execute(
            """
            DELETE FROM sqlite_sequence
            WHERE name IN ({})
            """.format(
                ",".join("?" for _ in tables_to_clear)
            ),
            tables_to_clear,
        )
        print("Сбросили счётчики AUTOINCREMENT для очищенных таблиц.")
    except sqlite3.Error as e:
        print(f"⚠ Не удалось сбросить sqlite_sequence: {e}")

    conn.commit()
    conn.close()
    print("Готово. Все данные из указанных таблиц удалены.")


if __name__ == "__main__":
    clear_data()
