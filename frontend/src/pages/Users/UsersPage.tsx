// frontend/src/pages/Users/UsersPage.tsx
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useLeadsStore } from "@/store/useLeadsStore";
import { LeadFilters } from "./LeadFilters";
import { LeadTable } from "./LeadTable";
import { Button } from "@/components/UI/button";
import { useToast } from "@/components/UI/use-toast";
import { LeadCreateDialog } from "./LeadCreateDialog";

export const UsersPage = () => {
  const {
    leads,
    statuses,
    filters,
    setFilters,
    loadLeads,
    loadStatuses,
    loading,
  } = useLeadsStore();

  const { toast } = useToast();
  const [createOpen, setCreateOpen] = useState(false);

  useEffect(() => {
    loadStatuses();
  }, [loadStatuses]);

  useEffect(() => {
    loadLeads();
  }, [filters, loadLeads]);

  const handleCreated = () => {
    // после создания перезагружаем список
    loadLeads();
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="flex flex-col gap-4"
    >
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Пользователи / Лиды</h1>
          <p className="text-xs text-slate-500">
            Управление лидами, статусами и анкетами.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>Создать пользователя</Button>
      </div>

      <LeadFilters
        filters={filters}
        statuses={statuses}
        onChange={(f) => setFilters(f)}
      />

      {loading ? (
        <div className="text-sm text-slate-500">Загрузка...</div>
      ) : (
        <LeadTable leads={leads} statuses={statuses} reload={loadLeads} />
      )}

      <LeadCreateDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        statuses={statuses}
        onCreated={handleCreated}
      />
    </motion.div>
  );
};
