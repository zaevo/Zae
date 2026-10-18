import { describe, expect, it } from "vitest";
import type { LedgerCategory, LedgerEntry } from "@/lib/types";
import {
  CATEGORY_META,
  balanceFromEntries,
  dayKey,
  groupByDay,
  incomeBySource,
  monthlyTotals,
  shiftDayKey,
  splitShiftPay,
  totalsForMonth,
} from "./ledger";

let seq = 0;
function entry(direction: "credit" | "debit", amountCents: number, category: LedgerCategory, createdAt: string): LedgerEntry {
  seq += 1;
  return { id: `e${seq}`, walletId: "w1", direction, amountCents, category, description: category, createdAt };
}

const TZ = "America/New_York";

describe("balanceFromEntries", () => {
  it("adds credits and subtracts debits from the opening balance", () => {
    const entries = [
      entry("credit", 9000, "shift_earnings", "2026-10-01T15:00:00Z"),
      entry("debit", 500, "membership_fee", "2026-10-02T15:00:00Z"),
      entry("debit", 1250, "card_spend", "2026-10-03T15:00:00Z"),
    ];
    expect(balanceFromEntries(entries)).toBe(7250);
    expect(balanceFromEntries(entries, 1000)).toBe(8250);
    expect(balanceFromEntries([])).toBe(0);
  });
});

describe("dayKey / shiftDayKey", () => {
  it("uses the display zone, not UTC", () => {
    // 02:30 UTC on Oct 18 is still the evening of Oct 17 in New York.
    expect(dayKey("2026-10-18T02:30:00Z", TZ)).toBe("2026-10-17");
    expect(dayKey("2026-10-18T02:30:00Z", "UTC")).toBe("2026-10-18");
  });

  it("does calendar arithmetic across month, year and DST boundaries", () => {
    expect(shiftDayKey("2026-03-01", -1)).toBe("2026-02-28");
    expect(shiftDayKey("2027-01-01", -1)).toBe("2026-12-31");
    expect(shiftDayKey("2026-03-09", -1)).toBe("2026-03-08");
  });
});

describe("groupByDay", () => {
  const now = new Date("2026-10-18T16:00:00Z");
  const entries = [
    entry("debit", 487, "card_spend", "2026-10-18T13:00:00Z"),
    entry("credit", 9000, "shift_earnings", "2026-10-18T02:00:00Z"), // Oct 17 evening in NY
    entry("debit", 1236, "card_spend", "2026-10-17T16:00:00Z"),
    entry("credit", 1599, "refund", "2026-10-12T16:00:00Z"),
    entry("debit", 500, "membership_fee", "2025-12-30T16:00:00Z"),
  ];

  it("groups newest day first with Today / Yesterday / dated labels", () => {
    const groups = groupByDay(entries, { now, timeZone: TZ });
    expect(groups.map((g) => g.key)).toEqual(["2026-10-18", "2026-10-17", "2026-10-12", "2025-12-30"]);
    expect(groups.map((g) => g.label)).toEqual(["Today", "Yesterday", "Mon, Oct 12", "Tue, Dec 30, 2025"]);
  });

  it("orders entries newest first within a day and computes each day's net", () => {
    const yesterday = groupByDay(entries, { now, timeZone: TZ })[1]!;
    expect(yesterday.entries.map((e) => e.amountCents)).toEqual([9000, 1236]);
    expect(yesterday.netCents).toBe(9000 - 1236);
  });
});

describe("monthly totals", () => {
  const entries = [
    entry("credit", 9000, "shift_earnings", "2026-10-03T16:00:00Z"),
    entry("credit", 61250, "deposit", "2026-10-10T16:00:00Z"),
    entry("debit", 500, "membership_fee", "2026-10-01T16:00:00Z"),
    entry("debit", 4000, "card_spend", "2026-10-05T16:00:00Z"),
    entry("credit", 1500, "refund", "2026-10-06T16:00:00Z"),
    entry("debit", 20000, "withdrawal", "2026-10-07T16:00:00Z"),
    entry("credit", 12000, "shift_earnings", "2026-09-20T16:00:00Z"),
  ];

  it("separates income, spend net of refunds, and transfers out", () => {
    const oct = totalsForMonth(entries, "2026-10", TZ);
    expect(oct.incomeCents).toBe(9000 + 61250);
    expect(oct.spendCents).toBe(500 + 4000 - 1500);
    expect(oct.transfersOutCents).toBe(20000);
    expect(oct.netCents).toBe(9000 + 61250 - 500 - 4000 + 1500 - 20000);
  });

  it("never reports negative spend when refunds exceed purchases", () => {
    const totals = totalsForMonth([entry("credit", 2000, "refund", "2026-10-06T16:00:00Z")], "2026-10", TZ);
    expect(totals.spendCents).toBe(0);
  });

  it("lists months newest first", () => {
    expect(monthlyTotals(entries, TZ).map((m) => m.month)).toEqual(["2026-10", "2026-09"]);
  });

  it("splits income into shift earnings vs other sources for one month", () => {
    expect(incomeBySource(entries, "2026-10", TZ)).toEqual({
      shiftEarningsCents: 9000,
      otherIncomeCents: 61250,
      totalCents: 70250,
      shiftCount: 1,
    });
    expect(incomeBySource(entries, "2026-09", TZ).shiftEarningsCents).toBe(12000);
  });
});

describe("splitShiftPay", () => {
  it("routes the allocated share to the wallet and the rest elsewhere, without losing a cent", () => {
    expect(splitShiftPay(9000, 100)).toEqual({ walletCents: 9000, externalCents: 0 });
    expect(splitShiftPay(9001, 50)).toEqual({ walletCents: 4501, externalCents: 4500 });
    expect(splitShiftPay(9000, 150)).toEqual({ walletCents: 9000, externalCents: 0 });
  });

  it("rejects fractional cents", () => {
    expect(() => splitShiftPay(10.5, 50)).toThrow();
  });
});

describe("CATEGORY_META", () => {
  it("has a label, icon and flow for every ledger category", () => {
    const categories: LedgerCategory[] = ["shift_earnings", "membership_fee", "addon_fee", "card_spend", "deposit", "withdrawal", "refund"];
    for (const c of categories) {
      expect(CATEGORY_META[c].label.length).toBeGreaterThan(0);
      expect(CATEGORY_META[c].icon).toBeTruthy();
    }
    expect(Object.keys(CATEGORY_META).sort()).toEqual([...categories].sort());
  });
});
