import type { Lang } from "./i18n";

// Money is integer UZS from the backend. Localized formatting with grouped
// thousands. UZS has no sub-unit, so no decimals.
export function formatMoney(amount: number, lang: Lang): string {
  const grouped = new Intl.NumberFormat(lang === "uz" ? "uz-UZ" : "ru-RU").format(
    Math.abs(Math.round(amount))
  );
  const sign = amount < 0 ? "-" : "";
  const suffix = lang === "uz" ? "so'm" : "UZS";
  return `${sign}${grouped} ${suffix}`;
}

export function formatDate(iso: string | undefined | null, lang: Lang): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(lang === "uz" ? "uz-UZ" : "ru-RU", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(d);
}
