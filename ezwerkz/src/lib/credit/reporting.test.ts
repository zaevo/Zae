import { describe, expect, it } from "vitest";
import { CREDIT } from "@/lib/pricing";
import { STATEMENT_DUE_DAYS, addMonths, type PaymentRecord, type StatementRecord } from "./engine";
import { BASE_SEGMENT_FIELDS, buildBaseSegment, parseRecord } from "./metro2";
import { balanceAsOf, buildMetro2Account, complianceConditionFor, historyCodesByMonth, type ReportableLine } from "./reporting";

function stmt(id: string, periodEnd: string, minimumDueCents: number): StatementRecord {
  const end = new Date(`${periodEnd}T00:00:00Z`);
  const due = new Date(end.getTime() + STATEMENT_DUE_DAYS * 86_400_000);
  return {
    id,
    creditLineId: "line-1",
    periodStart: new Date(addMonths(end, -1).getTime() + 86_400_000).toISOString().slice(0, 10),
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
  };
}

const pay = (id: string, day: string, amountCents: number): PaymentRecord => ({
  id,
  amountCents,
  paidAt: `${day}T12:00:00Z`,
  method: "wallet",
  status: "succeeded",
});

const closes = ["2026-05-15", "2026-06-15", "2026-07-15", "2026-08-15", "2026-09-15", "2026-10-15"];

function line(overrides: Partial<ReportableLine> = {}): ReportableLine {
  return {
    line: { limitCents: CREDIT.levelUpLimitCents, balanceCents: 5_00, status: "open", openedAt: "2026-04-16" },
    accountNumber: "SSV1000000000042",
    closedAt: null,
    closedAtConsumerRequest: false,
    chargedOffAt: null,
    chargeOffAmountCents: null,
    statements: closes.map((c, i) => stmt(`s${i}`, c, 5_00)),
    payments: closes.slice(0, 5).map((c, i) => pay(`p${i}`, c.replace("-15", "-28"), 5_00)),
    dispute: "none",
    consumer: {
      surname: "Johnson",
      firstName: "Maya",
      ssn: "666123456",
      dateOfBirth: "1998-03-07",
      addressLine1: "742 Evergreen Ter",
      city: "Oakland",
      state: "CA",
      postalCode: "94607",
    },
    firstReport: false,
    ...overrides,
  };
}

describe("complianceConditionFor", () => {
  it("reports XB while a dispute is open", () => {
    expect(complianceConditionFor("open", false)).toBe("XB");
    expect(complianceConditionFor("open", true)).toBe("XD");
    expect(complianceConditionFor("resolved_consumer_disagrees", false)).toBe("XC");
    expect(complianceConditionFor("resolved", false)).toBe("XH");
    expect(complianceConditionFor("none", true)).toBe("XA");
    expect(complianceConditionFor("none", false)).toBe("");
  });
});

describe("buildMetro2Account", () => {
  it("reports a current account with 5 on-time months", () => {
    const acct = buildMetro2Account(line(), "2026-10-15");
    expect(acct.accountStatus).toBe("11");
    expect(acct.paymentRating).toBe("");
    expect(acct.currentBalanceCents).toBe(5_00);
    expect(acct.amountPastDueCents).toBe(0);
    expect(acct.creditLimitCents).toBe(CREDIT.levelUpLimitCents);
    expect(acct.scheduledMonthlyPaymentCents).toBe(5_00);
    expect(acct.actualPaymentCents).toBe(5_00);
    // Sep..May measured at each close: "0", then April (opened, no statement) "D", then B.
    expect(acct.paymentHistoryProfile).toBe("00000D" + "B".repeat(18));
    expect(acct.dateOfFirstDelinquency).toBeNull();
    const rec = buildBaseSegment(acct, { identificationNumber: "SSV0000001" }, new Date(Date.UTC(2026, 9, 16)));
    expect(rec).toHaveLength(426);
    expect(parseRecord(BASE_SEGMENT_FIELDS, rec).dateOfLastPayment).toBe("09282026");
  });

  it("reports 71 with amount past due and DOFD when a statement is 30+ days late", () => {
    const l = line({
      payments: closes.slice(0, 3).map((c, i) => pay(`p${i}`, c.replace("-15", "-28"), 5_00)),
      line: { limitCents: CREDIT.levelUpLimitCents, balanceCents: 15_00, status: "open", openedAt: "2026-04-16" },
    });
    // s3 (Aug 15 close, due Sep 9) unpaid; s4 carries it.
    const statements = [...l.statements];
    statements[4] = { ...statements[4]!, statementBalanceCents: 10_00, minimumDueCents: 10_00 };
    statements[5] = { ...statements[5]!, statementBalanceCents: 15_00, minimumDueCents: 15_00 };
    const acct = buildMetro2Account({ ...l, statements }, "2026-10-15");
    expect(acct.accountStatus).toBe("71");
    expect(acct.amountPastDueCents).toBe(10_00);
    expect(acct.dateOfFirstDelinquency).toEqual(new Date(Date.UTC(2026, 9, 9)));
    // Sep close: Aug statement 6 days past due → still "0"; history stays clean until 30 days.
    expect(acct.paymentHistoryProfile.slice(0, 1)).toBe("0");
    expect(() => buildBaseSegment(acct, { identificationNumber: "X" }, new Date())).not.toThrow();
  });

  it("reports XB while a dispute is open", () => {
    expect(buildMetro2Account(line({ dispute: "open" }), "2026-10-15").complianceConditionCode).toBe("XB");
  });

  it("reports 13 with payment rating and XA when closed at the member's request with zero balance", () => {
    const acct = buildMetro2Account(
      line({
        closedAt: "2026-10-10",
        closedAtConsumerRequest: true,
        line: { limitCents: CREDIT.levelUpLimitCents, balanceCents: 0, status: "closed", openedAt: "2026-04-16" },
        statements: closes.slice(0, 5).map((c, i) => stmt(`s${i}`, c, 5_00)),
      }),
      "2026-10-15",
    );
    expect(acct.accountStatus).toBe("13");
    expect(acct.paymentRating).toBe("0");
    expect(acct.complianceConditionCode).toBe("XA");
    expect(acct.dateClosed).toBe("2026-10-10");
  });

  it("reports 97 with original charge-off amount", () => {
    const acct = buildMetro2Account(
      line({
        chargedOffAt: "2026-10-01",
        chargeOffAmountCents: 30_00,
        payments: [],
        line: { limitCents: CREDIT.defaultLimitCents, balanceCents: 30_00, status: "charged_off", openedAt: "2026-04-16" },
      }),
      "2026-10-15",
    );
    expect(acct.accountStatus).toBe("97");
    expect(acct.originalChargeOffCents).toBe(30_00);
    expect(acct.dateOfFirstDelinquency).not.toBeNull();
  });

  it("marks the first report as a new account", () => {
    expect(buildMetro2Account(line({ firstReport: true }), "2026-10-15").consumerTransactionType).toBe("1");
  });

  it("history codes reflect delinquency measured at each close", () => {
    const statements = [stmt("a", "2026-05-15", 5_00), stmt("b", "2026-06-15", 10_00), stmt("c", "2026-07-15", 15_00)];
    const codes = historyCodesByMonth(statements, []);
    // a due Jun 9: at Jun 15 → 6 dpd ("0"); at Jul 15 → 36 dpd ("1").
    expect(codes).toEqual({ "2026-05": "0", "2026-06": "0", "2026-07": "1" });
  });
});

describe("balanceAsOf", () => {
  const statements = [stmt("a", "2026-09-15", 5_00), stmt("b", "2026-10-15", 17_00)];
  it("uses the latest closed statement less payments since its close", () => {
    expect(balanceAsOf(statements, [], "2026-10-15")).toBe(17_00);
    expect(balanceAsOf(statements, [pay("p", "2026-10-20", 10_00)], "2026-10-25")).toBe(7_00);
    // A payment after the reporting date doesn't leak into it.
    expect(balanceAsOf(statements, [pay("p", "2026-10-20", 17_00)], "2026-10-15")).toBe(17_00);
    expect(balanceAsOf(statements, [], "2026-09-30")).toBe(5_00);
    expect(balanceAsOf(statements, [], "2026-08-01")).toBe(0);
  });
});
