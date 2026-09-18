import { useEffect, useState } from "react";
import { api } from "../api";
import { formatMoney } from "../format";
import { useI18n } from "../i18n";
import { atLeast, useApp } from "../state";
import { Badge, Card, EmptyState, ErrorState, Field, Loading, Modal } from "../ui";
import type { Plan } from "../types";

export default function Subscriptions() {
  const { t, lang } = useI18n();
  const { role } = useApp();
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      setPlans(await api<Plan[]>("/plans"));
    } catch (e: any) {
      setErr(e?.message ?? t("error"));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <h2>{t("plans")}</h2>
      {atLeast(role, "club_admin") && (
        <button className="btn btn-block" onClick={() => setShowNew(true)}>
          + {t("new_plan")}
        </button>
      )}
      <div style={{ height: 12 }} />
      {loading && <Loading />}
      {err && <ErrorState message={err} onRetry={load} />}
      {plans && !loading && (
        <Card>
          {plans.length === 0 && <EmptyState />}
          {plans.map((p) => (
            <div className="row" key={p.id}>
              <div>
                <div>{p.name}</div>
                <div className="muted small">
                  {p.duration_value} {p.duration_unit === "days" ? t("days") : t("months")}
                  {p.visit_limit != null ? ` · ${p.visit_limit}` : ` · ${t("unlimited")}`}
                </div>
              </div>
              <div className="right">
                <div>{formatMoney(p.price, lang)}</div>
                {!p.is_active && <Badge text={t("archived")} tone="neutral" />}
              </div>
            </div>
          ))}
        </Card>
      )}

      {showNew && (
        <NewPlanModal
          onClose={() => setShowNew(false)}
          onDone={() => {
            setShowNew(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function NewPlanModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useI18n();
  const [form, setForm] = useState({
    name: "",
    price: "",
    duration_value: "1",
    duration_unit: "months",
    visit_limit: "",
    description: "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    const price = Number(form.price);
    const dv = Number(form.duration_value);
    if (!form.name.trim() || price < 0 || dv <= 0) {
      setErr(t("error"));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const body: any = {
        name: form.name,
        price,
        duration_value: dv,
        duration_unit: form.duration_unit,
      };
      if (form.visit_limit) body.visit_limit = Number(form.visit_limit);
      if (form.description) body.description = form.description;
      await api("/plans", { method: "POST", body });
      onDone();
    } catch (e: any) {
      setErr(e?.message ?? t("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={t("new_plan")} onClose={onClose}>
      {err && <div className="field-error">{err}</div>}
      <Field label={t("plan_name")}>
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </Field>
      <Field label={`${t("price")} (UZS)`}>
        <input
          type="number"
          value={form.price}
          onChange={(e) => setForm({ ...form, price: e.target.value })}
        />
      </Field>
      <div className="toolbar">
        <Field label={t("duration")}>
          <input
            type="number"
            value={form.duration_value}
            onChange={(e) => setForm({ ...form, duration_value: e.target.value })}
          />
        </Field>
        <Field label=" ">
          <select
            value={form.duration_unit}
            onChange={(e) => setForm({ ...form, duration_unit: e.target.value })}
          >
            <option value="months">{t("months")}</option>
            <option value="days">{t("days")}</option>
          </select>
        </Field>
      </div>
      <Field label={t("visit_limit")}>
        <input
          type="number"
          placeholder={t("unlimited")}
          value={form.visit_limit}
          onChange={(e) => setForm({ ...form, visit_limit: e.target.value })}
        />
      </Field>
      <button className="btn btn-block" disabled={busy} onClick={submit}>
        {t("create")}
      </button>
    </Modal>
  );
}
