/**
 * Credit Engine — pure logic for the closed-loop credit builder line.
 *
 * No I/O here: everything takes plain data and returns plain data so it can
 * run in route handlers, cron jobs, demo mode and tests alike. Money is
 * integer cents; every price/limit/rate comes from @/lib/pricing.
 *
 * Payment model: each statement's minimum due is its full statement balance
 * (pay-in-full, no interest). A payment made after a statement was issued
 * counts toward that statement, so a statement is satisfied once the
 * payments received after its period end reach its minimum due. Because each
 * new statement's balance carries any unpaid prior balance, one payment can
 * satisfy several statements (the older ones as late).
 */
import { formatCents } from "@/lib/money";
import { CREDIT, REFERRAL, splitMembershipPayment } from "@/lib/pricing";
import type { AffiliateOffer, CreditLine, CreditStatement } from "@/lib/types";

/** Days between statement close and due date. The CARD Act floor is 21; we give more. */
export const STATEMENT_DUE_DAYS = 25;

const DAY_MS = 86_400_000;

/* ------------------------------------------------------------------ */
/* Dates                                                               */
/* ------------------------------------------------------------------ */

export function toDate(value: string | Date): Date {
  return value instanceof Date ? value : new Date(value);
}

/** UTC midnight of the given instant's calendar date. */
export function utcDay(value: string | Date): number {
  const d = toDate(value);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
}

/** Whole calendar days from a to b (negative if b is earlier). */
export function daysBetween(a: string | Date, b: string | Date): number {
  return Math.round((utcDay(b) - utcDay(a)) / DAY_MS);
}

export function isoDate(value: string | Date): string {
  return new Date(utcDay(value)).toISOString().slice(0, 10);
}

/** Add calendar months, clamping to the last day of shorter months (Jan 31 + 1 → Feb 28). */
export function addMonths(value: string | Date, months: number): Date {
  const d = toDate(value);
  const y = d.getUTCFullYear();
  const m = d.getUTCMonth() + months;
  const lastDay = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  return new Date(Date.UTC(y, m, Math.min(d.getUTCDate(), lastDay)));
}

export function addDays(value: string | Date, days: number): Date {
  return new Date(utcDay(value) + days * DAY_MS);
}

/** "YYYY-MM" (UTC). */
export function monthKeyOf(value: string | Date): string {
  return isoDate(value).slice(0, 7);
}

/* ------------------------------------------------------------------ */
/* Statements                                                          */
/* ------------------------------------------------------------------ */

/** "adjustment" is a credit adjustment (lowers the balance), like a refund. */
export type CreditTransactionKind = "purchase" | "membership_fee" | "addon_fee" | "payment" | "refund" | "adjustment";

export interface LineActivity {
  kind: CreditTransactionKind;
  /** Always positive; `kind` gives the direction. */
  amountCents: number;
  occurredAt: string;
}

/** A statement as stored: CreditStatement plus how its balance was built. */
export interface StatementRecord extends CreditStatement {
  previousBalanceCents: number;
  purchasesCents: number;
  membershipFeeCents: number;
  paymentsCents: number;
  creditsCents: number;
}

export interface MembershipState {
  status: "active" | "canceled";
  freeMonthsRemaining: number;
}

export interface GeneratedStatement {
  statement: Omit<StatementRecord, "id">;
  /** The membership fee posted to the line at period close (null when waived or not a member). */
  membershipCharge: { amountCents: number; description: string } | null;
  membershipWaived: boolean;
  freeMonthsRemaining: number;
  /** Line balance after the statement closes. */
  closingBalanceCents: number;
}

/** The statement period that follows `lastPeriodEnd` (or the first one after opening). */
export function nextStatementPeriod(openedAt: string | Date, lastPeriodEnd: string | Date | null): { periodStart: Date; periodEnd: Date } {
  const periodStart = lastPeriodEnd ? addDays(lastPeriodEnd, 1) : new Date(utcDay(openedAt));
  return { periodStart, periodEnd: addDays(addMonths(periodStart, 1), -1) };
}

/**
 * Close a monthly statement: charge the membership fee to the line (unless a
 * referral free month covers it or the membership is canceled), total the
 * period's activity, and set minimum due = statement balance.
 */
export function generateMonthlyStatement(input: {
  creditLineId: string;
  periodStart: string | Date;
  periodEnd: string | Date;
  previousBalanceCents: number;
  activity: readonly LineActivity[];
  membership: MembershipState;
}): GeneratedStatement {
  const start = utcDay(input.periodStart);
  const end = utcDay(input.periodEnd);
  if (end < start) throw new Error("Statement period ends before it starts");

  let purchases = 0;
  let payments = 0;
  let credits = 0;
  for (const a of input.activity) {
    if (!(a.amountCents > 0) || !Number.isInteger(a.amountCents)) throw new Error("Activity amounts must be positive integer cents");
    const day = utcDay(a.occurredAt);
    if (day < start || day > end) continue;
    if (a.kind === "purchase" || a.kind === "membership_fee" || a.kind === "addon_fee") purchases += a.amountCents;
    else if (a.kind === "payment") payments += a.amountCents;
    else credits += a.amountCents;
  }

  const member = input.membership.status === "active";
  const waived = member && input.membership.freeMonthsRemaining > 0;
  const fee = member && !waived ? CREDIT.membershipFeeCents : 0;
  const balance = Math.max(0, input.previousBalanceCents + purchases + fee - payments - credits);

  return {
    statement: {
      creditLineId: input.creditLineId,
      periodStart: isoDate(input.periodStart),
      periodEnd: isoDate(input.periodEnd),
      previousBalanceCents: input.previousBalanceCents,
      purchasesCents: purchases,
      membershipFeeCents: fee,
      paymentsCents: payments,
      creditsCents: credits,
      statementBalanceCents: balance,
      minimumDueCents: balance,
      dueDate: isoDate(addDays(input.periodEnd, STATEMENT_DUE_DAYS)),
      paidAt: null,
      paidOnTime: null,
      daysPastDue: 0,
    },
    membershipCharge: fee > 0 ? { amountCents: fee, description: "EzWerkz membership" } : null,
    membershipWaived: waived,
    freeMonthsRemaining: waived ? input.membership.freeMonthsRemaining - 1 : input.membership.freeMonthsRemaining,
    closingBalanceCents: balance,
  };
}

/* ------------------------------------------------------------------ */
/* Payments                                                            */
/* ------------------------------------------------------------------ */

export type PaymentMethod = "card" | "ach" | "wallet";

export interface PaymentRecord {
  id: string;
  amountCents: number;
  paidAt: string;
  method: PaymentMethod;
  /** Only succeeded payments count. ACH in flight is "pending". */
  status: "succeeded" | "pending" | "failed";
}

export type StatementStatus = "paid_on_time" | "paid_late" | "due" | "past_due" | "no_payment_due";

export interface StatementView extends StatementRecord {
  amountPaidCents: number;
  remainingDueCents: number;
  status: StatementStatus;
}

/** Days past due for one statement as of a date (0 once satisfied or before the due date). */
export function daysPastDue(statement: Pick<CreditStatement, "dueDate">, satisfiedAt: string | null, asOf: string | Date): number {
  if (satisfiedAt && utcDay(satisfiedAt) <= utcDay(asOf)) return 0;
  return Math.max(0, daysBetween(statement.dueDate, asOf));
}

/**
 * Derive paid/late/past-due state for every statement from the payment list.
 * Payments after `asOf` are ignored, so this also answers "what did the
 * account look like at the end of month X" for Metro 2 history.
 */
export function evaluateStatements(
  statements: readonly StatementRecord[],
  payments: readonly PaymentRecord[],
  asOf: string | Date,
): StatementView[] {
  const asOfDay = utcDay(asOf);
  const settled = payments
    .filter((p) => p.status === "succeeded" && utcDay(p.paidAt) <= asOfDay)
    .sort((a, b) => toDate(a.paidAt).getTime() - toDate(b.paidAt).getTime());

  return [...statements]
    .sort((a, b) => utcDay(a.periodEnd) - utcDay(b.periodEnd))
    .map((s) => {
      const issued = utcDay(s.periodEnd);
      if (s.minimumDueCents <= 0) {
        return { ...s, paidAt: null, paidOnTime: null, daysPastDue: 0, amountPaidCents: 0, remainingDueCents: 0, status: "no_payment_due" as const };
      }
      let paid = 0;
      let satisfiedAt: string | null = null;
      for (const p of settled) {
        // A payment on the closing day already shows on the statement itself.
        if (utcDay(p.paidAt) <= issued) continue;
        paid += p.amountCents;
        if (paid >= s.minimumDueCents) {
          satisfiedAt = p.paidAt;
          break;
        }
      }
      const amountPaid = Math.min(paid, s.minimumDueCents);
      const onTime = satisfiedAt ? utcDay(satisfiedAt) <= utcDay(s.dueDate) : null;
      const dpd = daysPastDue(s, satisfiedAt, asOf);
      const status: StatementStatus = satisfiedAt
        ? onTime
          ? "paid_on_time"
          : "paid_late"
        : utcDay(s.dueDate) < asOfDay
          ? "past_due"
          : "due";
      return {
        ...s,
        paidAt: satisfiedAt,
        paidOnTime: onTime,
        daysPastDue: dpd,
        amountPaidCents: amountPaid,
        remainingDueCents: s.minimumDueCents - amountPaid,
        status,
      };
    });
}

export interface PaymentApplication {
  payment: PaymentRecord;
  statements: StatementView[];
  /** Statements this payment brought to satisfied. */
  newlySatisfied: StatementView[];
  lineBalanceCents: number;
}

/**
 * Apply a payment: validates the amount against the line balance, then
 * re-evaluates every statement with the payment included.
 */
export function applyPayment(input: {
  line: Pick<CreditLine, "balanceCents">;
  statements: readonly StatementRecord[];
  payments: readonly PaymentRecord[];
  payment: PaymentRecord;
}): PaymentApplication {
  const { payment } = input;
  if (!Number.isInteger(payment.amountCents) || payment.amountCents <= 0) throw new PaymentError("INVALID_AMOUNT", "Payment must be a positive amount");
  if (payment.amountCents > input.line.balanceCents) throw new PaymentError("OVERPAYMENT", "Payment is more than your balance");
  const before = evaluateStatements(input.statements, input.payments, payment.paidAt);
  const after = evaluateStatements(input.statements, [...input.payments, payment], payment.paidAt);
  const wasSatisfied = new Set(before.filter((s) => s.paidAt).map((s) => s.id));
  return {
    payment,
    statements: after,
    newlySatisfied: payment.status === "succeeded" ? after.filter((s) => s.paidAt && !wasSatisfied.has(s.id)) : [],
    lineBalanceCents: payment.status === "succeeded" ? input.line.balanceCents - payment.amountCents : input.line.balanceCents,
  };
}

export class PaymentError extends Error {
  constructor(
    public readonly code: "INVALID_AMOUNT" | "OVERPAYMENT" | "ALREADY_PAID" | "NOT_FOUND",
    message: string,
  ) {
    super(message);
    this.name = "PaymentError";
  }
}

/** The statement a member should pay next: the newest one with money still due. */
export function currentStatement(views: readonly StatementView[]): StatementView | null {
  for (let i = views.length - 1; i >= 0; i--) {
    const s = views[i]!;
    if (s.remainingDueCents > 0) return s;
  }
  return null;
}

/** Worst days-past-due across all statements as of a date. */
export function accountDaysPastDue(statements: readonly StatementRecord[], payments: readonly PaymentRecord[], asOf: string | Date): number {
  return evaluateStatements(statements, payments, asOf).reduce((max, s) => Math.max(max, s.daysPastDue), 0);
}

/* ------------------------------------------------------------------ */
/* Streaks, level-up, badges                                           */
/* ------------------------------------------------------------------ */

/** Statements whose outcome is known: paid (on time or late) or past due. */
function decided(views: readonly StatementView[]): StatementView[] {
  return views.filter((s) => s.status === "paid_on_time" || s.status === "paid_late" || s.status === "past_due");
}

export interface StreakSummary {
  current: number;
  best: number;
  totalOnTime: number;
}

/**
 * Consecutive on-time statements, newest first. Statements not yet due and
 * zero-balance months neither extend nor break a streak.
 */
export function onTimeStreak(views: readonly StatementView[]): StreakSummary {
  const list = decided(views);
  let current = 0;
  for (let i = list.length - 1; i >= 0; i--) {
    if (list[i]!.status !== "paid_on_time") break;
    current++;
  }
  let best = 0;
  let run = 0;
  let total = 0;
  for (const s of list) {
    if (s.status === "paid_on_time") {
      run++;
      total++;
      best = Math.max(best, run);
    } else run = 0;
  }
  return { current, best, totalOnTime: total };
}

export interface LevelUpProgress {
  eligible: boolean;
  leveledUp: boolean;
  onTimeMonths: number;
  requiredMonths: number;
  remainingMonths: number;
  currentLimitCents: number;
  nextLimitCents: number;
}

/** Level-up: CREDIT.levelUpAfterOnTimeMonths consecutive on-time statements raise the real limit. */
export function levelUpProgress(line: Pick<CreditLine, "limitCents" | "status">, views: readonly StatementView[]): LevelUpProgress {
  const required = CREDIT.levelUpAfterOnTimeMonths;
  const leveledUp = line.limitCents >= CREDIT.levelUpLimitCents;
  const streak = onTimeStreak(views).current;
  const pastDue = views.some((s) => s.status === "past_due");
  const onTime = Math.min(streak, required);
  return {
    eligible: !leveledUp && line.status === "open" && !pastDue && streak >= required,
    leveledUp,
    onTimeMonths: leveledUp ? required : onTime,
    requiredMonths: required,
    remainingMonths: leveledUp ? 0 : Math.max(0, required - streak),
    currentLimitCents: line.limitCents,
    nextLimitCents: CREDIT.levelUpLimitCents,
  };
}

export type BadgeKey = "first_on_time_payment" | "streak_3" | "streak_6" | "level_up";

export interface BadgeDefinition {
  key: BadgeKey;
  title: string;
  description: string;
  howToEarn: string;
}

export const BADGES: Record<BadgeKey, BadgeDefinition> = {
  first_on_time_payment: {
    key: "first_on_time_payment",
    title: "First on-time payment",
    description: "You paid your first statement on time. Great start!",
    howToEarn: "Pay a statement by its due date.",
  },
  streak_3: {
    key: "streak_3",
    title: `${CREDIT.levelUpAfterOnTimeMonths}-month streak`,
    description: `${CREDIT.levelUpAfterOnTimeMonths} on-time payments in a row.`,
    howToEarn: `Pay ${CREDIT.levelUpAfterOnTimeMonths} statements on time in a row.`,
  },
  streak_6: {
    key: "streak_6",
    title: `${CREDIT.streakBadgeMonths}-month streak`,
    description: `${CREDIT.streakBadgeMonths} on-time payments in a row. Seriously consistent.`,
    howToEarn: `Pay ${CREDIT.streakBadgeMonths} statements on time in a row.`,
  },
  level_up: {
    key: "level_up",
    title: "Level up",
    description: "Your credit line limit grew.",
    howToEarn: `Pay ${CREDIT.levelUpAfterOnTimeMonths} statements on time in a row to unlock a higher limit.`,
  },
};

export const BADGE_ORDER: BadgeKey[] = ["first_on_time_payment", "streak_3", "streak_6", "level_up"];

/** Every badge the member's history qualifies for. Badges are never taken away. */
export function qualifyingBadges(state: { streak: StreakSummary; leveledUp: boolean }): BadgeKey[] {
  const out: BadgeKey[] = [];
  if (state.streak.totalOnTime >= 1) out.push("first_on_time_payment");
  if (state.streak.best >= CREDIT.levelUpAfterOnTimeMonths) out.push("streak_3");
  if (state.streak.best >= CREDIT.streakBadgeMonths) out.push("streak_6");
  if (state.leveledUp) out.push("level_up");
  return out;
}

/** Badges to award now (qualifying minus already held). */
export function badgesToAward(existing: readonly BadgeKey[], state: { streak: StreakSummary; leveledUp: boolean }): BadgeKey[] {
  const held = new Set(existing);
  return qualifyingBadges(state).filter((b) => !held.has(b));
}

/** The next streak badge and how many on-time months it needs. */
export function nextStreakMilestone(streak: StreakSummary, held: readonly BadgeKey[]): { badge: BadgeKey; monthsToGo: number } | null {
  const milestones: Array<[BadgeKey, number]> = [
    ["first_on_time_payment", 1],
    ["streak_3", CREDIT.levelUpAfterOnTimeMonths],
    ["streak_6", CREDIT.streakBadgeMonths],
  ];
  for (const [badge, months] of milestones) {
    if (!held.includes(badge)) return { badge, monthsToGo: Math.max(1, months - streak.current) };
  }
  return null;
}

/* ------------------------------------------------------------------ */
/* Utilization and history                                             */
/* ------------------------------------------------------------------ */

/** Balance ÷ limit, clamped to 0…1. */
export function utilization(balanceCents: number, limitCents: number): number {
  if (limitCents <= 0) return 0;
  return Math.min(1, Math.max(0, balanceCents / limitCents));
}

export function availableCredit(line: Pick<CreditLine, "limitCents" | "balanceCents">): number {
  return Math.max(0, line.limitCents - line.balanceCents);
}

export type HistoryDotState = "on_time" | "late" | "missed" | "due" | "no_payment_due" | "none" | "not_open";

export interface HistoryMonth {
  month: string; // YYYY-MM
  state: HistoryDotState;
  statementId: string | null;
}

/** 24 months, oldest first, ending with the month of `asOf`, keyed by statement close month. */
export function paymentHistoryMonths(views: readonly StatementView[], openedAt: string | Date, asOf: string | Date, months = 24): HistoryMonth[] {
  const byMonth = new Map<string, StatementView>();
  for (const s of views) byMonth.set(monthKeyOf(s.periodEnd), s);
  const opened = monthKeyOf(openedAt);
  const out: HistoryMonth[] = [];
  for (let i = months - 1; i >= 0; i--) {
    const key = monthKeyOf(addMonths(new Date(Date.UTC(toDate(asOf).getUTCFullYear(), toDate(asOf).getUTCMonth(), 1)), -i));
    const s = byMonth.get(key);
    let state: HistoryDotState;
    if (!s) state = key < opened ? "not_open" : "none";
    else if (s.status === "paid_on_time") state = "on_time";
    else if (s.status === "paid_late") state = "late";
    else if (s.status === "past_due") state = "missed";
    else if (s.status === "due") state = "due";
    else state = "no_payment_due";
    out.push({ month: key, state, statementId: s?.id ?? null });
  }
  return out;
}

/* ------------------------------------------------------------------ */
/* Referrals and membership money                                      */
/* ------------------------------------------------------------------ */

export interface ReferralRecord {
  id: string;
  referrerId: string;
  referredId: string;
  referredName: string;
  status: "pending" | "qualified";
  qualifiedAt: string | null;
  rewardMonths: number;
}

/**
 * A referral qualifies when the referred member makes their first on-time
 * payment; the referrer then earns REFERRAL.rewardMonths free months.
 */
export function qualifyReferral(
  referral: ReferralRecord,
  referredViews: readonly StatementView[],
): { referral: ReferralRecord; rewardMonths: number } {
  if (referral.status === "qualified" || referral.referrerId === referral.referredId) return { referral, rewardMonths: 0 };
  const first = referredViews.find((s) => s.status === "paid_on_time");
  if (!first || !first.paidAt) return { referral, rewardMonths: 0 };
  return {
    referral: { ...referral, status: "qualified", qualifiedAt: first.paidAt, rewardMonths: REFERRAL.rewardMonths },
    rewardMonths: REFERRAL.rewardMonths,
  };
}

export type TreasuryBucket = "reporting_vendor" | "impact" | "platform";

export interface TreasuryAllocation {
  bucket: TreasuryBucket;
  amountCents: number;
}

/** Split of a membership payment; zero buckets are omitted, the rows always sum to the amount. */
export function membershipTreasuryAllocations(amountCents: number): TreasuryAllocation[] {
  if (!Number.isInteger(amountCents) || amountCents < 0) throw new Error("Membership amount must be non-negative integer cents");
  const split = splitMembershipPayment(amountCents);
  const rows: TreasuryAllocation[] = [
    { bucket: "reporting_vendor", amountCents: split.reportingVendorCents },
    { bucket: "impact", amountCents: split.impactCents },
    { bucket: "platform", amountCents: split.platformCents },
  ];
  return rows.filter((r) => r.amountCents > 0);
}

/**
 * Treasury rows for the membership fees a payment just paid off. Only each
 * statement's own fee is split — store purchases repaid are not membership
 * revenue — and carried balances are never double-counted.
 */
export function treasuryForSatisfiedStatements(newlySatisfied: readonly StatementView[]): Array<TreasuryAllocation & { statementId: string }> {
  return newlySatisfied.flatMap((s) => membershipTreasuryAllocations(s.membershipFeeCents).map((r) => ({ ...r, statementId: s.id })));
}

/* ------------------------------------------------------------------ */
/* Store                                                               */
/* ------------------------------------------------------------------ */

export type PurchaseRejection = "LINE_NOT_OPEN" | "MEMBERSHIP_INACTIVE" | "INSUFFICIENT_CREDIT" | "PAST_DUE" | "INVALID_PRICE";

/** Whether a store purchase can be charged to the line. Purchases can never exceed available credit. */
export function canPurchase(input: {
  line: Pick<CreditLine, "limitCents" | "balanceCents" | "status">;
  membership: MembershipState;
  priceCents: number;
  hasPastDue: boolean;
}): { ok: true; balanceAfterCents: number; availableAfterCents: number } | { ok: false; reason: PurchaseRejection } {
  if (!Number.isInteger(input.priceCents) || input.priceCents <= 0) return { ok: false, reason: "INVALID_PRICE" };
  if (input.line.status !== "open") return { ok: false, reason: "LINE_NOT_OPEN" };
  if (input.membership.status !== "active") return { ok: false, reason: "MEMBERSHIP_INACTIVE" };
  if (input.hasPastDue) return { ok: false, reason: "PAST_DUE" };
  if (input.priceCents > availableCredit(input.line)) return { ok: false, reason: "INSUFFICIENT_CREDIT" };
  const balanceAfter = input.line.balanceCents + input.priceCents;
  return { ok: true, balanceAfterCents: balanceAfter, availableAfterCents: input.line.limitCents - balanceAfter };
}

/* ------------------------------------------------------------------ */
/* Affiliate offers (660+ widget)                                      */
/* ------------------------------------------------------------------ */

export interface RankedOffer extends AffiliateOffer {
  rank: number;
  reasons: string[];
}

/**
 * Rank offers by fit for this score: only offers whose minimum score the
 * member meets, then lowest annual fee, then most highlights. `bountyCents`
 * (what EzWerkz may earn) is deliberately never read here.
 */
export function rankAffiliateOffers(offers: readonly AffiliateOffer[], score: number): { eligible: RankedOffer[]; notYet: AffiliateOffer[] } {
  const eligible = offers.filter((o) => o.minScore <= score);
  const notYet = offers.filter((o) => o.minScore > score).sort((a, b) => a.minScore - b.minScore);
  const ranked = [...eligible]
    .sort(
      (a, b) =>
        a.annualFeeCents - b.annualFeeCents ||
        b.highlights.length - a.highlights.length ||
        a.issuer.localeCompare(b.issuer) ||
        a.productName.localeCompare(b.productName),
    )
    .map((o, i) => ({
      ...o,
      rank: i + 1,
      reasons: [
        `Your score (${score}) meets the issuer's typical ${o.minScore}+ range`,
        o.annualFeeCents === 0 ? "No annual fee" : `${formatCents(o.annualFeeCents)} annual fee (lower fees rank higher)`,
        `${o.highlights.length} key feature${o.highlights.length === 1 ? "" : "s"}`,
      ],
    }));
  return { eligible: ranked, notYet };
}
