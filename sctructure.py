import os

# ====== НАСТРОЙКИ ======
PROJECT_ROOT = r"C:\Users\Cassian Comp\Desktop\projects\automated\visabot\frontend"
SOURCE_DIR = os.path.join(PROJECT_ROOT, "src")  # ТОЛЬКО src
OUTPUT_DIR = "frontend"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "main.js")

# папки, которые игнорируем
EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "__tests__",
    "tests"
}

# расширения файлов
INCLUDE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}

# файлы, которые игнорируем по имени
EXCLUDE_FILE_SUFFIXES = (
    ".test.js",
    ".test.jsx",
    ".test.ts",
    ".test.tsx",
    ".spec.js",
    ".spec.jsx",
    ".spec.ts",
    ".spec.tsx",
    ".d.ts"
)
# ======================


def collect_js_files(source_dir):
    js_files = []

    for root, dirs, files in os.walk(source_dir):
        # исключаем ненужные папки
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in files:
            ext = os.path.splitext(file)[1]

            if ext not in INCLUDE_EXTENSIONS:
                continue

            if file.endswith(EXCLUDE_FILE_SUFFIXES):
                continue

            js_files.append(os.path.join(root, file))

    return js_files


def merge_files(js_files, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as out:
        for file_path in js_files:
            out.write(f"\n\n// ===== FILE: {os.path.relpath(file_path, SOURCE_DIR)} =====\n\n")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    out.write(f.read())
            except Exception as e:
                out.write(f"// ERROR READING FILE: {e}\n")


def main():
    if not os.path.exists(SOURCE_DIR):
        print("❌ Папка src не найдена")
        return

    js_files = collect_js_files(SOURCE_DIR)
    merge_files(js_files, OUTPUT_FILE)

    print(f"✅ Объединено файлов: {len(js_files)}")
    print(f"📁 Результат сохранён в: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
