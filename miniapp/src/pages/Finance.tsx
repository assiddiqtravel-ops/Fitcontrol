import { useEffect, useState } from "react";
import { api } from "../api";
import { formatMoney } from "../format";
import { useI18n } from "../i18n";
import { Card, EmptyState, ErrorState, Loading, StatCard } from "../ui";
import type { DebtRow } from "../types";

interface IncomeByMethod {
  method: string;
  total: number;
  count: number;
}
interface IncomeReport {
  period_start: string;
  period_end: string;
  total_income: number;
  total_refunds: number;
  net_income: number;
  by_method: IncomeByMethod[];
}

type Period = "today" | "7d" | "month";

export default function Finance() {
  const { t, lang } = useI18n();
  const [period, setPeriod] = useState<Period>("month");
  const [report, setReport] = useState<IncomeReport | null>(null);
  const [debts, setDebts] = useState<DebtRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const [r, d] = await Promise.all([
        api<IncomeReport>("/reports/income", { query: { period } }),
        api<DebtRow[]>("/debts"),
      ]);
      setReport(r);
      setDebts(d);
    } catch (e: any) {
      setErr(e?.message ?? t("error"));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  return (
    <div>
      <h2>{t("nav_finance")}</h2>
      <div className="pills">
        {(["today", "7d", "month"] as Period[]).map((p) => (
          <button
            key={p}
            className={`pill ${period === p ? "active" : ""}`}
            onClick={() => setPeriod(p)}
          >
            {t(`period_${p}`)}
          </button>
        ))}
      </div>

      {loading && <Loading />}
      {err && <ErrorState message={err} onRetry={load} />}

      {report && !loading && (
        <>
          <div className="grid">
            <StatCard
              label={t("income")}
              value={formatMoney(report.total_income, lang)}
              accent="var(--success)"
            />
            <StatCard label={t("refunds")} value={formatMoney(report.total_refunds, lang)} />
            <StatCard label={t("net_income")} value={formatMoney(report.net_income, lang)} />
          </div>

          <h3 style={{ margin: "16px 0 8px" }}>{t("method")}</h3>
          <Card>
            {report.by_method.length === 0 && <EmptyState />}
            {report.by_method.map((m) => (
              <div className="row" key={m.method}>
                <span>{t(`method_${m.method}`)}</span>
                <span>
                  {formatMoney(m.total, lang)} <span className="muted small">({m.count})</span>
                </span>
              </div>
            ))}
          </Card>
        </>
      )}

      <h3 style={{ margin: "16px 0 8px" }}>{t("debts")}</h3>
      {debts && (
        <Card>
          {debts.length === 0 && <EmptyState />}
          {debts.map((d) => (
            <div className="row" key={d.client_id}>
              <span>{d.client_name}</span>
              <span style={{ color: "var(--danger)" }}>{formatMoney(d.debt, lang)}</span>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
