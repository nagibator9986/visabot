import os

# ====== НАСТРОЙКИ ======
SOURCE_DIR = r"C:\Users\Cassian Comp\Desktop\projects\automated\bot"  # папка, которую сканируем
OUTPUT_DIR = "backend"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "main.py")

EXCLUDE_DIRS = {"__pycache__", "migrations"}
# ======================


def collect_python_files(source_dir):
    py_files = []

    for root, dirs, files in os.walk(source_dir):
        # исключаем ненужные папки
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in files:
            if file.endswith(".py"):
                py_files.append(os.path.join(root, file))

    return py_files


def merge_files(py_files, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as out:
        for file_path in py_files:
            out.write(f"\n\n# ===== FILE: {file_path} =====\n\n")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    out.write(f.read())
            except Exception as e:
                out.write(f"# ERROR READING FILE: {e}\n")


def main():
    py_files = collect_python_files(SOURCE_DIR)
    merge_files(py_files, OUTPUT_FILE)
    print(f"✅ Объединено файлов: {len(py_files)}")
    print(f"📁 Результат сохранён в: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
