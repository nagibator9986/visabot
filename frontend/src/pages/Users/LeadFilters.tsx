import { LeadFilterParams, LeadStatus } from "@/api/leads";
import { Input } from "@/components/UI/input";
import { Select } from "@/components/UI/select";
import { Label } from "@/components/UI/label";
import { motion } from "framer-motion";

interface Props {
  filters: LeadFilterParams;
  statuses: LeadStatus[];
  onChange: (v: Partial<LeadFilterParams>) => void;
}

export const LeadFilters = ({ filters, statuses, onChange }: Props) => {
  return (
    <motion.div
      className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-3"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      <div className="flex flex-col gap-1">
        <Label>Поиск (email / тема)</Label>
        <Input
          placeholder="example@company.com"
          value={filters.search ?? ""}
          onChange={(e) => onChange({ search: e.target.value })}
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label>Статус</Label>
        <Select
          value={filters.status ?? ""}
          onChange={(e) => onChange({ status: e.target.value || undefined })}
        >
          <option value="">Все</option>
          {statuses.map((s) => (
            <option key={s.code} value={s.code}>
              {s.label}
            </option>
          ))}
        </Select>
      </div>
      <div className="flex flex-col gap-1">
        <Label>Страна визы</Label>
        <Input
          placeholder="PL / US / FR..."
          value={filters.visa_country ?? ""}
          onChange={(e) => onChange({ visa_country: e.target.value || undefined })}
        />
      </div>
    </motion.div>
  );
};
