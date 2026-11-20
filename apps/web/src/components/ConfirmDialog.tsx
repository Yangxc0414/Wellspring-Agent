import { createPortal } from "react-dom";

/**
 * Reusable two-step destructive-action confirm card.
 *
 * The sidebar's task/workspace delete uses the same .confirm-layer/.confirm-card
 * shapes; this component centralizes them so settings / palette / agent actions
 * stop falling back to the native window.confirm() (which renders an out-of-place
 * OS dialog inside an otherwise custom UI, and can even show "undefined" when
 * called without an argument).
 */
export interface ConfirmDialogProps {
  open: boolean;
  eyebrow?: string;
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({ open, eyebrow, title, body, confirmLabel, onConfirm, onCancel }: ConfirmDialogProps) {
  if (!open) return null;
  return createPortal(
    <div className="confirm-layer" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel(); }}>
      <section className="confirm-card" role="alertdialog" aria-modal="true" aria-labelledby="confirm-dialog-title">
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h3 id="confirm-dialog-title">{title}</h3>
        <p>{body}</p>
        <div className="confirm-actions">
          <button type="button" className="text-button" onClick={onCancel}>取消</button>
          <button type="button" className="solid-button danger" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </section>
    </div>,
    document.body
  );
}
