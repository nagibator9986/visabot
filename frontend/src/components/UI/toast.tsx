// toast.tsx
import { useToastStore } from "./use-toast";
import { Button } from "./button";

export const ToastViewport = () => {
  const { toasts, dismiss } = useToastStore();
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="min-w-[220px] max-w-xs rounded-xl bg-white shadow-soft border border-slate-200 p-3"
        >
          <div className="text-sm font-medium">{toast.title}</div>
          {toast.description && (
            <div className="mt-1 text-xs text-slate-600">{toast.description}</div>
          )}
          <div className="mt-2 flex justify-end">
            <Button size="sm" variant="ghost" onClick={() => dismiss(toast.id)}>
              Закрыть
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
};
