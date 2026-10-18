/**
 * The Credit Builder view model. Demo and live mode both load raw records
 * into `CreditData`; `buildCreditSummary` derives everything the UI shows,
 * so the two modes can never disagree about streaks, statuses or offers.
 */
import { ADDONS, CREDIT } from "@/lib/pricing";
import type { AffiliateOffer, CreditLine } from "@/lib/types";
import {
  BADGE_ORDER,
  BADGES,
  availableCredit,
  currentStatement,
  evaluateStatements,
  levelUpProgress,
  nextStatementPeriod,
  nextStreakMilestone,
  onTimeStreak,
  paymentHistoryMonths,
  rankAffiliateOffers,
  utcDay,
  utilization,
  type BadgeDefinition,
  type BadgeKey,
  type CreditTransactionKind,
  type HistoryMonth,
  type LevelUpProgress,
  type PaymentRecord,
  type RankedOffer,
  type ReferralRecord,
  type StatementRecord,
  type StatementView,
  type StreakSummary,
} from "./engine";

export type AddonKey = (typeof ADDONS)[keyof typeof ADDONS]["key"];

export const ADDON_LIST = Object.values(ADDONS);

export const ADDON_DESCRIPTIONS: Record<AddonKey, string> = {
  rent_reporting: "Add your on-time rent and utility payments to your credit file through our reporting partner.",
  ai_coach: "Weekly check-ins and a plan for your budget, bills and savings goals.",
};

export function isAddonKey(value: string): value is AddonKey {
  return ADDON_LIST.some((a) => a.key === value);
}

export interface CreditLineRecord extends CreditLine {
  accountNumber: string;
  closedAt: string | null;
  closedAtConsumerRequest: boolean;
}

export interface MembershipRecord {
  status: "active" | "canceled";
  freeMonthsRemaining: number;
  startedAt: string;
  canceledAt: string | null;
}

export interface CreditTransactionRecord {
  id: string;
  kind: CreditTransactionKind;
  amountCents: number;
  description: string;
  occurredAt: string;
}

export interface ScoreSnapshot {
  score: number;
  pulledAt: string;
  source: string;
}

export interface AddonRecord {
  key: AddonKey;
  status: "active" | "canceled";
  startedAt: string;
  canceledAt: string | null;
}

export interface CreditData {
  line: CreditLineRecord | null;
  membership: MembershipRecord | null;
  statements: StatementRecord[];
  payments: PaymentRecord[];
  transactions: CreditTransactionRecord[];
  scores: ScoreSnapshot[];
  softPullConsentAt: string | null;
  badges: Array<{ key: BadgeKey; awardedAt: string }>;
  referralCode: string | null;
  referrals: ReferralRecord[];
  addons: AddonRecord[];
  offers: AffiliateOffer[];
}

export interface CurrentStatementView extends StatementView {
  /** ACH or card payments still settling. */
  pendingCents: number;
}

export interface AddonView {
  key: AddonKey;
  name: string;
  priceCents: number;
  description: string;
  active: boolean;
  startedAt: string | null;
}

export interface CreditSummary {
  enrolled: boolean;
  line: CreditLineRecord | null;
  accountLast4: string | null;
  availableCents: number;
  utilization: number;
  membership: MembershipRecord | null;
  statements: StatementView[];
  current: CurrentStatementView | null;
  nextStatementDate: string | null;
  history: HistoryMonth[];
  streak: StreakSummary;
  nextMilestone: { badge: BadgeDefinition; monthsToGo: number } | null;
  levelUp: LevelUpProgress | null;
  hasPastDue: boolean;
  score: ScoreSnapshot | null;
  scoreHistory: ScoreSnapshot[];
  softPullConsentAt: string | null;
  offers: { unlocked: boolean; threshold: number; eligible: RankedOffer[]; notYet: AffiliateOffer[] };
  badges: Array<BadgeDefinition & { earnedAt: string | null }>;
  referral: { code: string | null; referrals: ReferralRecord[]; earnedMonths: number; freeMonthsRemaining: number };
  addons: AddonView[];
  recentTransactions: CreditTransactionRecord[];
}

export function referralLink(appUrl: string, code: string): string {
  return `${appUrl.replace(/\/$/, "")}/login?ref=${encodeURIComponent(code)}`;
}

export function buildCreditSummary(data: CreditData, now: Date = new Date()): CreditSummary {
  const views = data.line ? evaluateStatements(data.statements, data.payments, now) : [];
  const streak = onTimeStreak(views);
  const held = data.badges.map((b) => b.key);
  const milestone = nextStreakMilestone(streak, held);
  const score = [...data.scores].sort((a, b) => utcDay(b.pulledAt) - utcDay(a.pulledAt))[0] ?? null;
  const ranked = score ? rankAffiliateOffers(data.offers, score.score) : { eligible: [], notYet: data.offers };
  const unlocked = Boolean(score && score.score >= CREDIT.affiliateScoreThreshold);

  const current = currentStatement(views);
  const pendingCents = current
    ? data.payments
        .filter((p) => p.status === "pending" && utcDay(p.paidAt) > utcDay(current.periodEnd))
        .reduce((n, p) => n + p.amountCents, 0)
    : 0;

  const lastClose = views.length ? views[views.length - 1]!.periodEnd : null;
  const nextStatementDate =
    data.line && data.line.status === "open" ? nextStatementPeriod(data.line.openedAt, lastClose).periodEnd.toISOString().slice(0, 10) : null;

  const badgeEarned = new Map(data.badges.map((b) => [b.key, b.awardedAt]));

  return {
    enrolled: Boolean(data.line),
    line: data.line,
    accountLast4: data.line ? data.line.accountNumber.slice(-4) : null,
    availableCents: data.line ? availableCredit(data.line) : 0,
    utilization: data.line ? utilization(data.line.balanceCents, data.line.limitCents) : 0,
    membership: data.membership,
    statements: [...views].reverse(),
    current: current ? { ...current, pendingCents } : null,
    nextStatementDate,
    history: data.line ? paymentHistoryMonths(views, data.line.openedAt, now) : [],
    streak,
    nextMilestone: milestone ? { badge: BADGES[milestone.badge], monthsToGo: milestone.monthsToGo } : null,
    levelUp: data.line ? levelUpProgress(data.line, views) : null,
    hasPastDue: views.some((v) => v.status === "past_due"),
    score,
    scoreHistory: [...data.scores].sort((a, b) => utcDay(a.pulledAt) - utcDay(b.pulledAt)),
    softPullConsentAt: data.softPullConsentAt,
    offers: { unlocked, threshold: CREDIT.affiliateScoreThreshold, eligible: unlocked ? ranked.eligible : [], notYet: ranked.notYet },
    badges: BADGE_ORDER.map((key) => ({ ...BADGES[key], earnedAt: badgeEarned.get(key) ?? null })),
    referral: {
      code: data.referralCode,
      referrals: data.referrals,
      earnedMonths: data.referrals.reduce((n, r) => n + (r.status === "qualified" ? r.rewardMonths : 0), 0),
      freeMonthsRemaining: data.membership?.freeMonthsRemaining ?? 0,
    },
    addons: ADDON_LIST.map((a) => {
      const rec = data.addons.find((x) => x.key === a.key && x.status === "active");
      return {
        key: a.key,
        name: a.name,
        priceCents: a.priceCents,
        description: ADDON_DESCRIPTIONS[a.key],
        active: Boolean(rec),
        startedAt: rec?.startedAt ?? null,
      };
    }),
    recentTransactions: [...data.transactions].sort((a, b) => b.occurredAt.localeCompare(a.occurredAt)).slice(0, 10),
  };
}

export interface StoreProduct {
  id: string;
  name: string;
  description: string;
  priceCents: number;
  category: "course" | "gear" | "digital";
  fulfillment: "digital" | "shipped";
}
