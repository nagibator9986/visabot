import * as React from "react";
import { cn } from "./utils";

export const Label = ({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => (
  <label className={cn("text-xs font-medium text-slate-600", className)} {...props} />
);
