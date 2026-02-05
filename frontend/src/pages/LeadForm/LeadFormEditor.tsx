import { LeadForm } from "@/api/leads";
import { Label } from "@/components/UI/label";
import { Select } from "@/components/UI/select";
import { Textarea } from "@/components/UI/textarea";
import { Button } from "@/components/UI/button";

const FORM_OPTIONS = [
  { value: "poland", label: "Польша" },
  { value: "schengen", label: "Шенген" },
  { value: "usa", label: "США" },
  { value: "germany", label: "Германия" },
  { value: "france", label: "Франция" },
  { value: "italy", label: "Италия" },
  { value: "spain", label: "Испания" },
  { value: "generic", label: "Универсальная" }
];

interface Props {
  leadForm: LeadForm | null;
  onChange: (value: Partial<LeadForm>) => void;
  onSave: () => void;
  onDelete?: () => void;
}

export const LeadFormEditor = ({ leadForm, onChange, onSave, onDelete }: Props) => {
  const formType = leadForm?.form_type ?? "";
  const rawText = leadForm?.raw_text ?? "";

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="flex flex-col gap-1">
          <Label>Тип анкеты</Label>
          <Select
            value={formType}
            onChange={(e) => onChange({ form_type: e.target.value })}
          >
            <option value="">Не указан</option>
            {FORM_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <Label>Текст анкеты (raw_text)</Label>
        <Textarea
          rows={10}
          placeholder="1. ФИО&#10;2. Дата рождения&#10;3. ..."
          value={rawText}
          onChange={(e) => onChange({ raw_text: e.target.value })}
        />
      </div>
      <div className="flex items-center justify-between">
        <Button onClick={onSave}>Сохранить</Button>
        {leadForm?.id && onDelete && (
          <Button variant="destructive" onClick={onDelete}>
            Удалить анкету
          </Button>
        )}
      </div>
    </div>
  );
};
