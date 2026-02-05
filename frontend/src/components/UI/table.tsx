import * as React from "react";
import { cn } from "./utils";

export const Table = ({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) => (
  <table className={cn("w-full text-sm", className)} {...props} />
);
export const Thead = (props: React.HTMLAttributes<HTMLTableSectionElement>) => (
  <thead className="text-xs uppercase text-slate-500" {...props} />
);
export const Tbody = (props: React.HTMLAttributes<HTMLTableSectionElement>) => (
  <tbody className="divide-y divide-slate-100" {...props} />
);
export const Tr = (props: React.HTMLAttributes<HTMLTableRowElement>) => (
  <tr className="hover:bg-slate-50/70" {...props} />
);
export const Th = (props: React.ThHTMLAttributes<HTMLTableCellElement>) => (
  <th className="px-4 py-2 text-left font-semibold" {...props} />
);
export const Td = (props: React.TdHTMLAttributes<HTMLTableCellElement>) => (
  <td className="px-4 py-2 align-middle" {...props} />
);
