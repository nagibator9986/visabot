import { useState } from "react";
import { LeadStatus, Lead, createLead } from "@/api/leads";
import { Dialog, DialogTitle, DialogDescription } from "@/components/UI/dialog";
import { Input } from "@/components/UI/input";
import { Button } from "@/components/UI/button";
import { useToast } from "@/components/UI/use-toast";

interface Props {
  open: boolean;
  onClose: () => void;
  statuses: LeadStatus[];
  onCreated: (lead: Lead) => void;
}

export const LeadCreateDialog = ({ open, onClose, statuses, onCreated }: Props) => {
  const { toast } = useToast();

  const [email, setEmail] = useState("");
  const [subject, setSubject] = useState("");
  const [status, setStatus] = useState<string>("new");
  const [visaCountry, setVisaCountry] = useState<string>("");

  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) {
      toast({ title: "Введите email", variant: "destructive" });
      return;
    }

    setSaving(true);
    try {
      const payload = {
        from_address: email.trim(),
        subject: subject.trim() || "Лид (создан в CRM)",
        status: status || "new",
        visa_country: visaCountry || null,
      };

      const lead = await createLead(payload);
      toast({
        title: "Лид создан",
        description: `ID: ${lead.id}`,
      });
      onCreated(lead);
      onClose();
      // сброс формы
      setEmail("");
      setSubject("");
      setVisaCountry("");
      setStatus("new");
    } catch (err) {
      console.error(err);
      toast({
        title: "Ошибка создания лида",
        description: "Не удалось создать лида. Проверьте данные.",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>Создать нового пользователя / лида</DialogTitle>
      <DialogDescription>
        Укажите контактные данные и базовую информацию. Остальное можно будет
        отредактировать позже.
      </DialogDescription>

      <form onSubmit={handleSubmit} className="mt-4 space-y-3 text-sm">
        <div className="space-y-1">
          <div className="text-xs font-medium text-slate-700">Email</div>
          <Input
            type="email"
            placeholder="user@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        <div className="space-y-1">
          <div className="text-xs font-medium text-slate-700">Тема</div>
          <Input
            placeholder="Тема лида (например, Тип визы / Направление)"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
        </div>

        <div className="space-y-1">
          <div className="text-xs font-medium text-slate-700">Статус</div>
          <select
            className="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {statuses.map((s) => (
              <option key={s.code} value={s.code}>
                {s.label || s.code}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <div className="text-xs font-medium text-slate-700">
            Страна визы (опционально)
          </div>
          <Input
            placeholder="Например, SCHENGEN / PL / US"
            value={visaCountry}
            onChange={(e) => setVisaCountry(e.target.value)}
          />
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            disabled={saving}
          >
            Отмена
          </Button>
          <Button type="submit" size="sm" disabled={saving}>
            {saving ? "Создание..." : "Создать"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
};
