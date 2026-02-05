import { NavLink } from "react-router-dom";
import { Users, Globe2, Settings } from "lucide-react";

const navLinkClass =
  "flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition hover:bg-slate-100";

export const Sidebar = () => {
  return (
    <aside className="flex h-full w-60 flex-col border-r border-slate-200 bg-white/80 backdrop-blur">
      <div className="px-4 py-4 border-b border-slate-200">
        <div className="text-sm font-semibold tracking-tight">Visa CRM</div>
        <div className="text-xs text-slate-500">BCD Travel</div>
      </div>
      <nav className="flex-1 px-3 py-4 flex flex-col gap-1 text-slate-700">
        <NavLink
          to="/users"
          className={({ isActive }) =>
            `${navLinkClass} ${isActive ? "bg-slate-900 text-white" : ""}`
          }
        >
          <Users className="h-4 w-4" />
          Пользователи
        </NavLink>
        <NavLink
          to="/visas"
          className={({ isActive }) =>
            `${navLinkClass} ${isActive ? "bg-slate-900 text-white" : ""}`
          }
        >
          <Globe2 className="h-4 w-4" />
          Визы
        </NavLink>
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `${navLinkClass} ${isActive ? "bg-slate-900 text-white" : ""}`
          }
        >
          <Settings className="h-4 w-4" />
          Настройки бота
        </NavLink>
      </nav>
    </aside>
  );
};
