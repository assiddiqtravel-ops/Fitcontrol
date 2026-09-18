// Telegram WebApp integration + auth header resolution.
//
// In production the app runs inside Telegram; we forward the raw `initData`
// string in the X-Init-Data header and the backend validates it. For local
// development outside Telegram, set VITE_DEV_TELEGRAM_ID to exercise the API
// with the backend's DEV_AUTH_MODE (which is disabled in production).

const tg = window.Telegram?.WebApp;

export function initTelegram(): void {
  try {
    tg?.ready();
    tg?.expand();
  } catch {
    /* not inside Telegram */
  }
}

export function getInitData(): string {
  return tg?.initData ?? "";
}

export function getDevTelegramId(): string | null {
  return import.meta.env.VITE_DEV_TELEGRAM_ID ?? null;
}

export function detectLanguage(): "ru" | "uz" {
  const stored = localStorage.getItem("fc_lang");
  if (stored === "ru" || stored === "uz") return stored;
  const code = tg?.initDataUnsafe?.user?.language_code;
  return code === "uz" ? "uz" : "ru";
}

export function authHeaders(): Record<string, string> {
  const initData = getInitData();
  if (initData) return { "X-Init-Data": initData };
  const dev = getDevTelegramId();
  if (dev) return { "X-Dev-Telegram-Id": dev };
  return {};
}

export function confirmDanger(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    if (tg?.showConfirm) {
      tg.showConfirm(message, (ok) => resolve(ok));
    } else {
      resolve(window.confirm(message));
    }
  });
}
