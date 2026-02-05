import * as React from "react";
import { cn } from "./utils";

interface TabsProps {
  value: string;
  onValueChange: (val: string) => void;
  children: React.ReactNode;
}

export const Tabs = ({ value, onValueChange, children }: TabsProps) => (
  <div className="flex flex-col gap-3">{children}</div>
);

export const TabsList = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "inline-flex items-center gap-1 rounded-xl bg-slate-100 p-1 text-xs",
      className
    )}
    {...props}
  />
);

export const TabsTrigger = ({
  className,
  isActive,
  onClick,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { isActive?: boolean }) => (
  <button
    className={cn(
      "px-3 py-1 rounded-lg transition text-xs font-medium",
      isActive ? "bg-white shadow-sm" : "text-slate-500 hover:text-slate-800",
      className
    )}
    onClick={onClick}
    {...props}
  />
);

export const TabsContent = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("mt-2", className)} {...props} />
);
