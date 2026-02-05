import { create } from "zustand";
import {
  Lead,
  LeadFilterParams,
  fetchLeads,
  fetchStatuses,
  LeadStatus
} from "@/api/leads";

interface LeadsState {
  leads: Lead[];
  statuses: LeadStatus[];
  loading: boolean;
  filters: LeadFilterParams;
  setFilters: (f: Partial<LeadFilterParams>) => void;
  loadLeads: () => Promise<void>;
  loadStatuses: () => Promise<void>;
}

export const useLeadsStore = create<LeadsState>((set, get) => ({
  leads: [],
  statuses: [],
  loading: false,
  filters: {},
  setFilters: (f) =>
    set((state) => ({
      filters: { ...state.filters, ...f }
    })),
  loadLeads: async () => {
    set({ loading: true });
    try {
      const data = await fetchLeads(get().filters);
      set({ leads: data });
    } finally {
      set({ loading: false });
    }
  },
  loadStatuses: async () => {
    const data = await fetchStatuses();
    set({ statuses: data });
  }
}));
