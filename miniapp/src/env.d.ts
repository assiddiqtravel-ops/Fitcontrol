/// <reference types="vite/client" />

interface TelegramWebApp {
  initData: string;
  initDataUnsafe: { user?: { id: number; language_code?: string } };
  ready: () => void;
  expand: () => void;
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  showConfirm?: (message: string, cb: (ok: boolean) => void) => void;
}

interface Window {
  Telegram?: { WebApp?: TelegramWebApp };
}

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  readonly VITE_DEV_TELEGRAM_ID?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
