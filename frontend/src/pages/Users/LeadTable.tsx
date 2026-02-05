import { Link } from "react-router-dom";
import { Lead, LeadStatus, updateLead, deleteLead } from "@/api/leads";
import { Table, Thead, Tbody, Tr, Th, Td } from "@/components/UI/table";
import { Select } from "@/components/UI/select";
import { Button } from "@/components/UI/button";
import { LeadStatusBadge } from "./LeadStatusBadge";
import { useState } from "react";
import { ConfirmDialog } from "@/components/UI/ConfirmDialog";
import { useToast } from "@/components/UI/use-toast";

interface Props {
  leads: Lead[];
  statuses: LeadStatus[];
  reload: () => void;
}

export const LeadTable = ({ leads, statuses, reload }: Props) => {
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const { toast } = useToast();

  const statusMap = Object.fromEntries(statuses.map((s) => [s.code, s]));

  const handleStatusChange = async (id: number, status: string) => {
    await updateLead(id, { status });
    toast({ title: "Статус обновлён" });
    reload();
  };

  const handleDelete = async () => {
    if (!deleteId) return;
    await deleteLead(deleteId);
    setDeleteId(null);
    toast({ title: "Лид удалён" });
    reload();
  };

  return (
    <>
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <Table>
          <Thead>
            <Tr>
              <Th>ID</Th>
              <Th>Email</Th>
              <Th>Тема</Th>
              <Th>Страна</Th>
              <Th>Статус</Th>
              <Th>Анкеты</Th>
              <Th className="text-right">Действия</Th>
            </Tr>
          </Thead>
          <Tbody>
            {leads.map((lead) => {
              const s = lead.status ? statusMap[lead.status] : undefined;
              return (
                <Tr key={lead.id}>
                  <Td>{lead.id}</Td>
                  <Td>{lead.from_address}</Td>
                  <Td className="max-w-xs truncate">{lead.subject}</Td>
                  <Td>{lead.visa_country}</Td>
                  <Td>
                    <div className="flex items-center gap-2">
                      <LeadStatusBadge status={lead.status} label={lead.status_label} />
                      <Select
                        value={lead.status ?? ""}
                        onChange={(e) => handleStatusChange(lead.id, e.target.value)}
                        className="w-32 text-xs"
                      >
                        <option value="">—</option>
                        {statuses.map((st) => (
                          <option key={st.code} value={st.code}>
                            {st.label}
                          </option>
                        ))}
                      </Select>
                    </div>
                  </Td>
                  <Td>
                    {lead.forms_count ?? 0} / {lead.form_responses_count ?? 0}
                  </Td>
                  <Td className="text-right">
                    <Link to={`/users/${lead.id}/form`}>
                      <Button size="sm" variant="outline" className="mr-2">
                        Анкета
                      </Button>
                    </Link>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setDeleteId(lead.id)}
                    >
                      Удалить
                    </Button>
                  </Td>
                </Tr>
              );
            })}
          </Tbody>
        </Table>
      </div>

      <ConfirmDialog
        open={deleteId !== null}
        title="Удалить лида?"
        description="Действие необратимо, данные будут удалены из CRM."
        onCancel={() => setDeleteId(null)}
        onConfirm={handleDelete}
      />
    </>
  );
};
