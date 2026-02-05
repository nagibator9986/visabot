// frontend/src/api/visas.ts
import { api } from "./client";

export interface Visa {
  code: string;
  name: string;
  type: string;
  description: string;
  requirements: string[];
  processing_time: string;
}

// список всех виз
export const fetchVisas = async () => {
  const res = await api.get<Visa[]>("/visas/");
  return res.data;
};

// детальная инфа по визе
export const fetchVisa = async (code: string) => {
  const res = await api.get<Visa>(`/visas/${code}/`);
  return res.data;
};

// запуск процесса по визе с опциональным lead_id
export const startVisa = async (code: string, leadId?: number) => {
  const payload = leadId ? { lead_id: leadId } : {};
  const res = await api.post(`/visas/${code}/start/`, payload);
  return res.data;
};
