// frontend/src/pages/LeadForm/LeadFormPage.tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";

import {
  LeadDetail,
  LeadForm,
  FormResponse,
  ParsedAnswer,
  QuestionnaireField,
  fetchLeadDetail,
  fetchLeadQuestionnaire,
  createLeadForm,
  updateLeadForm,
  deleteLeadForm,
  updateFormResponse,
} from "@/api/leads";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/UI/card";
import { Button } from "@/components/UI/button";
import { useToast } from "@/components/UI/use-toast";
import { LeadFormEditor } from "./LeadFormEditor";

export const LeadFormPage = () => {
  const { id } = useParams();
  const leadId = Number(id);

  const [detail, setDetail] = useState<LeadDetail | null>(null);
  const [currentForm, setCurrentForm] = useState<LeadForm | null>(null);
  const [formResponses, setFormResponses] = useState<
    (FormResponse & { _dirty?: boolean })[]
  >([]);
  const [questionnaire, setQuestionnaire] = useState<QuestionnaireField[]>([]);

  const { toast } = useToast();

  const load = async () => {
    try {
      const d = await fetchLeadDetail(leadId);
      setDetail(d);

      // Анкета: берём первую или создаём пустую
      setCurrentForm(
        d.lead_forms[0] ?? {
          id: 0,
          lead_id: leadId,
          form_type: "",
          raw_text: "",
          created_at: "",
        }
      );

      // Ответы Google Forms
      setFormResponses(
        d.form_responses.map((fr) => ({
          ...fr,
          _dirty: false,
        }))
      );

      // Сводная анкета
      try {
        const q = await fetchLeadQuestionnaire(leadId);
        setQuestionnaire(q.fields);
      } catch (e) {
        console.error("Failed to load questionnaire", e);
      }
    } catch (e) {
      console.error(e);
      toast({
        title: "Ошибка",
        description: "Не удалось загрузить данные лида.",
        variant: "destructive",
      });
    }
  };

  useEffect(() => {
    if (leadId) {
      load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leadId]);

  const handleSaveForm = async () => {
    if (!currentForm) return;

    try {
      if (currentForm.id) {
        await updateLeadForm(currentForm.id, currentForm);
      } else {
        const created = await createLeadForm({ ...currentForm, lead_id: leadId });
        setCurrentForm(created);
      }

      toast({ title: "Анкета сохранена" });
      load();
    } catch (e) {
      console.error(e);
      toast({
        title: "Ошибка",
        description: "Не удалось сохранить анкету.",
        variant: "destructive",
      });
    }
  };

  const handleDeleteForm = async () => {
    if (!currentForm?.id) return;

    try {
      await deleteLeadForm(currentForm.id);
      setCurrentForm({
        id: 0,
        lead_id: leadId,
        form_type: "",
        raw_text: "",
        created_at: "",
      });
      toast({ title: "Анкета удалена" });
      load();
    } catch (e) {
      console.error(e);
      toast({
        title: "Ошибка",
        description: "Не удалось удалить анкету.",
        variant: "destructive",
      });
    }
  };

  /* === Работа с ответами Google Forms === */

  const handleAnswerChange = (
    responseId: number,
    questionId: string,
    value: string
  ) => {
    setFormResponses((prev) =>
      prev.map((fr) =>
        fr.id === responseId
          ? {
              ...fr,
              _dirty: true,
              parsed_answers: fr.parsed_answers.map((pa: ParsedAnswer) =>
                pa.question_id === questionId ? { ...pa, value } : pa
              ),
            }
          : fr
      )
    );
  };

  const handleSaveFormResponse = async (responseId: number) => {
    const fr = formResponses.find((x) => x.id === responseId);
    if (!fr) return;

    try {
      const updated = await updateFormResponse(responseId, fr.parsed_answers);
      setFormResponses((prev) =>
        prev.map((x) =>
          x.id === responseId ? { ...updated, _dirty: false } : x
        )
      );
      toast({ title: "Ответ формы сохранён" });
      // после сохранения можно обновить и сводную анкету
      load();
    } catch (e) {
      console.error(e);
      toast({
        title: "Ошибка",
        description: "Не удалось сохранить изменения ответа формы",
        variant: "destructive",
      });
    }
  };

  if (!detail) {
    return <div className="text-sm text-slate-500">Загрузка...</div>;
  }

  return (
    <motion.div
      className="grid gap-4 md:grid-cols-[2fr_1.5fr]"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      {/* Левая колонка - Лид + ручная анкета */}
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Лид #{detail.lead.id}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-1">
            <div>
              <span className="font-medium">Email: </span>
              {detail.lead.from_address}
            </div>
            <div>
              <span className="font-medium">Тема: </span>
              {detail.lead.subject}
            </div>
            <div>
              <span className="font-medium">Статус: </span>
              {detail.lead.status_label || detail.lead.status}
            </div>
            <div>
              <span className="font-medium">Страна: </span>
              {detail.lead.visa_country || "не указана"}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Анкета пользователя (ручная)</CardTitle>
          </CardHeader>
          <CardContent>
            <LeadFormEditor
              leadForm={currentForm}
              onChange={(v) =>
                setCurrentForm((prev) => ({
                  ...(prev as LeadForm),
                  ...v,
                }))
              }
              onSave={handleSaveForm}
              onDelete={handleDeleteForm}
            />
          </CardContent>
        </Card>
      </div>

      {/* Правая колонка - Сводная анкета + Google Forms + Audit */}
      <div className="space-y-4">
        {/* Сводная анкета */}
        <Card>
          <CardHeader>
            <CardTitle>Сводная анкета</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {questionnaire.length === 0 && (
              <div className="text-xs text-slate-500">
                Данных анкеты пока нет (ни Google Forms, ни ручных анкет).
              </div>
            )}

            {questionnaire.map((field) => (
              <div
                key={field.code}
                className="grid grid-cols-1 gap-1 md:grid-cols-[1.2fr,2fr] border-b border-slate-100 pb-1"
              >
                <div className="text-[11px] font-medium text-slate-600 pr-2">
                  {field.label || field.code}
                  <span className="ml-1 text-[10px] text-slate-400">
                    ({field.source === "gform" ? "Google Forms" : "ручная анкета"})
                  </span>
                </div>
                <div className="text-xs text-slate-800 break-words">
                  {field.value || <span className="text-slate-400">—</span>}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Блок с расшифрованными ответами Google Forms */}
        <Card>
          <CardHeader>
            <CardTitle>Ответы Google Forms</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {formResponses.length === 0 && (
              <div className="text-xs text-slate-500">Ответов пока нет.</div>
            )}

            {formResponses.map((r) => (
              <div
                key={r.id}
                className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-xs">
                      {r.respondent_email || "Без e-mail"}
                    </div>
                    <div className="text-[11px] text-slate-500">
                      {r.visa_country || "Страна не указана"} •{" "}
                      {r.form_id || "form_id"} • {r.created_at || ""}
                    </div>
                  </div>

                  <Button
                    size="sm"
                    variant={r._dirty ? "default" : "outline"}
                    disabled={!r._dirty}
                    onClick={() => handleSaveFormResponse(r.id)}
                  >
                    {r._dirty ? "Сохранить" : "Сохранено"}
                  </Button>
                </div>

                {/* Список вопросов/ответов */}
                <div className="space-y-2 mt-2">
                  {r.parsed_answers.map((pa) => (
                    <div
                      key={pa.question_id}
                      className="grid grid-cols-1 gap-1 md:grid-cols-[1.2fr,2fr]"
                    >
                      <label className="text-[11px] text-slate-500 pr-2">
                        {pa.label}
                      </label>
                      <input
                        className="border border-slate-200 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-slate-200"
                        value={pa.value}
                        onChange={(e) =>
                          handleAnswerChange(
                            r.id,
                            pa.question_id,
                            e.target.value
                          )
                        }
                      />
                    </div>
                  ))}
                </div>
                {/* Список вопросов/ответов */}
<div className="space-y-2 mt-2">
  {r.parsed_answers.map((pa) => (
    <div
      key={pa.question_id}
      className="grid grid-cols-1 gap-1 md:grid-cols-[1.2fr,2fr]"
    >
      <label className="text-[11px] text-slate-500 pr-2">
        {pa.label}
      </label>
      <input
        className="border border-slate-200 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-slate-200"
        value={pa.value}
        onChange={(e) =>
          handleAnswerChange(
            r.id,
            pa.question_id,
            e.target.value
          )
        }
      />
    </div>
  ))}
</div>

{/* НОВОЕ: загруженные файлы */}
{r.attachments && r.attachments.length > 0 && (
  <div className="mt-3 border-t border-slate-200 pt-2">
    <div className="text-[11px] font-semibold text-slate-600 mb-1">
      Загруженные файлы
    </div>
    <ul className="space-y-1 text-[11px] text-slate-600">
      {r.attachments.map((att) => (
        <li key={`${att.question_id}-${att.file_id}`}>
          <span className="font-medium">{att.label}:</span>{" "}
          <a
            href={att.drive_url}
            target="_blank"
            rel="noreferrer"
            className="underline"
          >
            {att.file_name}
          </a>
        </li>
      ))}
    </ul>
  </div>
)}


                {/* По желанию — посмотреть сырое raw_json */}
                <details className="mt-2 text-[11px] text-slate-500">
                  <summary className="cursor-pointer select-none">
                    Показать raw JSON
                  </summary>
                  <pre className="mt-1 max-h-60 overflow-auto rounded bg-slate-900 text-slate-50 p-2 text-[10px] leading-snug">
                    {r.raw_json}
                  </pre>
                </details>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* История аудита */}
        <Card>
          <CardHeader>
            <CardTitle>История действий (AuditLog)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            {detail.audit_logs.length === 0 && (
              <div className="text-slate-500">История пока пуста.</div>
            )}
            {detail.audit_logs.map((log) => (
              <div key={log.id} className="border-b border-slate-100 pb-1">
                <div className="font-medium">{log.event}</div>
                {log.details && (
                  <div className="text-slate-600">{log.details}</div>
                )}
                <div className="text-[10px] text-slate-400 mt-0.5">
                  {log.created_at}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </motion.div>
  );
};
