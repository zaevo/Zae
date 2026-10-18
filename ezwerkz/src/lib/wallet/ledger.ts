/**
 * Pure ledger helpers. The ledger mirrors the bank partner's balance: entries
 * are append-only, amount_cents is always positive and direction gives the
 * sign. Nothing here touches the network or the database.
 */
import type { LedgerCategory, LedgerEntry } from "@/lib/types";

/** Day grouping happens on the server, so it needs an explicit zone. US product → Eastern by default. */
export const DISPLAY_TIME_ZONE = "America/New_York";

export type LedgerIconKey = "shift" | "membership" | "addon" | "card" | "deposit" | "withdrawal" | "refund";

export interface CategoryMeta {
  label: string;
  icon: LedgerIconKey;
  /** How the entry counts in monthly totals. Withdrawals move the member's own money out, so they are neither. */
  flow: "income" | "spend" | "refund" | "transfer";
}

export const CATEGORY_META: Record<LedgerCategory, CategoryMeta> = {
  shift_earnings: { label: "Shift pay", icon: "shift", flow: "income" },
  deposit: { label: "Deposit", icon: "deposit", flow: "income" },
  membership_fee: { label: "Membership", icon: "membership", flow: "spend" },
  addon_fee: { label: "Add-on", icon: "addon", flow: "spend" },
  card_spend: { label: "Card", icon: "card", flow: "spend" },
  refund: { label: "Refund", icon: "refund", flow: "refund" },
  withdrawal: { label: "Transfer out", icon: "withdrawal", flow: "transfer" },
};

type Entry = Pick<LedgerEntry, "direction" | "amountCents" | "category" | "createdAt">;

export function signedCents(entry: Pick<LedgerEntry, "direction" | "amountCents">): number {
  return entry.direction === "credit" ? entry.amountCents : -entry.amountCents;
}

export function balanceFromEntries(entries: readonly Pick<LedgerEntry, "direction" | "amountCents">[], openingCents = 0): number {
  return entries.reduce((sum, e) => sum + signedCents(e), openingCents);
}

const keyFormatters = new Map<string, Intl.DateTimeFormat>();

/** Calendar day ("YYYY-MM-DD") of an instant in the given zone. */
export function dayKey(at: string | Date, timeZone: string = DISPLAY_TIME_ZONE): string {
  let f = keyFormatters.get(timeZone);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" });
    keyFormatters.set(timeZone, f);
  }
  const parts = f.formatToParts(typeof at === "string" ? new Date(at) : at);
  const get = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

export function monthKey(at: string | Date, timeZone: string = DISPLAY_TIME_ZONE): string {
  return dayKey(at, timeZone).slice(0, 7);
}

/** Calendar arithmetic on a day key, so DST days (23h/25h) never skip or repeat a date. */
export function shiftDayKey(key: string, days: number): string {
  const [y, m, d] = key.split("-").map(Number) as [number, number, number];
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

function dayLabel(key: string, todayKey: string): string {
  if (key === todayKey) return "Today";
  if (key === shiftDayKey(todayKey, -1)) return "Yesterday";
  const [y, m, d] = key.split("-").map(Number) as [number, number, number];
  const noonUtc = new Date(Date.UTC(y, m - 1, d, 12));
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "UTC",
    weekday: "short",
    month: "short",
    day: "numeric",
    ...(key.slice(0, 4) === todayKey.slice(0, 4) ? {} : { year: "numeric" }),
  }).format(noonUtc);
}

export interface DayGroup<T extends Entry = LedgerEntry> {
  key: string;
  label: string;
  entries: T[];
  netCents: number;
}

/** Newest day first; entries newest first within a day. */
export function groupByDay<T extends Entry>(
  entries: readonly T[],
  { now = new Date(), timeZone = DISPLAY_TIME_ZONE }: { now?: Date; timeZone?: string } = {},
): DayGroup<T>[] {
  const todayKey = dayKey(now, timeZone);
  const groups = new Map<string, T[]>();
  const sorted = [...entries].sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
  for (const entry of sorted) {
    const key = dayKey(entry.createdAt, timeZone);
    const list = groups.get(key);
    if (list) list.push(entry);
    else groups.set(key, [entry]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (a < b ? 1 : a > b ? -1 : 0))
    .map(([key, list]) => ({ key, label: dayLabel(key, todayKey), entries: list, netCents: balanceFromEntries(list) }));
}

export interface MonthTotals {
  month: string; // "YYYY-MM"
  incomeCents: number;
  /** Spend net of refunds, never below zero. */
  spendCents: number;
  transfersOutCents: number;
  netCents: number;
}

function emptyTotals(month: string): MonthTotals {
  return { month, incomeCents: 0, spendCents: 0, transfersOutCents: 0, netCents: 0 };
}

function accumulate(totals: MonthTotals, entry: Entry, refundsRef: { cents: number }): void {
  const flow = CATEGORY_META[entry.category].flow;
  totals.netCents += signedCents(entry);
  if (flow === "income" && entry.direction === "credit") totals.incomeCents += entry.amountCents;
  else if (flow === "spend" && entry.direction === "debit") totals.spendCents += entry.amountCents;
  else if (flow === "refund" && entry.direction === "credit") refundsRef.cents += entry.amountCents;
  else if (flow === "transfer" && entry.direction === "debit") totals.transfersOutCents += entry.amountCents;
}

export function totalsForMonth(entries: readonly Entry[], month: string, timeZone: string = DISPLAY_TIME_ZONE): MonthTotals {
  const totals = emptyTotals(month);
  const refunds = { cents: 0 };
  for (const e of entries) if (monthKey(e.createdAt, timeZone) === month) accumulate(totals, e, refunds);
  totals.spendCents = Math.max(0, totals.spendCents - refunds.cents);
  return totals;
}

/** Income vs spend per month that has activity, newest month first. */
export function monthlyTotals(entries: readonly Entry[], timeZone: string = DISPLAY_TIME_ZONE): MonthTotals[] {
  const months = new Set(entries.map((e) => monthKey(e.createdAt, timeZone)));
  return [...months].sort().reverse().map((m) => totalsForMonth(entries, m, timeZone));
}

export interface IncomeBySource {
  shiftEarningsCents: number;
  otherIncomeCents: number;
  totalCents: number;
  shiftCount: number;
}

export function incomeBySource(entries: readonly Entry[], month: string, timeZone: string = DISPLAY_TIME_ZONE): IncomeBySource {
  const out: IncomeBySource = { shiftEarningsCents: 0, otherIncomeCents: 0, totalCents: 0, shiftCount: 0 };
  for (const e of entries) {
    if (e.direction !== "credit" || CATEGORY_META[e.category].flow !== "income") continue;
    if (monthKey(e.createdAt, timeZone) !== month) continue;
    if (e.category === "shift_earnings") {
      out.shiftEarningsCents += e.amountCents;
      out.shiftCount += 1;
    } else {
      out.otherIncomeCents += e.amountCents;
    }
  }
  out.totalCents = out.shiftEarningsCents + out.otherIncomeCents;
  return out;
}

/** Split one shift payout between the Wallet and the worker's other payout destination. */
export function splitShiftPay(payCents: number, allocationPercent: number): { walletCents: number; externalCents: number } {
  if (!Number.isInteger(payCents) || payCents < 0) throw new Error("payCents must be a non-negative integer");
  const pct = Math.min(100, Math.max(0, Math.round(allocationPercent)));
  const walletCents = Math.round((payCents * pct) / 100);
  return { walletCents, externalCents: payCents - walletCents };
}
