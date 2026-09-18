import { useEffect, useState } from "react";
import { api } from "../api";
import { formatMoney } from "../format";
import { useI18n } from "../i18n";
import { StatCard, ErrorState, Loading } from "../ui";
import type { Dashboard } from "../types";

type Period = "today" | "7d" | "month" | "custom";

export default function Overview() {
  const { t, lang } = useI18n();
  const [period, setPeriod] = useState<Period>("month");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const query: Record<string, string> = { period };
      if (period === "custom" && start && end) {
        query.start = start;
        query.end = end;
      }
      const d = await api<Dashboard>("/dashboard", { query });
      setData(d);
    } catch (e: any) {
      setErr(e?.message ?? t("error"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (period !== "custom" || (start && end)) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, start, end]);

  return (
    <div>
      <h2>{t("nav_overview")}</h2>
      <div className="pills">
        {(["today", "7d", "month", "custom"] as Period[]).map((p) => (
          <button
            key={p}
            className={`pill ${period === p ? "active" : ""}`}
            onClick={() => setPeriod(p)}
          >
            {t(`period_${p}`)}
          </button>
        ))}
      </div>
      {period === "custom" && (
        <div className="toolbar">
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
      )}

      {loading && <Loading />}
      {err && <ErrorState message={err} onRetry={load} />}
      {data && !loading && (
        <div className="grid">
          <StatCard label={t("active_clients")} value={String(data.active_clients)} />
          <StatCard label={t("visits_today")} value={String(data.visits_today)} />
          <StatCard
            label={t("ending_soon")}
            value={String(data.subscriptions_ending_soon)}
            accent="var(--warning)"
          />
          <StatCard
            label={t("clients_with_debt")}
            value={String(data.clients_with_debt)}
          />
          <StatCard
            label={t("income")}
            value={formatMoney(data.income_in_period, lang)}
            accent="var(--success)"
          />
          <StatCard
            label={t("total_debt")}
            value={formatMoney(data.total_debt, lang)}
            accent="var(--danger)"
          />
        </div>
      )}
    </div>
  );
}
