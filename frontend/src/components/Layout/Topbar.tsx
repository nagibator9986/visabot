import { useLocation } from "react-router-dom";

const titles: Record<string, string> = {
  "/users": "Пользователи",
  "/visas": "Визы",
  "/settings": "Настройки бота"
};

export const Topbar = () => {
  const { pathname } = useLocation();
  const title =
    titles[Object.keys(titles).find((k) => pathname.startsWith(k)) ?? ""] ??
    "Панель";

  return (
    <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div className="text-sm font-semibold">{title}</div>
      <div className="text-xs text-slate-500">Visa Team</div>
    </header>
  );
};
