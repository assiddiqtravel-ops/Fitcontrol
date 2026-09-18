import { useEffect, useState } from "react";
import { api } from "../api";
import { formatDate } from "../format";
import { useI18n } from "../i18n";
import { atLeast, useApp } from "../state";
import { Badge, Card, EmptyState, ErrorState, Field, Loading, Modal } from "../ui";
import type { Club, Invite, Role, Staff } from "../types";

export default function Settings() {
  const { t, lang } = useI18n();
  const { activeClub, role, reload } = useApp();
  const [club, setClub] = useState<Club | null>(activeClub?.club ?? null);
  const [staff, setStaff] = useState<Staff[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showInvite, setShowInvite] = useState(false);
  const isOwner = atLeast(role, "club_owner");
  const isAdmin = atLeast(role, "club_admin");

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const c = await api<Club>("/clubs/current");
      setClub(c);
      if (isAdmin) setStaff(await api<Staff[]>("/staff"));
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

  async function toggleNotify(field: keyof Club, value: boolean) {
    if (!isOwner || !club) return;
    setClub({ ...club, [field]: value });
    await api<Club>("/settings", { method: "PATCH", body: { [field]: value } });
  }

  async function toggleStaff(m: Staff) {
    await api<Staff>(`/staff/${m.membership_id}`, {
      method: "PATCH",
      body: { is_active: !m.is_active },
    });
    load();
  }

  if (loading) return <Loading />;
  if (err) return <ErrorState message={err} onRetry={load} />;

  return (
    <div>
      <h2>{t("nav_settings")}</h2>

      <Card>
        <h3>{club?.name}</h3>
        <div className="muted small" style={{ marginTop: 4 }}>
          {club?.timezone} · {club?.currency}
        </div>
      </Card>

      <h3 style={{ margin: "16px 0 8px" }}>{t("notifications")}</h3>
      <Card>
        <ToggleRow
          label={t("notify_expiry")}
          value={!!club?.notify_expiry_enabled}
          disabled={!isOwner}
          onChange={(v) => toggleNotify("notify_expiry_enabled", v)}
        />
        <ToggleRow
          label={t("notify_overdue")}
          value={!!club?.notify_overdue_enabled}
          disabled={!isOwner}
          onChange={(v) => toggleNotify("notify_overdue_enabled", v)}
        />
        <ToggleRow
          label={t("notify_daily")}
          value={!!club?.notify_daily_summary_enabled}
          disabled={!isOwner}
          onChange={(v) => toggleNotify("notify_daily_summary_enabled", v)}
        />
      </Card>

      {isAdmin && (
        <>
          <div className="row" style={{ marginTop: 16 }}>
            <h3>{t("staff")}</h3>
            <button className="btn" onClick={() => setShowInvite(true)}>
              + {t("invite_staff")}
            </button>
          </div>
          <Card>
            {staff && staff.length === 0 && <EmptyState />}
            {staff?.map((m) => (
              <div className="row" key={m.membership_id}>
                <div>
                  <div>
                    {m.user.first_name ?? ""} {m.user.last_name ?? ""}{" "}
                    <span className="muted small">#{m.user.telegram_id}</span>
                  </div>
                  <Badge text={t(`role_${m.role}`)} tone="neutral" />
                  {!m.is_active && <Badge text={t("disable")} tone="danger" />}
                </div>
                {isOwner && m.role !== "club_owner" && (
                  <button className="btn btn-secondary" onClick={() => toggleStaff(m)}>
                    {m.is_active ? t("disable") : t("enable")}
                  </button>
                )}
              </div>
            ))}
          </Card>
        </>
      )}

      <div className="muted small" style={{ marginTop: 24 }}>
        {t("language")}: RU / UZ — {formatDate(club?.created_at, lang)}
      </div>

      {showInvite && (
        <InviteModal
          onClose={() => setShowInvite(false)}
          onDone={() => {
            setShowInvite(false);
            reload();
            load();
          }}
        />
      )}
    </div>
  );
}

function ToggleRow({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="row">
      <span>{label}</span>
      <input
        type="checkbox"
        style={{ width: 20, height: 20 }}
        checked={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
    </div>
  );
}

function InviteModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useI18n();
  const [role, setRole] = useState<Role>("trainer");
  const [tgId, setTgId] = useState("");
  const [created, setCreated] = useState<Invite | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      const body: any = { role, ttl_hours: 72 };
      if (tgId) body.telegram_id = Number(tgId);
      const inv = await api<Invite>("/staff/invites", { method: "POST", body });
      setCreated(inv);
    } catch (e: any) {
      setErr(e?.message ?? t("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={t("invite_staff")} onClose={created ? onDone : onClose}>
      {err && <div className="field-error">{err}</div>}
      {created ? (
        <div>
          <p>{t("invite_code")}:</p>
          <h2 style={{ letterSpacing: 2 }}>{created.code}</h2>
          <p className="muted small">
            {t("role")}: {t(`role_${created.role}`)}
          </p>
          <button className="btn btn-block" onClick={onDone}>
            {t("save")}
          </button>
        </div>
      ) : (
        <>
          <Field label={t("role")}>
            <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
              <option value="trainer">{t("role_trainer")}</option>
              <option value="club_admin">{t("role_club_admin")}</option>
            </select>
          </Field>
          <Field label="Telegram ID (?)">
            <input
              type="number"
              placeholder="123456789"
              value={tgId}
              onChange={(e) => setTgId(e.target.value)}
            />
          </Field>
          <button className="btn btn-block" disabled={busy} onClick={submit}>
            {t("create")}
          </button>
        </>
      )}
    </Modal>
  );
}
