import { RouterProvider } from "react-router-dom";
import { router } from "./router";
import { ToastProvider } from "@/components/UI/ToastProvider";

export const App = () => (
  <ToastProvider>
    <RouterProvider router={router} />
  </ToastProvider>
);
