import { describe, expect, it } from "vitest";
import { CREDIT, MEMBERSHIP_SPLIT, REFERRAL } from "@/lib/pricing";
import type { AffiliateOffer } from "@/lib/types";
import {
  PaymentError,
  STATEMENT_DUE_DAYS,
  accountDaysPastDue,
  addMonths,
  applyPayment,
  availableCredit,
  badgesToAward,
  canPurchase,
  currentStatement,
  daysBetween,
  evaluateStatements,
  generateMonthlyStatement,
  levelUpProgress,
  membershipTreasuryAllocations,
  nextStatementPeriod,
  nextStreakMilestone,
  onTimeStreak,
  paymentHistoryMonths,
  qualifyReferral,
  qualifyingBadges,
  rankAffiliateOffers,
  treasuryForSatisfiedStatements,
  utilization,
  type PaymentRecord,
  type ReferralRecord,
  type StatementRecord,
} from "./engine";

function stmt(id: string, periodEnd: string, minimumDueCents: number, extra: Partial<StatementRecord> = {}): StatementRecord {
  const end = new Date(`${periodEnd}T00:00:00Z`);
  const start = new Date(addMonths(end, -1).getTime() + 86_400_000);
  const due = new Date(end.getTime() + STATEMENT_DUE_DAYS * 86_400_000);
  return {
    id,
    creditLineId: "line-1",
    periodStart: start.toISOString().slice(0, 10),
    periodEnd,
    statementBalanceCents: minimumDueCents,
    minimumDueCents,
    dueDate: due.toISOString().slice(0, 10),
    paidAt: null,
    paidOnTime: null,
    daysPastDue: 0,
    previousBalanceCents: 0,
    purchasesCents: 0,
    membershipFeeCents: CREDIT.membershipFeeCents,
    paymentsCents: 0,
    creditsCents: 0,
    ...extra,
  };
}

function pay(id: string, paidAt: string, amountCents: number, status: PaymentRecord["status"] = "succeeded"): PaymentRecord {
  return { id, paidAt: `${paidAt}T15:00:00Z`, amountCents, method: "wallet", status };
}

describe("dates", () => {
  it("clamps month addition and counts calendar days", () => {
    expect(addMonths("2026-01-31", 1).toISOString().slice(0, 10)).toBe("2026-02-28");
    expect(daysBetween("2026-10-01T23:00:00Z", "2026-10-02T01:00:00Z")).toBe(1);
    expect(daysBetween("2026-10-10", "2026-10-01")).toBe(-9);
  });

  it("computes consecutive statement periods anchored on the open date", () => {
    const first = nextStatementPeriod("2026-04-16", null);
    expect(first.periodStart.toISOString().slice(0, 10)).toBe("2026-04-16");
    expect(first.periodEnd.toISOString().slice(0, 10)).toBe("2026-05-15");
    const second = nextStatementPeriod("2026-04-16", first.periodEnd);
    expect(second.periodStart.toISOString().slice(0, 10)).toBe("2026-05-16");
    expect(second.periodEnd.toISOString().slice(0, 10)).toBe("2026-06-15");
  });
});

describe("generateMonthlyStatement", () => {
  const base = {
    creditLineId: "line-1",
    periodStart: "2026-09-16",
    periodEnd: "2026-10-15",
  };

  it("charges the membership fee to the line and sets minimum due = statement balance", () => {
    const g = generateMonthlyStatement({
      ...base,
      previousBalanceCents: 0,
      activity: [{ kind: "purchase", amountCents: 15_00, occurredAt: "2026-09-20T10:00:00Z" }],
      membership: { status: "active", freeMonthsRemaining: 0 },
    });
    expect(g.membershipCharge).toEqual({ amountCents: CREDIT.membershipFeeCents, description: "EzWerkz membership" });
    expect(g.statement.statementBalanceCents).toBe(15_00 + CREDIT.membershipFeeCents);
    expect(g.statement.minimumDueCents).toBe(g.statement.statementBalanceCents);
    expect(g.statement.dueDate).toBe("2026-11-09");
    expect(g.closingBalanceCents).toBe(g.statement.statementBalanceCents);
  });

  it("carries the previous balance and nets payments and refunds", () => {
    const g = generateMonthlyStatement({
      ...base,
      previousBalanceCents: 20_00,
      activity: [
        { kind: "payment", amountCents: 20_00, occurredAt: "2026-10-01T10:00:00Z" },
        { kind: "purchase", amountCents: 10_00, occurredAt: "2026-10-02T10:00:00Z" },
        { kind: "refund", amountCents: 4_00, occurredAt: "2026-10-03T10:00:00Z" },
        { kind: "purchase", amountCents: 99_00, occurredAt: "2026-10-16T10:00:00Z" }, // next period
      ],
      membership: { status: "active", freeMonthsRemaining: 0 },
    });
    expect(g.statement.purchasesCents).toBe(10_00);
    expect(g.statement.paymentsCents).toBe(20_00);
    expect(g.statement.creditsCents).toBe(4_00);
    expect(g.statement.statementBalanceCents).toBe(20_00 - 20_00 + 10_00 - 4_00 + CREDIT.membershipFeeCents);
  });

  it("waives the fee with a referral free month and decrements it", () => {
    const g = generateMonthlyStatement({ ...base, previousBalanceCents: 0, activity: [], membership: { status: "active", freeMonthsRemaining: 2 } });
    expect(g.membershipCharge).toBeNull();
    expect(g.membershipWaived).toBe(true);
    expect(g.freeMonthsRemaining).toBe(1);
    expect(g.statement.minimumDueCents).toBe(0);
  });

  it("does not charge canceled memberships", () => {
    const g = generateMonthlyStatement({ ...base, previousBalanceCents: 0, activity: [], membership: { status: "canceled", freeMonthsRemaining: 0 } });
    expect(g.membershipCharge).toBeNull();
    expect(g.membershipWaived).toBe(false);
  });

  it("rejects non-positive activity amounts", () => {
    expect(() =>
      generateMonthlyStatement({
        ...base,
        previousBalanceCents: 0,
        activity: [{ kind: "purchase", amountCents: -5, occurredAt: "2026-09-20" }],
        membership: { status: "active", freeMonthsRemaining: 0 },
      }),
    ).toThrow();
  });
});

describe("evaluateStatements and payments", () => {
  const s1 = stmt("s1", "2026-08-15", 5_00); // due 2026-09-09
  const s2 = stmt("s2", "2026-09-15", 10_00, { previousBalanceCents: 5_00 }); // due 2026-10-10, carries s1

  it("marks statements paid on time when paid by the due date", () => {
    const v = evaluateStatements([s1], [pay("p1", "2026-09-01", 5_00)], "2026-10-01");
    expect(v[0]!.status).toBe("paid_on_time");
    expect(v[0]!.paidOnTime).toBe(true);
    expect(v[0]!.remainingDueCents).toBe(0);
  });

  it("paying on the due date counts as on time; the day after is late", () => {
    expect(evaluateStatements([s1], [pay("p", "2026-09-09", 5_00)], "2026-10-01")[0]!.status).toBe("paid_on_time");
    expect(evaluateStatements([s1], [pay("p", "2026-09-10", 5_00)], "2026-10-01")[0]!.status).toBe("paid_late");
  });

  it("computes days past due for unpaid statements", () => {
    const v = evaluateStatements([s1], [], "2026-10-12");
    expect(v[0]!.status).toBe("past_due");
    expect(v[0]!.daysPastDue).toBe(33);
    expect(accountDaysPastDue([s1], [], "2026-10-12")).toBe(33);
    expect(evaluateStatements([s1], [], "2026-09-05")[0]!.status).toBe("due");
  });

  it("ignores pending and failed payments", () => {
    const v = evaluateStatements([s1], [pay("p", "2026-09-01", 5_00, "pending"), pay("q", "2026-09-02", 5_00, "failed")], "2026-09-20");
    expect(v[0]!.status).toBe("past_due");
  });

  it("one payment can satisfy a carried statement late and the newer one on time", () => {
    const v = evaluateStatements([s1, s2], [pay("p", "2026-10-01", 10_00)], "2026-10-02");
    expect(v.map((s) => s.status)).toEqual(["paid_late", "paid_on_time"]);
  });

  it("partial payments count toward the oldest statement first", () => {
    const v = evaluateStatements([s1, s2], [pay("p", "2026-09-20", 5_00)], "2026-09-21");
    expect(v[0]!.status).toBe("paid_late");
    expect(v[1]!.status).toBe("due");
    expect(v[1]!.remainingDueCents).toBe(5_00);
  });

  it("applyPayment validates the amount and reports newly satisfied statements", () => {
    const line = { balanceCents: 10_00 };
    expect(() => applyPayment({ line, statements: [s1, s2], payments: [], payment: pay("p", "2026-10-01", 0) })).toThrow(PaymentError);
    expect(() => applyPayment({ line, statements: [s1, s2], payments: [], payment: pay("p", "2026-10-01", 11_00) })).toThrow(/more than your balance/);
    const r = applyPayment({ line, statements: [s1, s2], payments: [], payment: pay("p", "2026-10-01", 10_00) });
    expect(r.lineBalanceCents).toBe(0);
    expect(r.newlySatisfied.map((s) => s.id)).toEqual(["s1", "s2"]);
    const pending = applyPayment({ line, statements: [s1, s2], payments: [], payment: pay("p", "2026-10-01", 10_00, "pending") });
    expect(pending.newlySatisfied).toEqual([]);
    expect(pending.lineBalanceCents).toBe(10_00);
  });

  it("currentStatement is the newest statement with money due", () => {
    const v = evaluateStatements([s1, s2], [pay("p", "2026-09-01", 5_00)], "2026-09-20");
    expect(currentStatement(v)?.id).toBe("s2");
    const paid = evaluateStatements([s1, s2], [pay("p", "2026-09-01", 5_00), pay("q", "2026-09-20", 10_00)], "2026-09-21");
    expect(currentStatement(paid)).toBeNull();
  });
});

describe("streaks, badges and level-up", () => {
  const months = ["2026-05-15", "2026-06-15", "2026-07-15", "2026-08-15", "2026-09-15"];
  const statements = months.map((m, i) => stmt(`s${i}`, m, 5_00));
  const onTimePayments = months.map((m, i) => pay(`p${i}`, m.replace("-15", "-25"), 5_00));

  it("counts consecutive on-time statements and ignores ones not yet due", () => {
    const withOpen = [...statements, stmt("s5", "2026-10-15", 5_00)];
    const v = evaluateStatements(withOpen, onTimePayments, "2026-10-16");
    expect(onTimeStreak(v)).toEqual({ current: 5, best: 5, totalOnTime: 5 });
  });

  it("a late payment resets the current streak but keeps the best", () => {
    const payments = [...onTimePayments.slice(0, 3), pay("late", "2026-09-20", 5_00), pay("p4", "2026-09-25", 5_00)];
    const v = evaluateStatements(statements, payments, "2026-10-16");
    expect(v[3]!.status).toBe("paid_late");
    expect(onTimeStreak(v)).toEqual({ current: 1, best: 3, totalOnTime: 4 });
  });

  it("awards badges once and never revokes them", () => {
    const v = evaluateStatements(statements, onTimePayments, "2026-10-16");
    const streak = onTimeStreak(v);
    expect(qualifyingBadges({ streak, leveledUp: false })).toEqual(["first_on_time_payment", "streak_3"]);
    expect(badgesToAward(["first_on_time_payment"], { streak, leveledUp: true })).toEqual(["streak_3", "level_up"]);
    expect(badgesToAward(["first_on_time_payment", "streak_3", "level_up"], { streak, leveledUp: true })).toEqual([]);
    const six = { current: CREDIT.streakBadgeMonths, best: CREDIT.streakBadgeMonths, totalOnTime: CREDIT.streakBadgeMonths };
    expect(qualifyingBadges({ streak: six, leveledUp: true })).toContain("streak_6");
  });

  it("names the next streak milestone", () => {
    expect(nextStreakMilestone({ current: 5, best: 5, totalOnTime: 5 }, ["first_on_time_payment", "streak_3"])).toEqual({
      badge: "streak_6",
      monthsToGo: 1,
    });
    expect(nextStreakMilestone({ current: 0, best: 0, totalOnTime: 0 }, [])).toEqual({ badge: "first_on_time_payment", monthsToGo: 1 });
  });

  it("is eligible to level up after the required on-time months", () => {
    const line = { limitCents: CREDIT.defaultLimitCents, status: "open" as const };
    const two = evaluateStatements(statements.slice(0, 2), onTimePayments, "2026-07-20");
    expect(levelUpProgress(line, two)).toMatchObject({ eligible: false, onTimeMonths: 2, remainingMonths: 1 });
    const three = evaluateStatements(statements.slice(0, CREDIT.levelUpAfterOnTimeMonths), onTimePayments, "2026-08-20");
    expect(levelUpProgress(line, three)).toMatchObject({ eligible: true, remainingMonths: 0, nextLimitCents: CREDIT.levelUpLimitCents });
    const leveled = levelUpProgress({ limitCents: CREDIT.levelUpLimitCents, status: "open" }, three);
    expect(leveled).toMatchObject({ eligible: false, leveledUp: true });
  });

  it("is not eligible while anything is past due or the line is closed", () => {
    const pastDue = evaluateStatements([...statements.slice(0, 3), stmt("x", "2026-08-15", 5_00)], onTimePayments.slice(0, 3), "2026-10-16");
    expect(levelUpProgress({ limitCents: CREDIT.defaultLimitCents, status: "open" }, pastDue).eligible).toBe(false);
    const ok = evaluateStatements(statements.slice(0, 3), onTimePayments, "2026-08-20");
    expect(levelUpProgress({ limitCents: CREDIT.defaultLimitCents, status: "closed" }, ok).eligible).toBe(false);
  });

  it("builds 24 history dots ending this month", () => {
    const withOpen = [...statements, stmt("s5", "2026-10-15", 5_00)];
    const v = evaluateStatements(withOpen, onTimePayments, "2026-10-16");
    const dots = paymentHistoryMonths(v, "2026-04-16", "2026-10-16");
    expect(dots).toHaveLength(24);
    expect(dots.at(-1)).toMatchObject({ month: "2026-10", state: "due" });
    expect(dots.at(-2)).toMatchObject({ month: "2026-09", state: "on_time" });
    expect(dots.find((d) => d.month === "2026-04")?.state).toBe("none");
    expect(dots[0]).toMatchObject({ month: "2024-11", state: "not_open" });
  });
});

describe("utilization and purchases", () => {
  it("computes utilization and available credit", () => {
    expect(utilization(25_00, 500_00)).toBeCloseTo(0.05);
    expect(utilization(900_00, 500_00)).toBe(1);
    expect(utilization(10, 0)).toBe(0);
    expect(availableCredit({ limitCents: 500_00, balanceCents: 520_00 })).toBe(0);
  });

  it("never lets a purchase exceed available credit", () => {
    const line = { limitCents: 500_00, balanceCents: 480_00, status: "open" as const };
    const member = { status: "active" as const, freeMonthsRemaining: 0 };
    expect(canPurchase({ line, membership: member, priceCents: 20_00, hasPastDue: false })).toEqual({
      ok: true,
      balanceAfterCents: 500_00,
      availableAfterCents: 0,
    });
    expect(canPurchase({ line, membership: member, priceCents: 20_01, hasPastDue: false })).toEqual({ ok: false, reason: "INSUFFICIENT_CREDIT" });
    expect(canPurchase({ line, membership: { status: "canceled", freeMonthsRemaining: 0 }, priceCents: 1_00, hasPastDue: false })).toEqual({
      ok: false,
      reason: "MEMBERSHIP_INACTIVE",
    });
    expect(canPurchase({ line: { ...line, status: "closed" }, membership: member, priceCents: 1_00, hasPastDue: false })).toEqual({
      ok: false,
      reason: "LINE_NOT_OPEN",
    });
    expect(canPurchase({ line, membership: member, priceCents: 1_00, hasPastDue: true })).toEqual({ ok: false, reason: "PAST_DUE" });
    expect(canPurchase({ line, membership: member, priceCents: 0, hasPastDue: false })).toEqual({ ok: false, reason: "INVALID_PRICE" });
  });
});

describe("referrals", () => {
  const referral: ReferralRecord = {
    id: "r1",
    referrerId: "u1",
    referredId: "u2",
    referredName: "Jordan",
    status: "pending",
    qualifiedAt: null,
    rewardMonths: 0,
  };

  it("qualifies on the referred member's first on-time payment", () => {
    const v = evaluateStatements([stmt("a", "2026-09-15", 5_00)], [pay("p", "2026-09-30", 5_00)], "2026-10-16");
    const r = qualifyReferral(referral, v);
    expect(r.rewardMonths).toBe(REFERRAL.rewardMonths);
    expect(r.referral.status).toBe("qualified");
    expect(r.referral.qualifiedAt).toBe("2026-09-30T15:00:00Z");
  });

  it("does not reward late payers, repeats, or self-referrals", () => {
    const late = evaluateStatements([stmt("a", "2026-08-15", 5_00)], [pay("p", "2026-09-30", 5_00)], "2026-10-16");
    expect(qualifyReferral(referral, late).rewardMonths).toBe(0);
    const v = evaluateStatements([stmt("a", "2026-09-15", 5_00)], [pay("p", "2026-09-30", 5_00)], "2026-10-16");
    expect(qualifyReferral({ ...referral, status: "qualified" }, v).rewardMonths).toBe(0);
    expect(qualifyReferral({ ...referral, referredId: "u1" }, v).rewardMonths).toBe(0);
  });
});

describe("treasury split", () => {
  it("splits membership revenue using the pricing config and sums exactly", () => {
    const rows = membershipTreasuryAllocations(CREDIT.membershipFeeCents);
    expect(rows.reduce((n, r) => n + r.amountCents, 0)).toBe(CREDIT.membershipFeeCents);
    expect(rows.find((r) => r.bucket === "reporting_vendor")?.amountCents).toBe(MEMBERSHIP_SPLIT.reportingVendorCents);
    if (MEMBERSHIP_SPLIT.impactCents === 0) expect(rows.find((r) => r.bucket === "impact")).toBeUndefined();
    expect(membershipTreasuryAllocations(1_00)).toEqual([{ bucket: "reporting_vendor", amountCents: 1_00 }]);
    expect(membershipTreasuryAllocations(0)).toEqual([]);
  });

  it("splits only each satisfied statement's own fee", () => {
    const s1 = stmt("s1", "2026-08-15", 5_00);
    const s2 = stmt("s2", "2026-09-15", 30_00, { previousBalanceCents: 5_00, purchasesCents: 20_00 });
    const r = applyPayment({ line: { balanceCents: 30_00 }, statements: [s1, s2], payments: [], payment: pay("p", "2026-10-01", 30_00) });
    const rows = treasuryForSatisfiedStatements(r.newlySatisfied);
    expect(rows.reduce((n, x) => n + x.amountCents, 0)).toBe(2 * CREDIT.membershipFeeCents);
    expect(new Set(rows.map((x) => x.statementId))).toEqual(new Set(["s1", "s2"]));
  });
});

describe("rankAffiliateOffers", () => {
  const offers: AffiliateOffer[] = [
    { id: "a", issuer: "Aster", productName: "Gold", minScore: 640, annualFeeCents: 95_00, aprText: "", highlights: ["x", "y", "z"], bountyCents: 300_00, url: "" },
    { id: "b", issuer: "Birch", productName: "Cash", minScore: 650, annualFeeCents: 0, aprText: "", highlights: ["x"], bountyCents: 10_00, url: "" },
    { id: "c", issuer: "Cedar", productName: "Plus", minScore: 600, annualFeeCents: 0, aprText: "", highlights: ["x", "y"], bountyCents: 50_00, url: "" },
    { id: "d", issuer: "Dune", productName: "Prime", minScore: 700, annualFeeCents: 0, aprText: "", highlights: ["x", "y", "z", "w"], bountyCents: 500_00, url: "" },
  ];

  it("keeps only offers the score qualifies for, then lowest fee, then most highlights", () => {
    const r = rankAffiliateOffers(offers, 668);
    expect(r.eligible.map((o) => o.id)).toEqual(["c", "b", "a"]);
    expect(r.eligible.map((o) => o.rank)).toEqual([1, 2, 3]);
    expect(r.notYet.map((o) => o.id)).toEqual(["d"]);
  });

  it("never ranks by bounty", () => {
    const boosted = offers.map((o) => (o.id === "a" ? { ...o, bountyCents: 10_000_00 } : { ...o, bountyCents: 0 }));
    expect(rankAffiliateOffers(boosted, 668).eligible.map((o) => o.id)).toEqual(rankAffiliateOffers(offers, 668).eligible.map((o) => o.id));
  });
});
