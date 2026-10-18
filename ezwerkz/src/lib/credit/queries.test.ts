import { describe, expect, it } from "vitest";
import { mockBillAnalysis } from "@/lib/ai/billAnalysis";
import {
  billAnalysisBundle,
  mapBadgeKey,
  mapBillAnalysisRow,
  mapLine,
  mapOffer,
  mapPayment,
  mapProduct,
  mapReferral,
  mapStatement,
  maskEmail,
  shortName,
  type TransactionRow,
} from "./queries";

describe("row mappers (0003_credit.sql shapes)", () => {
  const lineRow = {
    id: "l1",
    user_id: "u1",
    limit_cents: 50000,
    balance_cents: 1700,
    status: "closed" as const,
    account_number: "SS000000000001",
    opened_at: "2026-04-16T00:00:00Z",
    closed_at: "2026-10-10T00:00:00Z",
  };

  it("maps credit lines; closed-at-request comes from a canceled membership", () => {
    expect(mapLine(lineRow, true)).toMatchObject({ limitCents: 50000, balanceCents: 1700, closedAtConsumerRequest: true, accountNumber: "SS000000000001" });
    expect(mapLine(lineRow).closedAtConsumerRequest).toBe(false);
    expect(mapLine({ ...lineRow, status: "open", closed_at: null }, true).closedAtConsumerRequest).toBe(false);
  });

  it("derives the statement breakdown from attached transactions", () => {
    const tx: TransactionRow[] = [
      { id: "t1", kind: "membership_fee", amount_cents: 500, description: "", posted_at: "2026-10-15T00:00:00Z", statement_id: "s1" },
      { id: "t2", kind: "purchase", amount_cents: 1200, description: "", posted_at: "2026-10-02T00:00:00Z", statement_id: "s1" },
      { id: "t3", kind: "refund", amount_cents: 200, description: "", posted_at: "2026-10-03T00:00:00Z", statement_id: "s1" },
      { id: "t4", kind: "purchase", amount_cents: 9900, description: "", posted_at: "2026-10-16T00:00:00Z", statement_id: null },
    ];
    const s = mapStatement(
      {
        id: "s1",
        credit_line_id: "l1",
        period_start: "2026-09-16",
        period_end: "2026-10-15",
        statement_balance_cents: 1500,
        minimum_due_cents: 1500,
        amount_paid_cents: 0,
        due_date: "2026-11-09",
        paid_at: null,
        paid_on_time: null,
        days_past_due: 0,
      },
      tx,
    );
    expect(s).toMatchObject({ membershipFeeCents: 500, purchasesCents: 1200, creditsCents: 200, previousBalanceCents: 0, minimumDueCents: 1500 });
  });

  it("uses paid_at and treats reversed payments as not counting", () => {
    const base = { id: "p", statement_id: "s", amount_cents: 500, method: "ach" as const, provider_payment_id: null, created_at: "2026-10-01T00:00:00Z" };
    expect(mapPayment({ ...base, status: "pending", paid_at: null }).paidAt).toBe("2026-10-01T00:00:00Z");
    expect(mapPayment({ ...base, status: "succeeded", paid_at: "2026-10-03T00:00:00Z" })).toMatchObject({ paidAt: "2026-10-03T00:00:00Z", status: "succeeded" });
    expect(mapPayment({ ...base, status: "reversed", paid_at: "2026-10-03T00:00:00Z" }).status).toBe("failed");
  });

  it("maps offers and products", () => {
    expect(
      mapOffer({ id: "o", issuer: "I", product_name: "P", min_score: 660, annual_fee_cents: 0, apr_text: null, highlights: null, bounty_cents: 1000, url: "https://x" }),
    ).toMatchObject({ aprText: "", highlights: [], productName: "P", bountyCents: 1000 });
    expect(mapProduct({ id: "p", name: "Course", description: null, kind: "course", price_cents: 1500, billing_interval: "one_time" })).toMatchObject({
      category: "course",
      fulfillment: "digital",
      description: "",
    });
    expect(mapProduct({ id: "p", name: "Guide", description: "x", kind: "ebook", price_cents: 900, billing_interval: "one_time" }).category).toBe("digital");
  });

  it("maps database badge keys to UI badges", () => {
    expect(mapBadgeKey("first_on_time_payment")).toBe("first_on_time_payment");
    expect(mapBadgeKey("on_time_streak_3")).toBe("streak_3");
    expect(mapBadgeKey("on_time_streak_6")).toBe("streak_6");
    expect(mapBadgeKey("limit_level_up")).toBe("level_up");
    expect(mapBadgeKey("referral_reward")).toBeNull();
  });

  it("maps referrals: rewarded = qualified, void hidden, names minimized", () => {
    const base = { id: "r", referrer_id: "u1", referred_user_id: "u2", referred_email: null, reward_months: 1, rewarded_at: null };
    expect(mapReferral({ ...base, status: "rewarded", rewarded_at: "2026-10-01T00:00:00Z", referred: [{ full_name: "Jordan Rivera" }] })).toMatchObject({
      status: "qualified",
      rewardMonths: 1,
      referredName: "Jordan R.",
    });
    expect(mapReferral({ ...base, status: "signed_up", referred: null })).toMatchObject({ status: "pending", rewardMonths: 0, referredName: "A friend" });
    expect(mapReferral({ ...base, referred_user_id: null, referred_email: "alex@example.com", status: "invited" })?.referredName).toBe("al•••@example.com");
    expect(mapReferral({ ...base, status: "void" })).toBeNull();
  });

  it("minimizes names and emails", () => {
    expect(shortName("Jordan Rivera")).toBe("Jordan R.");
    expect(shortName("  Ana  María de la Cruz ")).toBe("Ana C.");
    expect(shortName("Cher")).toBe("Cher");
    expect(maskEmail("not-an-email")).toBe("Invited friend");
  });

  it("round-trips a bill analysis through the bill_analyses columns", () => {
    const a = mockBillAnalysis({ id: "b1", fileName: "bill.pdf", analyzedAt: "2026-10-16T00:00:00Z" });
    const back = mapBillAnalysisRow({
      id: "b1",
      provider_name: a.provider,
      billed_amount_cents: a.totalDueCents,
      findings: a.flaggedIssues,
      negotiation_script: billAnalysisBundle(a),
      model: null,
    });
    expect(back).not.toBeNull();
    expect(back!.estimatedMonthlySavingsCents).toBe(a.estimatedMonthlySavingsCents);
    expect(back!.letterDraft).toEqual(a.letterDraft);
    expect(back!.lineItems).toEqual(a.lineItems);
    expect(back!.fileName).toBe("bill.pdf");
    expect(mapBillAnalysisRow({ id: "x", provider_name: null, billed_amount_cents: null, findings: [], negotiation_script: "{bad", model: null })).toBeNull();
  });
});
