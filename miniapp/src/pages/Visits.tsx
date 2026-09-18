import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { formatDate } from "../format";
import { useI18n } from "../i18n";
import { Badge, Card, EmptyState, ErrorState, Field, Loading, Modal } from "../ui";
import type { Client, Page, Visit, VisitEligibility } from "../types";

export default function Visits() {
  const { t, lang } = useI18n();
  const [visits, setVisits] = useState<Visit[] | null>(null);
  const [clientMap, setClientMap] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showReg, setShowReg] = useState(false);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const [v, clients] = await Promise.all([
        api<Visit[]>("/visits", { query: { limit: 50 } }),
        api<Page<Client>>("/clients", { query: { limit: 100 } }),
      ]);
      setVisits(v);
      const map: Record<number, string> = {};
      clients.items.forEach((c) => (map[c.id] = `${c.first_name} ${c.last_name ?? ""}`.trim()));
      setClientMap(map);
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
      <h2>{t("nav_visits")}</h2>
      <button className="btn btn-block" onClick={() => setShowReg(true)}>
        {t("register_visit")}
      </button>
      <h3 style={{ margin: "16px 0 8px" }}>{t("visit_history")}</h3>
      {loading && <Loading />}
      {err && <ErrorState message={err} onRetry={load} />}
      {visits && !loading && (
        <Card>
          {visits.length === 0 && <EmptyState />}
          {visits.map((v) => (
            <div className="row" key={v.id}>
              <div>
                <div>{clientMap[v.client_id] ?? `#${v.client_id}`}</div>
                <div className="muted small">{formatDate(v.created_at, lang)}</div>
              </div>
              {v.result === "override" ? (
                <Badge text={t("override_reason")} tone="warning" />
              ) : (
                <Badge text="✓" tone="success" />
              )}
            </div>
          ))}
        </Card>
      )}
      {showReg && (
        <RegisterVisitModal
          clientMap={clientMap}
          onClose={() => setShowReg(false)}
          onDone={() => {
            setShowReg(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function RegisterVisitModal({
  clientMap,
  onClose,
  onDone,
}: {
  clientMap: Record<number, string>;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const [clientId, setClientId] = useState<number | "">("");
  const [elig, setElig] = useState<VisitEligibility | null>(null);
  const [override, setOverride] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!clientId) {
      setElig(null);
      return;
    }
    api<VisitEligibility>(`/clients/${clientId}/visit-eligibility`)
      .then(setElig)
      .catch(() => setElig(null));
  }, [clientId]);

  async function submit() {
    if (!clientId) return;
    setBusy(true);
    setErr(null);
    try {
      const body: any = { client_id: clientId };
      if (elig && !elig.allowed) {
        if (!override.trim()) {
          setErr(t("visit_override_hint"));
          setBusy(false);
          return;
        }
        body.override_reason = override;
      }
      await api("/visits", { method: "POST", body });
      onDone();
    } catch (e: any) {
      if (e instanceof ApiError) setErr(e.message);
      else setErr(t("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={t("register_visit")} onClose={onClose}>
      {err && <div className="field-error">{err}</div>}
      <Field label={t("nav_clients")}>
        <select value={clientId} onChange={(e) => setClientId(Number(e.target.value))}>
          <option value="">—</option>
          {Object.entries(clientMap).map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
      </Field>

      {elig && (
        <Card>
          {elig.allowed ? (
            <div style={{ color: "var(--success)" }}>
              ✓ {t("eligible")}
              {elig.visits_left != null && (
                <div className="muted small">
                  {t("visits_left")}: {elig.visits_left}
                </div>
              )}
            </div>
          ) : (
            <div style={{ color: "var(--danger)" }}>
              ✕ {t("not_eligible")} — {t(`reason_${elig.reason}`)}
            </div>
          )}
        </Card>
      )}

      {elig && !elig.allowed && (
        <>
          <p className="muted small">{t("visit_override_hint")}</p>
          <Field label={t("override_reason")}>
            <input value={override} onChange={(e) => setOverride(e.target.value)} />
          </Field>
        </>
      )}

      <button className="btn btn-block" disabled={busy || !clientId} onClick={submit}>
        {t("register_visit")}
      </button>
    </Modal>
  );
}
