// frontend/src/api/settings.ts
import { api } from "./client";

export interface BotSettings {
  id: number;
  bot_name: string;
  sender_email: string;
  first_reminder_days: number;
  second_reminder_days: number;

  // опрос бота / окно отправки писем
  poll_interval_seconds: number;
  send_window_start_hour: number;
  send_window_end_hour: number;

  auto_create_leads: boolean;
  auto_change_status: boolean;
  auto_reminders_enabled: boolean;

  form_poland_url: string | null;
  form_schengen_url: string | null;
  form_usa_url: string | null;
  form_generic_url: string | null;

  extra_config: Record<string, unknown>;
}

export const fetchBotSettings = async () => {
  const res = await api.get<BotSettings>("/bot-settings/");
  return res.data;
};

export const updateBotSettings = async (payload: Partial<BotSettings>) => {
  const res = await api.put<BotSettings>("/bot-settings/", payload);
  return res.data;
};
