import { useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { useApp } from "../state";
import { Card, Field } from "../ui";
import type { Club, Membership } from "../types";

export default function Onboarding() {
  const { t } = useI18n();
  const { reload } = useApp();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function createClub() {
    if (!name.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      await api<Club>("/clubs", { method: "POST", body: { name }, clubScoped: false });
      await reload();
    } catch (e: any) {
      setErr(e?.message ?? t("error"));
    } finally {
      setBusy(false);
    }
  }

  async function acceptInvite() {
    if (!code.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      await api<Membership>("/staff/invites/accept", {
        method: "POST",
        body: { code },
        clubScoped: false,
      });
      await reload();
    } catch (e: any) {
      setErr(e?.message ?? t("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2>{t("welcome")}</h2>
      <p className="muted">{t("onboarding_hint")}</p>
      {err && <div className="field-error">{err}</div>}

      <Card>
        <h3>{t("create_club")}</h3>
        <div style={{ height: 12 }} />
        <Field label={t("club_name")}>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <button className="btn btn-block" disabled={busy || !name.trim()} onClick={createClub}>
          {t("create_club")}
        </button>
      </Card>

      <Card>
        <h3>{t("accept_invite")}</h3>
        <div style={{ height: 12 }} />
        <Field label={t("invite_code")}>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="ABCD1234"
          />
        </Field>
        <button
          className="btn btn-secondary btn-block"
          disabled={busy || !code.trim()}
          onClick={acceptInvite}
        >
          {t("accept_invite")}
        </button>
      </Card>
    </div>
  );
}
