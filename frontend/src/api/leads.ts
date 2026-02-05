// frontend/src/api/leads.ts
import { api } from "./client";

// ---- Базовые типы лида ----

export interface Lead {
  id: number;
  from_address: string | null;
  subject: string | null;
  visa_country: string | null;
  status: string | null;
  status_label?: string | null;
  questionnaire_status?: string | null;
  questionnaire_form_id?: string | null;
  questionnaire_response_id?: string | null;
  last_message_id?: string | null;
  last_contacted?: string | null;
  next_reminder_at?: string | null;
  reminders_sent?: number;
  form_ack_sent?: number;
  forms_count?: number;
  form_responses_count?: number;
}

export interface LeadFilterParams {
  status?: string;
  visa_country?: string;
  search?: string;
}

// ---- LeadForm (ручная анкета по письму) ----

export interface LeadForm {
  id: number;
  lead_id: number | null;   // <-- привязка к лиду
  form_type: string | null;
  raw_text: string | null;
  created_at: string | null;
}

// ---- FormResponse (ответ Google Forms) ----

export interface ParsedAnswer {
  question_id: string;
  label: string;
  value: string;
}

export interface FormResponse {
  id: number;
  lead_id: number | null;   // поправка: в БД поле lead_id
  visa_country: string | null;
  form_id: string | null;
  response_id: string;
  respondent_email: string | null;
  raw_json: string | null;
  created_at: string | null;
  parsed_answers: ParsedAnswer[];
}

// ---- AuditLog ----

export interface AuditLog {
  id: number;
  lead_id: number | null;
  event: string | null;
  details: string | null;
  created_at: string | null;
}

// ---- Детальный ответ по лиду ----

export interface LeadDetail {
  lead: Lead;
  lead_forms: LeadForm[];
  form_responses: FormResponse[];
  audit_logs: AuditLog[];
}

// ---- Статусы лида ----

export interface LeadStatus {
  code: string;
  label: string;
  description?: string;
}

// ---- Сводная анкета (questionnaire) ----

export interface QuestionnaireField {
  code: string;   // внутренний код поля (например, "full_name")
  label: string;  // человекочитаемый заголовок
  value: string;  // склеенное значение
  source: "gform" | "manual"; // откуда взято: Google Forms или ручная анкета
}

export interface LeadQuestionnaireResponse {
  lead_id: number;
  fields: QuestionnaireField[];
}

// ================== API-функции по лидам ==================

// список лидов
export const fetchLeads = async (params?: LeadFilterParams) => {
  const res = await api.get<Lead[]>("/leads/", { params });
  return res.data;
};

// детальная информация по лиду
export const fetchLeadDetail = async (id: number) => {
  const res = await api.get<LeadDetail>(`/leads/${id}/detail/`);
  return res.data;
};

// сводная анкета для лида
export const fetchLeadQuestionnaire = async (leadId: number) => {
  const res = await api.get<LeadQuestionnaireResponse>(
    `/leads/${leadId}/questionnaire/`
  );
  return res.data;
};

// статусы
export const fetchStatuses = async () => {
  const res = await api.get<LeadStatus[]>("/statuses/");
  return res.data;
};

// обновление лида (например, смена статуса)
export const updateLead = async (id: number, data: Partial<Lead>) => {
  const res = await api.patch<Lead>(`/leads/${id}/`, data);
  return res.data;
};

// создание лида
export const createLead = async (payload: Partial<Lead>) => {
  const res = await api.post<Lead>("/leads/", payload);
  return res.data;
};

// удаление лида
export const deleteLead = async (id: number) => {
  await api.delete(`/leads/${id}/`);
};

// ---- LeadForm CRUD ----

export const createLeadForm = async (payload: Partial<LeadForm>) => {
  const res = await api.post<LeadForm>("/lead-forms/", payload);
  return res.data;
};

export const updateLeadForm = async (id: number, payload: Partial<LeadForm>) => {
  const res = await api.patch<LeadForm>(`/lead-forms/${id}/`, payload);
  return res.data;
};

export const deleteLeadForm = async (id: number) => {
  await api.delete(`/lead-forms/${id}/`);
};

// ---- Обновление ответов Google Forms (parsed_answers) ----

export const updateFormResponse = async (
  id: number,
  parsed_answers: ParsedAnswer[]
): Promise<FormResponse> => {
  const res = await api.patch<FormResponse>(`/form-responses/${id}/`, {
    parsed_answers,
  });
  return res.data;
};
export interface FormAttachment {
  question_id: string;
  label: string;
  file_id: string;
  file_name: string;
  drive_url: string;
}

export interface FormResponse {
  id: number;
  lead: number | null;
  visa_country: string | null;
  form_id: string | null;
  response_id: string;
  respondent_email: string | null;
  raw_json: string | null;
  created_at: string | null;
  parsed_answers: ParsedAnswer[];
  attachments?: FormAttachment[];   // 👈 НОВОЕ
}
