import { create } from "zustand";
import { BotSettings, fetchBotSettings, updateBotSettings } from "@/api/settings";

interface SettingsState {
  settings: BotSettings | null;
  loading: boolean;
  loadSettings: () => Promise<void>;
  saveSettings: (payload: Partial<BotSettings>) => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  settings: null,
  loading: false,
  loadSettings: async () => {
    set({ loading: true });
    try {
      const s = await fetchBotSettings();
      set({ settings: s });
    } finally {
      set({ loading: false });
    }
  },
  saveSettings: async (payload) => {
    const current = get().settings ?? ({} as BotSettings);
    const s = await updateBotSettings({ ...current, ...payload });
    set({ settings: s });
  }
}));
