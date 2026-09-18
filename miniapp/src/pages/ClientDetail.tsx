import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, uuid } from "../api";
import { formatDate, formatMoney } from "../format";
import { useI18n } from "../i18n";
import { confirmDanger } from "../telegram";
import { atLeast, useApp } from "../state";
import { Badge, Card, EmptyState, ErrorState, Field, Loading, Modal } from "../ui";
import type { Client, Ledger, Payment, Plan, Subscription } from "../types";

function statusTone(status: string): string {
  if (status === "active") return "success";
  if (status === "expired" || status === "cancelled") return "danger";
  if (status === "frozen" || status === "upcoming") return "warning";
  return "neutral";
}

export default function ClientDetail() {
  const { id } = useParams();
  const clientId = Number(id);
  const { t, lang } = useI18n();
  const { role } = useApp();
  const nav = useNavigate();

  const [client, setClient] = useState<Client | null>(null);
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [modal, setModal] = useState<null | "sub" | "pay">(null);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const [c, l, s, p] = await Promise.all([
        api<Client>(`/clients/${clientId}`),
        api<Ledger>(`/clients/${clientId}/ledger`),
        api<Subscription[]>("/subscriptions", { query: { client_id: clientId } }),
        api<Payment[]>("/payments", { query: { client_id: clientId } }),
      ]);
      setClient(c);
      setLedger(l);
      setSubs(s);
      setPayments(p);
    } catch (e: any) {
      setErr(e?.message ?? t("error"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  async function archive() {
    if (!(await confirmDanger(t("confirm_archive")))) return;
    await api(`/clients/${clientId}/archive`, { method: "POST" });
    nav("/clients");
  }

  if (loading) return <Loading />;
  if (err) return <ErrorState message={err} onRetry={load} />;
  if (!client || !ledger) return <EmptyState />;

  const canAdmin = atLeast(role, "club_admin");

  return (
    <div>
      <button className="btn btn-secondary" onClick={() => nav("/clients")}>
        ‹ {t("nav_clients")}
      </button>
      <h2 style={{ marginTop: 12 }}>
        {client.first_name} {client.last_name ?? ""}
      </h2>

      <Card>
        <div className="row">
          <span className="muted">{t("phone")}</span>
          <span>{client.phone ?? "—"}</span>
        </div>
        <div className="row">
          <span className="muted">{t("birth_date")}</span>
          <span>{formatDate(client.birth_date, lang)}</span>
        </div>
        <div className="row">
          <span className="muted">{t("client_debt")}</span>
          <span style={{ color: ledger.debt > 0 ? "var(--danger)" : "var(--success)" }}>
            {formatMoney(ledger.debt, lang)}
          </span>
        </div>
        {ledger.credit > 0 && (
          <div className="row">
            <span className="muted">{t("client_credit")}</span>
            <span style={{ color: "var(--success)" }}>{formatMoney(ledger.credit, lang)}</span>
          </div>
        )}
        {client.note && <div className="small muted" style={{ marginTop: 8 }}>{client.note}</div>}
      </Card>

      {canAdmin && (
        <div className="toolbar">
          <button className="btn btn-block" onClick={() => setModal("sub")}>
            {t("assign_subscription")}
          </button>
          <button className="btn btn-block" onClick={() => setModal("pay")}>
            {t("new_payment")}
          </button>
        </div>
      )}

      <h3 style={{ margin: "16px 0 8px" }}>{t("nav_subscriptions")}</h3>
      <Card>
        {subs.length === 0 && <EmptyState />}
        {subs.map((s) => (
          <div className="row" key={s.id}>
            <div>
              <div>
                {formatDate(s.start_date, lang)} — {formatDate(s.end_date, lang)}
              </div>
              <div className="muted small">
                {formatMoney(s.price, lang)}
                {s.visit_limit != null
                  ? ` · ${s.visits_used}/${s.visit_limit}`
                  : ""}
              </div>
            </div>
            <Badge text={t(`status`) + ": " + s.status} tone={statusTone(s.status)} />
          </div>
        ))}
      </Card>

      <h3 style={{ margin: "16px 0 8px" }}>{t("payments")}</h3>
      <Card>
        {payments.length === 0 && <EmptyState />}
        {payments.map((p) => (
          <div className="row" key={p.id}>
            <div>
              <div style={{ textDecoration: p.is_reversed ? "line-through" : "none" }}>
                {formatMoney(p.amount, lang)}
              </div>
              <div className="muted small">
                {t(`method_${p.method}`)} · {formatDate(p.paid_at, lang)}
              </div>
            </div>
            {p.is_reversed ? (
              <Badge text={t("reverse")} tone="danger" />
            ) : (
              canAdmin && (
                <button
                  className="icon-btn"
                  title={t("reverse")}
                  onClick={async () => {
                    if (!(await confirmDanger(t("confirm_reverse")))) return;
                    const reason = window.prompt(t("reason"));
                    if (!reason) return;
                    await api(`/payments/${p.id}/reverse`, {
                      method: "POST",
                      body: { reason },
                    });
                    load();
                  }}
                >
                  ↩
                </button>
              )
            )}
          </div>
        ))}
      </Card>

      {canAdmin && (
        <button className="btn btn-danger btn-block" onClick={archive} style={{ marginTop: 8 }}>
          {t("archive")}
        </button>
      )}

      {modal === "sub" && (
        <AssignSubModal
          clientId={clientId}
          onClose={() => setModal(null)}
          onDone={() => {
            setModal(null);
            load();
          }}
        />
      )}
      {modal === "pay" && (
        <PaymentModal
          clientId={clientId}
          onClose={() => setModal(null)}
          onDone={() => {
            setModal(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function AssignSubModal({
  clientId,
  onClose,
  onDone,
}: {
  clientId: number;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [planId, setPlanId] = useState<number | "">("");
  const [startDate, setStartDate] = useState(new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<Plan[]>("/plans", { query: { active_only: "true" } }).then(setPlans).catch(() => {});
  }, []);

  async function submit() {
    if (!planId) return;
    setBusy(true);
    setErr(null);
    try {
      await api("/subscriptions", {
        method: "POST",
        body: { client_id: clientId, plan_id: planId, start_date: startDate },
      });
      onDone();
    } catch (e: any) {
      setErr(e?.message ?? t("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={t("assign_subscription")} onClose={onClose}>
      {err && <div className="field-error">{err}</div>}
      <Field label={t("plans")}>
        <select value={planId} onChange={(e) => setPlanId(Number(e.target.value))}>
          <option value="">—</option>
          {plans.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("start_date")}>
        <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
      </Field>
      <button className="btn btn-block" disabled={busy || !planId} onClick={submit}>
        {t("create")}
      </button>
    </Modal>
  );
}

function PaymentModal({
  clientId,
  onClose,
  onDone,
}: {
  clientId: number;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Stable idempotency key for the lifetime of this modal so a double-tap
  // cannot create two payments.
  const [key] = useState(uuid());

  async function submit() {
    const amt = Number(amount);
    if (!amt || amt <= 0) {
      setErr(t("amount"));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api("/payments", {
        method: "POST",
        idempotencyKey: key,
        body: { client_id: clientId, amount: amt, method, comment: comment || undefined },
      });
      onDone();
    } catch (e: any) {
      setErr(e?.message ?? t("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={t("new_payment")} onClose={onClose}>
      {err && <div className="field-error">{err}</div>}
      <Field label={`${t("amount")} (UZS)`}>
        <input
          type="number"
          inputMode="numeric"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </Field>
      <Field label={t("method")}>
        <select value={method} onChange={(e) => setMethod(e.target.value)}>
          <option value="cash">{t("method_cash")}</option>
          <option value="card">{t("method_card")}</option>
          <option value="transfer">{t("method_transfer")}</option>
          <option value="other">{t("method_other")}</option>
        </select>
      </Field>
      <Field label={t("comment")}>
        <input value={comment} onChange={(e) => setComment(e.target.value)} />
      </Field>
      <button className="btn btn-block" disabled={busy} onClick={submit}>
        {t("save")}
      </button>
    </Modal>
  );
}
