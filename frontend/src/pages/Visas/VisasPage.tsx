// frontend/src/pages/Visas/VisasPage.tsx
import { useEffect, useState } from "react";
import { fetchVisas, Visa } from "@/api/visas";
import { VisaCard } from "./VisaCard";

export const VisasPage = () => {
  const [visas, setVisas] = useState<Visa[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        setVisas(await fetchVisas());
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Визы</h1>
        <p className="text-xs text-slate-500">
          Справочник стран и быстрый старт процесса подачи на визу.
        </p>
      </div>
      {loading ? (
        <div className="text-sm text-slate-500">Загрузка...</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          {visas.map((visa) => (
            <VisaCard key={visa.code} visa={visa} />
          ))}
        </div>
      )}
    </div>
  );
};
