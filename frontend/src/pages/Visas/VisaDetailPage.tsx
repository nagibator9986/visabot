// frontend/src/pages/Visas/VisaDetailPage.tsx

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { fetchVisa, startVisa, Visa } from "@/api/visas";
import { fetchLeads, Lead } from "@/api/leads";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/UI/card";
import { Button } from "@/components/UI/button";
import { motion } from "framer-motion";
import { useToast } from "@/components/UI/use-toast";
import { Dialog, DialogDescription, DialogTitle } from "@/components/UI/dialog";

export const VisaDetailPage = () => {
  const { code } = useParams();
  const [visa, setVisa] = useState<Visa | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [selectedLeadId, setSelectedLeadId] = useState<number | null>(null);

  const [loading, setLoading] = useState(false);
  const [loadingLeads, setLoadingLeads] = useState(false);
  const [successOpen, setSuccessOpen] = useState(false);

  const { toast } = useToast();

  // грузим визу
  useEffect(() => {
    const loadVisa = async () => {
      if (!code) return;
      setLoading(true);
      try {
        const v = await fetchVisa(code);
        setVisa(v);
      } finally {
        setLoading(false);
      }
    };
    loadVisa();
  }, [code]);

  // грузим список лидов
  useEffect(() => {
    const loadLeads = async () => {
      setLoadingLeads(true);
      try {
        const items = await fetchLeads();
        setLeads(items);
      } finally {
        setLoadingLeads(false);
      }
    };
    loadLeads();
  }, []);

  const handleStart = async () => {
    if (!code) return;

    if (!selectedLeadId) {
      toast({
        title: "Не выбран пользователь",
        description: "Пожалуйста, выбери лида для подачи на визу.",
        variant: "destructive",
      });
      return;
    }

    await startVisa(code, selectedLeadId);
    toast({
      title: "Подача на визу запущена",
      description: `Лид #${selectedLeadId} отправлен на обработку по визе ${visa?.name}.`,
    });
    setSuccessOpen(true);
  };

  if (!visa || loading) {
    return <div className="text-sm text-slate-500">Загрузка...</div>;
  }

  return (
    <motion.div
      className="max-w-3xl space-y-4"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      <Card>
        <CardHeader>
          <CardTitle>{visa.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p>{visa.description}</p>

          <div>
            <div className="mb-1 font-semibold">Тип визы:</div>
            <p className="text-slate-700">{visa.type}</p>
          </div>

          <div>
            <div className="mb-1 font-semibold">Требования:</div>
            <ul className="list-disc pl-5 space-y-1">
              {visa.requirements.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>

          <div>
            <div className="mb-1 font-semibold">Сроки рассмотрения:</div>
            <p className="text-slate-600">{visa.processing_time}</p>
          </div>

          <div className="pt-4 space-y-3 border-t border-slate-100">
            <div className="text-sm font-semibold">
              Выбор пользователя для подачи
            </div>

            {loadingLeads ? (
              <div className="text-xs text-slate-500">Загрузка списка лидов...</div>
            ) : leads.length === 0 ? (
              <div className="text-xs text-slate-500">
                Лиды пока отсутствуют. Сначала создайте лида в CRM.
              </div>
            ) : (
              <div className="space-y-1">
                <label className="text-xs text-slate-700">
                  Пользователь (лид):
                </label>
                <select
                  className="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm"
                  value={selectedLeadId ?? ""}
                  onChange={(e) => {
                    const val = e.target.value;
                    setSelectedLeadId(val ? Number(val) : null);
                  }}
                >
                  <option value="">— выберите лида —</option>
                  {leads.map((lead) => (
                    <option key={lead.id} value={lead.id}>
                      #{lead.id} • {lead.from_address || "без email"} •{" "}
                      {lead.subject || ""}
                    </option>
                  ))}
                </select>
                <div className="text-[11px] text-slate-500">
                  Этот лид будет отмечен как начавший процесс по визе
                  (запишем событие в AuditLog).
                </div>
              </div>
            )}
          </div>

          <div className="pt-2">
  <Button
    disabled={!selectedLeadId}
    onClick={handleStart}
  >
    Запустить подачу на визу
  </Button>
</div>

        </CardContent>
      </Card>

      <Dialog open={successOpen} onClose={() => setSuccessOpen(false)}>
        <DialogTitle>Подача на визу запущена</DialogTitle>
        <DialogDescription>
          Событие зафиксировано в системе. Менеджер увидит это в CRM и продолжит
          обработку заявки.
        </DialogDescription>
        <div className="mt-4 flex justify-end">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setSuccessOpen(false)}
          >
            Ок
          </Button>
        </div>
      </Dialog>
    </motion.div>
  );
};
