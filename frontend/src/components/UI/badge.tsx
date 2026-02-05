import * as React from "react";
import { cn } from "./utils";

export const Badge = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) => (
  <span
    className={cn(
      "inline-flex items-center rounded-full border border-slate-200 px-2.5 py-0.5 text-xs font-medium",
      className
    )}
    {...props}
  />
);
