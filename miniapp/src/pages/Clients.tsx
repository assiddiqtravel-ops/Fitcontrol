import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { atLeast, useApp } from "../state";
import { Card, EmptyState, ErrorState, Field, Loading, Modal } from "../ui";
import type { Client, Page } from "../types";

export default function Clients() {
  const { t } = useI18n();
  const { role } = useApp();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [data, setData] = useState<Page<Client> | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const res = await api<Page<Client>>("/clients", {
        query: { q, status: "active", limit: 50 },
      });
      setData(res);
    } catch (e: any) {
      setErr(e?.message ?? t("error"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const id = setTimeout(load, q ? 300 : 0);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  return (
    <div>
      <h2>{t("nav_clients")}</h2>
      <div className="toolbar">
        <input
          placeholder={t("search")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {atLeast(role, "club_admin") && (
          <button className="btn" onClick={() => setShowNew(true)}>
            + {t("add")}
          </button>
        )}
      </div>

      {loading && <Loading />}
      {err && <ErrorState message={err} onRetry={load} />}
      {data && !loading && (
        <Card>
          {data.items.length === 0 && <EmptyState />}
          {data.items.map((c) => (
            <div
              key={c.id}
              className="row list-item"
              onClick={() => nav(`/clients/${c.id}`)}
              role="button"
            >
              <div>
                <div>
                  {c.first_name} {c.last_name ?? ""}
                </div>
                <div className="muted small">{c.phone ?? "—"}</div>
              </div>
              <div className="muted">›</div>
            </div>
          ))}
        </Card>
      )}

      {showNew && (
        <NewClientModal
          onClose={() => setShowNew(false)}
          onCreated={() => {
            setShowNew(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function NewClientModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useI18n();
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    phone: "",
    birth_date: "",
    note: "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!form.first_name.trim()) {
      setErr(t("first_name"));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const body: any = { first_name: form.first_name };
      if (form.last_name) body.last_name = form.last_name;
      if (form.phone) body.phone = form.phone;
      if (form.birth_date) body.birth_date = form.birth_date;
      if (form.note) body.note = form.note;
      await api<Client>("/clients", { method: "POST", body });
      onCreated();
    } catch (e: any) {
      setErr(e?.message ?? t("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={t("new_client")} onClose={onClose}>
      {err && <div className="field-error">{err}</div>}
      <Field label={t("first_name")}>
        <input
          value={form.first_name}
          onChange={(e) => setForm({ ...form, first_name: e.target.value })}
        />
      </Field>
      <Field label={t("last_name")}>
        <input
          value={form.last_name}
          onChange={(e) => setForm({ ...form, last_name: e.target.value })}
        />
      </Field>
      <Field label={t("phone")}>
        <input
          value={form.phone}
          onChange={(e) => setForm({ ...form, phone: e.target.value })}
        />
      </Field>
      <Field label={t("birth_date")}>
        <input
          type="date"
          value={form.birth_date}
          onChange={(e) => setForm({ ...form, birth_date: e.target.value })}
        />
      </Field>
      <Field label={t("note")}>
        <textarea
          value={form.note}
          onChange={(e) => setForm({ ...form, note: e.target.value })}
        />
      </Field>
      <button className="btn btn-block" disabled={busy} onClick={submit}>
        {t("create")}
      </button>
    </Modal>
  );
}
