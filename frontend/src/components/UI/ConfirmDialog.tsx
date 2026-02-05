import { Dialog, DialogDescription, DialogTitle } from "@/components/UI/dialog";
import { Button } from "@/components/UI/button";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export const ConfirmDialog = ({
  open,
  title,
  description,
  confirmLabel = "Подтвердить",
  cancelLabel = "Отмена",
  onConfirm,
  onCancel
}: ConfirmDialogProps) => (
  <Dialog open={open} onClose={onCancel}>
    <DialogTitle>{title}</DialogTitle>
    {description && <DialogDescription>{description}</DialogDescription>}
    <div className="mt-4 flex justify-end gap-2">
      <Button variant="ghost" size="sm" onClick={onCancel}>
        {cancelLabel}
      </Button>
      <Button variant="destructive" size="sm" onClick={onConfirm}>
        {confirmLabel}
      </Button>
    </div>
  </Dialog>
);
