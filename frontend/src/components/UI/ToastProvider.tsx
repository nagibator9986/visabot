import { ToastViewport } from "@/components/UI/toast";

export const ToastProvider = ({ children }: { children: React.ReactNode }) => {
  return (
    <>
      {children}
      <ToastViewport />
    </>
  );
};
