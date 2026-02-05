import os

# Полный список файлов и папок
structure = {
    "index.html": "",
    "package.json": "",
    "tsconfig.json": "",
    "vite.config.ts": "",
    "postcss.config.cjs": "",
    "tailwind.config.cjs": "",
    "src/main.tsx": "",
    "src/App.tsx": "",
    "src/router.tsx": "",
    "src/index.css": "",
    "src/api/client.ts": "",
    "src/api/leads.ts": "",
    "src/api/visas.ts": "",
    "src/api/settings.ts": "",
    "src/store/useLeadsStore.ts": "",
    "src/store/useSettingsStore.ts": "",
    "src/components/Layout/Layout.tsx": "",
    "src/components/Layout/Sidebar.tsx": "",
    "src/components/Layout/Topbar.tsx": "",
    "src/components/UI/ConfirmDialog.tsx": "",
    "src/components/UI/ToastProvider.tsx": "",
    "src/components/ui/button.tsx": "",
    "src/components/ui/card.tsx": "",
    "src/components/ui/input.tsx": "",
    "src/components/ui/label.tsx": "",
    "src/components/ui/textarea.tsx": "",
    "src/components/ui/select.tsx": "",
    "src/components/ui/badge.tsx": "",
    "src/components/ui/table.tsx": "",
    "src/components/ui/tabs.tsx": "",
    "src/components/ui/dialog.tsx": "",
    "src/components/ui/toast.tsx": "",
    "src/components/ui/use-toast.ts": "",
    "src/pages/Users/UsersPage.tsx": "",
    "src/pages/Users/LeadTable.tsx": "",
    "src/pages/Users/LeadFilters.tsx": "",
    "src/pages/Users/LeadStatusBadge.tsx": "",
    "src/pages/LeadForm/LeadFormPage.tsx": "",
    "src/pages/LeadForm/LeadFormEditor.tsx": "",
    "src/pages/Visas/VisasPage.tsx": "",
    "src/pages/Visas/VisaCard.tsx": "",
    "src/pages/Visas/VisaDetailPage.tsx": "",
    "src/pages/Settings/SettingsPage.tsx": "",
}

def create_structure(base_dir="frontend"):
    print(f"Создаю структуру внутри: {base_dir}")

    for path, content in structure.items():
        full_path = os.path.join(base_dir, path)
        folder = os.path.dirname(full_path)

        # Создание папки, если ее нет
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"[+] Создана папка: {folder}")

        # Создание файла, если его нет
        if not os.path.exists(full_path):
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[+] Создан файл: {full_path}")
        else:
            print(f"[=] Пропущено (уже существует): {full_path}")

    print("\nГотово! 🎉 Вся структура создана.")

if __name__ == "__main__":
    create_structure()
