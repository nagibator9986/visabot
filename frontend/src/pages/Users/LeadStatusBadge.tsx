import { Badge } from "@/components/UI/badge";

export const LeadStatusBadge = ({ status, label }: { status?: string | null; label?: string | null }) => {
  if (!status) return null;
  const normalized = status.toLowerCase();
  let cls = "border-slate-200 bg-slate-50";
  if (normalized === "new") cls = "border-blue-200 bg-blue-50 text-blue-700";
  if (normalized.includes("questionnaire")) cls = "border-amber-200 bg-amber-50 text-amber-700";
  if (normalized.includes("docs")) cls = "border-indigo-200 bg-indigo-50 text-indigo-700";
  if (normalized.includes("closed")) cls = "border-emerald-200 bg-emerald-50 text-emerald-700";

  return <Badge className={cls}>{label || status}</Badge>;
};
