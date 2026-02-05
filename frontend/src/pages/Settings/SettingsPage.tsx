import { useEffect, useState } from "react";
import { motion } from "framer-motion";

import {
  fetchBotSettings,
  updateBotSettings,
  BotSettings,
} from "@/api/settings";

import { Card, CardHeader, CardTitle, CardContent } from "@/components/UI/card";
import { Input } from "@/components/UI/input";
import { Button } from "@/components/UI/button";
import { useToast } from "@/components/UI/use-toast";
import { Textarea } from "@/components/UI/textarea";

export const SettingsPage = () => {
  const { toast } = useToast();
  const [settings, setSettings] = useState<BotSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchBotSettings();
        setSettings(data);
      } catch (e) {
        console.error(e);
        toast({
          title: "Ошибка загрузки настроек",
          description: "Не удалось получить настройки бота.",
          variant: "destructive",
        });
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [toast]);

  const handleTextChange =
    (field: keyof BotSettings) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      if (!settings) return;
      setSettings({ ...settings, [field]: e.target.value });
    };

  const handleNumberChange =
    (field: keyof BotSettings) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (!settings) return;
      const value = e.target.value === "" ? "" : Number(e.target.value);
      setSettings({ ...settings, [field]: value as any });
    };

  const handleCheckboxChange =
    (field: keyof BotSettings) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (!settings) return;
      setSettings({ ...settings, [field]: e.target.checked as any });
    };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!settings) return;

    setSaving(true);
    try {
      const payload: Partial<BotSettings> = {
        bot_name: settings.bot_name,
        sender_email: settings.sender_email,
        first_reminder_days: settings.first_reminder_days,
        second_reminder_days: settings.second_reminder_days,
        poll_interval_seconds: settings.poll_interval_seconds,
        send_window_start_hour: settings.send_window_start_hour,
        send_window_end_hour: settings.send_window_end_hour,
        auto_create_leads: settings.auto_create_leads,
        auto_change_status: settings.auto_change_status,
        auto_reminders_enabled: settings.auto_reminders_enabled,
        form_poland_url: settings.form_poland_url,
        form_schengen_url: settings.form_schengen_url,
        form_usa_url: settings.form_usa_url,
        form_generic_url: settings.form_generic_url,
        extra_config: settings.extra_config,
      };

      const updated = await updateBotSettings(payload);
      setSettings(updated);

      toast({
        title: "Настройки сохранены",
        description: "Изменения успешно применены.",
      });
    } catch (e) {
      console.error(e);
      toast({
        title: "Ошибка сохранения",
        description: "Не удалось сохранить настройки бота.",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading || !settings) {
    return <div className="text-sm text-slate-500">Загрузка настроек...</div>;
  }

  return (
    <motion.div
      className="grid gap-4 md:grid-cols-2"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      {/* Левая колонка: общие, тайминги, поведение */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Общие настройки</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="space-y-1">
              <div className="text-xs font-medium text-slate-700">Имя бота</div>
              <Input
                value={settings.bot_name}
                onChange={handleTextChange("bot_name")}
                placeholder="BCD Travel Bot"
              />
            </div>

            <div className="space-y-1">
              <div className="text-xs font-medium text-slate-700">
                Email отправителя
              </div>
              <Input
                value={settings.sender_email}
                onChange={handleTextChange("sender_email")}
                placeholder="visa@itplus.kz"
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Тайминги и опрос</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm md:grid-cols-2">
            <div className="space-y-1">
              <div className="text-xs font-medium text-slate-700">
                Первый ремайндер (дней)
              </div>
              <Input
                type="number"
                min={0}
                max={365}
                value={settings.first_reminder_days}
                onChange={handleNumberChange("first_reminder_days")}
              />
            </div>

            <div className="space-y-1">
              <div className="text-xs font-medium text-slate-700">
                Второй ремайндер (дней)
              </div>
              <Input
                type="number"
                min={0}
                max={365}
                value={settings.second_reminder_days}
                onChange={handleNumberChange("second_reminder_days")}
              />
            </div>

            <div className="space-y-1 md:col-span-2">
              <div className="text-xs font-medium text-slate-700">
                Интервал опроса (секунды)
              </div>
              <Input
                type="number"
                min={1}
                max={3600}
                value={settings.poll_interval_seconds}
                onChange={handleNumberChange("poll_interval_seconds")}
              />
              <div className="text-[11px] text-slate-500">
                Как часто бот проверяет почту и напоминания.
              </div>
            </div>

            <div className="space-y-1 md:col-span-2">
              <div className="text-xs font-medium text-slate-700">
                Окно отправки писем (часы)
              </div>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min={0}
                  max={23}
                  value={settings.send_window_start_hour}
                  onChange={handleNumberChange("send_window_start_hour")}
                  className="w-20"
                />
                <span className="text-xs text-slate-500">до</span>
                <Input
                  type="number"
                  min={0}
                  max={23}
                  value={settings.send_window_end_hour}
                  onChange={handleNumberChange("send_window_end_hour")}
                  className="w-20"
                />
              </div>
              <div className="text-[11px] text-slate-500">
                Бот не будет отправлять письма вне этого диапазона (локальное
                время).
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Автоматизация</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <label className="flex items-center justify-between gap-4">
              <div>
                <div className="text-xs font-medium text-slate-700">
                  Автоматически создавать лиды
                </div>
                <div className="text-[11px] text-slate-500">
                  Из новых входящих писем.
                </div>
              </div>
              <Input
                type="checkbox"
                className="h-4 w-4"
                checked={settings.auto_create_leads}
                onChange={handleCheckboxChange("auto_create_leads")}
              />
            </label>

            <label className="flex items-center justify-between gap-4">
              <div>
                <div className="text-xs font-medium text-slate-700">
                  Автоматически менять статус
                </div>
                <div className="text-[11px] text-slate-500">
                  Например, при заполнении анкеты.
                </div>
              </div>
              <Input
                type="checkbox"
                className="h-4 w-4"
                checked={settings.auto_change_status}
                onChange={handleCheckboxChange("auto_change_status")}
              />
            </label>

            <label className="flex items-center justify-between gap-4">
              <div>
                <div className="text-xs font-medium text-slate-700">
                  Авто-ремайндеры
                </div>
                <div className="text-[11px] text-slate-500">
                  Бот сам будет слать follow-up письма.
                </div>
              </div>
              <Input
                type="checkbox"
                className="h-4 w-4"
                checked={settings.auto_reminders_enabled}
                onChange={handleCheckboxChange("auto_reminders_enabled")}
              />
            </label>
          </CardContent>
        </Card>

        <div className="flex justify-end">
          <Button type="submit" disabled={saving}>
            {saving ? "Сохранение..." : "Сохранить настройки"}
          </Button>
        </div>
      </form>

      {/* Правая колонка: формы + JSON-конфиг */}
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Google Forms</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="space-y-1">
              <div className="text-xs font-medium text-slate-700">
                Форма Польша
              </div>
              <Input
                value={settings.form_poland_url ?? ""}
                onChange={handleTextChange("form_poland_url")}
                placeholder="https://docs.google.com/forms/..."
              />
            </div>

            <div className="space-y-1">
              <div className="text-xs font-medium text-slate-700">
                Форма Шенген
              </div>
              <Input
                value={settings.form_schengen_url ?? ""}
                onChange={handleTextChange("form_schengen_url")}
                placeholder="https://docs.google.com/forms/..."
              />
            </div>

            <div className="space-y-1">
              <div className="text-xs font-medium text-slate-700">
                Форма США
              </div>
              <Input
                value={settings.form_usa_url ?? ""}
                onChange={handleTextChange("form_usa_url")}
                placeholder="https://docs.google.com/forms/..."
              />
            </div>

            <div className="space-y-1">
              <div className="text-xs font-medium text-slate-700">
                Общая форма
              </div>
              <Input
                value={settings.form_generic_url ?? ""}
                onChange={handleTextChange("form_generic_url")}
                placeholder="https://docs.google.com/forms/..."
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Доп. конфигурация (JSON)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="text-[11px] text-slate-500">
              Здесь можно хранить любые доп. параметры в формате JSON
              (например, шаблоны писем).
            </div>
            <Textarea
              className="font-mono text-[11px] min-h-[160px]"
              value={JSON.stringify(settings.extra_config ?? {}, null, 2)}
              onChange={(e) => {
                try {
                  const parsed = JSON.parse(e.target.value || "{}");
                  setSettings({
                    ...(settings as BotSettings),
                    extra_config: parsed,
                  });
                } catch {
                  // если JSON кривой — просто не обновляем extra_config
                }
              }}
            />
          </CardContent>
        </Card>
      </div>
    </motion.div>
  );
};

export default SettingsPage;
