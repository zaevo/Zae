/**
 * Demo fixtures for the Credit Builder (module A).
 *
 * Every demo account gets the same story, generated relative to "now" so it
 * never goes stale: a line opened six statements ago, five statements paid
 * on time (so the limit has leveled up), the newest statement closed
 * yesterday and is due in 24 days, and a 668 soft-pull score — just past the
 * 660 card-matcher threshold. State lives in demoStore so actions taken in
 * the demo (pay, buy, cancel …) persist for the session.
 */
import { CREDIT, ADDONS } from "@/lib/pricing";
import type { AffiliateOffer } from "@/lib/types";
import type { BillAnalysis } from "@/lib/ai/billAnalysis";
import {
  addDays,
  addMonths,
  generateMonthlyStatement,
  type PaymentRecord,
  type ReferralRecord,
  type StatementRecord,
} from "@/lib/credit/engine";
import type { CreditData, CreditTransactionRecord, StoreProduct } from "@/lib/credit/summary";
import { demoStore } from "./store";

export const demoStoreProducts: StoreProduct[] = [
  {
    id: "prod-food-handler",
    name: "Food Handler Certificate course",
    description: "Online, state-accepted course most grocery and c-store shifts ask for. About 2 hours.",
    priceCents: 15_00,
    category: "course",
    fulfillment: "digital",
  },
  {
    id: "prod-forklift-prep",
    name: "Forklift safety prep course",
    description: "OSHA-aligned study course to prepare for an employer's forklift certification.",
    priceCents: 29_00,
    category: "course",
    fulfillment: "digital",
  },
  {
    id: "prod-budget-kit",
    name: "Paycheck budgeting kit",
    description: "Printable planner and spreadsheet built for variable, shift-based income.",
    priceCents: 12_00,
    category: "digital",
    fulfillment: "digital",
  },
  {
    id: "prod-resume-review",
    name: "Résumé review by a career coach",
    description: "Written feedback on your résumé within 3 business days.",
    priceCents: 35_00,
    category: "digital",
    fulfillment: "digital",
  },
  {
    id: "prod-hi-vis-vest",
    name: "High-visibility safety vest",
    description: "ANSI Class 2 reflective vest for lot and warehouse shifts. Ships free.",
    priceCents: 18_00,
    category: "gear",
    fulfillment: "shipped",
  },
  {
    id: "prod-nonslip-shoes",
    name: "Non-slip work shoes",
    description: "Slip-resistant, lightweight shoes for long shifts on hard floors. Ships free.",
    priceCents: 49_00,
    category: "gear",
    fulfillment: "shipped",
  },
];

/** Fictional issuers. Ranking ignores bountyCents; it is shown only as a disclosure. */
export const demoAffiliateOffers: AffiliateOffer[] = [
  {
    id: "offer-northwind-cash",
    issuer: "Northwind Bank",
    productName: "Everyday Cash Card",
    minScore: 640,
    annualFeeCents: 0,
    aprText: "Variable APR 24.49%–30.49%",
    highlights: ["1.5% cash back on everything", "No annual fee", "Free monthly score updates"],
    bountyCents: 60_00,
    url: "https://example.com/offers/northwind-everyday-cash",
  },
  {
    id: "offer-lumen-build",
    issuer: "Lumen Credit Union",
    productName: "Build+ Visa",
    minScore: 620,
    annualFeeCents: 0,
    aprText: "Variable APR 18.00%",
    highlights: ["Lower APR than most starter cards", "No annual fee"],
    bountyCents: 25_00,
    url: "https://example.com/offers/lumen-build-plus",
  },
  {
    id: "offer-harbor-rewards",
    issuer: "Harbor Financial",
    productName: "Harbor Rewards Card",
    minScore: 650,
    annualFeeCents: 39_00,
    aprText: "Variable APR 26.99%",
    highlights: ["3% back on gas and groceries", "1% everywhere else", "Cell phone protection", "No foreign transaction fees"],
    bountyCents: 150_00,
    url: "https://example.com/offers/harbor-rewards",
  },
  {
    id: "offer-cobalt-travel",
    issuer: "Cobalt Card Co.",
    productName: "Cobalt Travel Card",
    minScore: 700,
    annualFeeCents: 95_00,
    aprText: "Variable APR 23.99%–29.99%",
    highlights: ["2x miles on every purchase", "Airport lounge passes"],
    bountyCents: 250_00,
    url: "https://example.com/offers/cobalt-travel",
  },
];

export interface DemoCreditState extends CreditData {
  billAnalyses: BillAnalysis[];
  seq: number;
}

function demoId(prefix: string, n: number): string {
  return `${prefix}-${String(n).padStart(4, "0")}`;
}

function referralCodeFor(fullName: string, userId: string): string {
  const first = (fullName.split(" ")[0] ?? "friend").toUpperCase().replace(/[^A-Z]/g, "").slice(0, 8) || "FRIEND";
  return `${first}-${userId.slice(-4).toUpperCase()}`;
}

/** Build the six-statement history described in the file header. */
export function buildDemoCreditState(user: { id: string; fullName: string }, now: Date = new Date()): DemoCreditState {
  const lastClose = addDays(now, -1);
  const closes = Array.from({ length: 6 }, (_, i) => addMonths(lastClose, i - 5));
  const openedAt = addDays(addMonths(closes[0]!, -1), 1);
  const lineId = `demo-line-${user.id.slice(-4)}`;

  // Store purchases sprinkled through the history (statement index → purchase).
  const purchases: Record<number, { productId: string; dayOffset: number }> = {
    1: { productId: "prod-food-handler", dayOffset: -12 },
    3: { productId: "prod-forklift-prep", dayOffset: -20 },
    5: { productId: "prod-budget-kit", dayOffset: -9 },
  };

  const statements: StatementRecord[] = [];
  const payments: PaymentRecord[] = [];
  const transactions: CreditTransactionRecord[] = [];
  let balance = 0;
  let seq = 1;

  closes.forEach((close, i) => {
    const periodStart = i === 0 ? openedAt : addDays(closes[i - 1]!, 1);
    const activity: Array<{ kind: "purchase" | "payment"; amountCents: number; occurredAt: string }> = [];
    const p = purchases[i];
    if (p) {
      const product = demoStoreProducts.find((x) => x.id === p.productId)!;
      const at = addDays(close, p.dayOffset).toISOString();
      activity.push({ kind: "purchase", amountCents: product.priceCents, occurredAt: at });
      transactions.push({ id: demoId("txn", seq++), kind: "purchase", amountCents: product.priceCents, description: product.name, occurredAt: at });
    }
    // Last month's payment lands inside this period.
    const prev = payments[payments.length - 1];
    if (prev && i > 0) activity.push({ kind: "payment", amountCents: prev.amountCents, occurredAt: prev.paidAt });

    const g = generateMonthlyStatement({
      creditLineId: lineId,
      periodStart,
      periodEnd: close,
      previousBalanceCents: balance,
      activity,
      membership: { status: "active", freeMonthsRemaining: 0 },
    });
    if (g.membershipCharge) {
      transactions.push({
        id: demoId("txn", seq++),
        kind: "membership_fee",
        amountCents: g.membershipCharge.amountCents,
        description: g.membershipCharge.description,
        occurredAt: close.toISOString(),
      });
    }
    statements.push({ ...g.statement, id: demoId("stmt", i + 1) });
    balance = g.closingBalanceCents;

    // Statements 1–5 were paid in full, on time, ten days after closing.
    if (i < 5) {
      const paidAt = addDays(close, 10);
      paidAt.setUTCHours(16, 30, 0, 0);
      payments.push({ id: demoId("pay", i + 1), amountCents: g.statement.minimumDueCents, paidAt: paidAt.toISOString(), method: i % 2 ? "wallet" : "card", status: "succeeded" });
    }
  });
  // The final statement's balance is the line balance (its payment hasn't happened yet).
  const lineBalance = statements[statements.length - 1]!.statementBalanceCents;

  const leveledUpAt = addDays(closes[2]!, 10).toISOString();
  // Monthly soft-pull refreshes; the newest one came back with this week's statement.
  const scores = [604, 618, 633, 645, 657, 668].map((score, i) => ({
    score,
    pulledAt: (i === 5 ? lastClose : addDays(closes[i]!, 3)).toISOString(),
    source: "Soft-inquiry partner (VantageScore 4.0)",
  }));

  const referrals: ReferralRecord[] = [
    {
      id: "ref-0001",
      referrerId: user.id,
      referredId: "demo-friend-jordan",
      referredName: "Jordan R.",
      status: "qualified",
      // Qualified after the last statement closed, so the free month is still banked.
      qualifiedAt: new Date(now.getTime() - 6 * 3_600_000).toISOString(),
      rewardMonths: 1,
    },
    {
      id: "ref-0002",
      referrerId: user.id,
      referredId: "demo-friend-alex",
      referredName: "Alex P.",
      status: "pending",
      qualifiedAt: null,
      rewardMonths: 0,
    },
  ];

  return {
    line: {
      id: lineId,
      userId: user.id,
      limitCents: CREDIT.levelUpLimitCents,
      balanceCents: lineBalance,
      status: "open",
      openedAt: openedAt.toISOString(),
      accountNumber: `SSV1000${user.id.replace(/\D/g, "").slice(-9).padStart(9, "0")}`,
      closedAt: null,
      closedAtConsumerRequest: false,
    },
    membership: { status: "active", freeMonthsRemaining: 1, startedAt: openedAt.toISOString(), canceledAt: null },
    statements,
    payments,
    transactions,
    scores,
    softPullConsentAt: openedAt.toISOString(),
    badges: [
      { key: "first_on_time_payment", awardedAt: payments[0]!.paidAt },
      { key: "streak_3", awardedAt: payments[2]!.paidAt },
      { key: "level_up", awardedAt: leveledUpAt },
    ],
    referralCode: referralCodeFor(user.fullName, user.id),
    referrals,
    addons: [{ key: ADDONS.rentReporting.key, status: "active", startedAt: addDays(closes[3]!, 2).toISOString(), canceledAt: null }],
    offers: demoAffiliateOffers,
    billAnalyses: [],
    seq: 100,
  };
}

/** Per-user mutable demo state. */
export function getDemoCreditState(user: { id: string; fullName: string }): DemoCreditState {
  return demoStore(`credit:${user.id}`, () => buildDemoCreditState(user));
}

/** Next demo id for this user's state. */
export function nextDemoId(state: DemoCreditState, prefix: string): string {
  state.seq += 1;
  return demoId(prefix, state.seq);
}
