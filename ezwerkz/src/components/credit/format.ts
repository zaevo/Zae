const short = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const long = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const monthOnly = new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" });
const monthYear = new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric", timeZone: "UTC" });

function parse(value: string): Date {
  return new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00Z` : value);
}

/** "Nov 9" */
export function formatShortDate(value: string): string {
  return short.format(parse(value));
}

/** "Nov 9, 2026" */
export function formatLongDate(value: string): string {
  return long.format(parse(value));
}

/** "2026-10" → "Oct" */
export function formatMonth(monthKey: string): string {
  return monthOnly.format(parse(`${monthKey}-01`));
}

/** "2026-10" → "October 2026" */
export function formatMonthYear(monthKey: string): string {
  return monthYear.format(parse(`${monthKey}-01`));
}

/** Whole days from today (UTC) until the date; negative when past. */
export function daysUntil(value: string, now: Date = new Date()): number {
  const d = parse(value);
  const a = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const b = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  return Math.round((b - a) / 86_400_000);
}
