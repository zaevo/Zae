import { describe, expect, it } from "vitest";
import { CREDIT } from "@/lib/pricing";
import { buildDemoCreditState } from "@/lib/demo/credit";
import { buildCreditSummary, referralLink } from "./summary";

const NOW = new Date("2026-10-16T12:00:00Z");
const user = { id: "00000000-0000-4000-8000-000000000001", fullName: "Maya Johnson" };

describe("demo credit story", () => {
  const state = buildDemoCreditState(user, NOW);
  const s = buildCreditSummary(state, NOW);

  it("has 5 on-time months, a leveled-up real limit and an open statement", () => {
    expect(s.enrolled).toBe(true);
    expect(s.streak).toEqual({ current: 5, best: 5, totalOnTime: 5 });
    expect(s.line?.limitCents).toBe(CREDIT.levelUpLimitCents);
    expect(s.levelUp?.leveledUp).toBe(true);
    expect(s.current?.status).toBe("due");
    expect(s.current?.periodEnd).toBe("2026-10-15");
    expect(s.current?.dueDate).toBe("2026-11-09");
    expect(s.current?.remainingDueCents).toBe(s.line?.balanceCents);
    expect(s.hasPastDue).toBe(false);
  });

  it("line balance equals the sum of charges minus payments", () => {
    const charges = state.transactions.reduce((n, t) => n + t.amountCents, 0);
    const paid = state.payments.reduce((n, p) => n + p.amountCents, 0);
    expect(state.line!.balanceCents).toBe(charges - paid);
    expect(s.availableCents).toBe(CREDIT.levelUpLimitCents - state.line!.balanceCents);
  });

  it("score 668 unlocks the offers widget, ranked by fit", () => {
    expect(s.score?.score).toBe(668);
    expect(s.offers.unlocked).toBe(true);
    expect(s.offers.eligible.map((o) => o.issuer)).toEqual(["Northwind Bank", "Lumen Credit Union", "Harbor Financial"]);
    expect(s.offers.notYet.map((o) => o.issuer)).toEqual(["Cobalt Card Co."]);
  });

  it("history has 24 months ending with the open statement", () => {
    expect(s.history).toHaveLength(24);
    expect(s.history.at(-1)?.state).toBe("due");
    expect(s.history.filter((h) => h.state === "on_time")).toHaveLength(5);
  });

  it("badges, referrals and add-ons", () => {
    expect(s.badges.filter((b) => b.earnedAt).map((b) => b.key)).toEqual(["first_on_time_payment", "streak_3", "level_up"]);
    expect(s.nextMilestone?.badge.key).toBe("streak_6");
    expect(s.nextMilestone?.monthsToGo).toBe(1);
    expect(s.referral.earnedMonths).toBe(1);
    expect(s.referral.freeMonthsRemaining).toBe(1);
    expect(s.addons.find((a) => a.key === "rent_reporting")?.active).toBe(true);
    expect(s.addons.find((a) => a.key === "ai_coach")?.active).toBe(false);
  });

  it("builds an absolute referral link", () => {
    expect(referralLink("https://app.example/", "MAYA-0001")).toBe("https://app.example/login?ref=MAYA-0001");
  });

  it("locks offers below the threshold", () => {
    const low = buildCreditSummary({ ...state, scores: [{ score: 640, pulledAt: NOW.toISOString(), source: "x" }] }, NOW);
    expect(low.offers.unlocked).toBe(false);
    expect(low.offers.eligible).toEqual([]);
    const none = buildCreditSummary({ ...state, scores: [] }, NOW);
    expect(none.score).toBeNull();
    expect(none.offers.unlocked).toBe(false);
  });
});
