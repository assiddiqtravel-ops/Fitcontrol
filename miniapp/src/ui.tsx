import { ReactNode } from "react";
import { useI18n } from "./i18n";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>;
}

export function StatCard({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="stat-card">
      <div className="stat-value" style={accent ? { color: accent } : undefined}>
        {value}
      </div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export function Loading() {
  const { t } = useI18n();
  return <div className="state-msg">{t("loading")}</div>;
}

export function EmptyState({ text }: { text?: string }) {
  const { t } = useI18n();
  return <div className="state-msg muted">{text ?? t("empty")}</div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div className="state-msg error">
      <div>⚠️ {message}</div>
      {onRetry && (
        <button className="btn" onClick={onRetry} style={{ marginTop: 8 }}>
          {t("retry")}
        </button>
      )}
    </div>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="close">
            ✕
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function Badge({ text, tone = "neutral" }: { text: string; tone?: string }) {
  return <span className={`badge badge-${tone}`}>{text}</span>;
}
