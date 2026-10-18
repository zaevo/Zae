/**
 * Maps a EzWerkz credit line (statements + payments + disputes) onto a
 * Metro 2 Base Segment. Pure: the caller loads the data.
 *
 * Only facts are reported — the actual limit, balances, payment history and
 * status (SPEC §2 rule 6). The output is prepared for delivery to a
 * credentialed furnisher partner, who validates against the current CRRG.
 */
import { CREDIT } from "@/lib/pricing";
import type { CreditLine } from "@/lib/types";
import {
  addDays,
  evaluateStatements,
  monthKeyOf,
  utcDay,
  type PaymentRecord,
  type StatementRecord,
} from "./engine";
import {
  COMPLIANCE_CONDITION,
  accountStatusFor,
  buildPaymentHistoryProfile,
  paymentHistoryCodeFor,
  paymentRatingFor,
  type ComplianceConditionCode,
  type Metro2Account,
  type Metro2Consumer,
  type PaymentHistoryCode,
} from "./metro2";

/** FCRA dispute state for the account (credit_reporting_disputes). */
export type DisputeState = "none" | "open" | "resolved" | "resolved_consumer_disagrees";

export interface ReportableLine {
  /** balanceCents is only used when no statement has closed yet. */
  line: Pick<CreditLine, "limitCents" | "balanceCents" | "status" | "openedAt">;
  accountNumber: string;
  closedAt: string | null;
  closedAtConsumerRequest: boolean;
  chargedOffAt: string | null;
  chargeOffAmountCents: number | null;
  statements: readonly StatementRecord[];
  payments: readonly PaymentRecord[];
  dispute: DisputeState;
  consumer: Metro2Consumer;
  /** True the first time this account appears in an export (Consumer Transaction Type 1). */
  firstReport: boolean;
}

/** Metro 2 product classification for the store line: a consumer line of credit, paid monthly. */
export const LINE_CLASSIFICATION = {
  portfolioType: "C",
  accountType: "15",
  termsDuration: "LOC",
  termsFrequency: "M",
} as const;

export function complianceConditionFor(dispute: DisputeState, closedAtConsumerRequest: boolean): ComplianceConditionCode | "" {
  if (dispute === "open") return closedAtConsumerRequest ? COMPLIANCE_CONDITION.closedAtConsumerRequestDisputed : COMPLIANCE_CONDITION.disputedFcra;
  if (dispute === "resolved_consumer_disagrees") return COMPLIANCE_CONDITION.disputeResolvedConsumerDisagrees;
  if (closedAtConsumerRequest) return COMPLIANCE_CONDITION.closedAtConsumerRequest;
  if (dispute === "resolved") return COMPLIANCE_CONDITION.disputeResolved;
  return "";
}

/** Month-by-month history codes keyed "YYYY-MM", measured at each statement's close. */
export function historyCodesByMonth(statements: readonly StatementRecord[], payments: readonly PaymentRecord[]): Record<string, PaymentHistoryCode> {
  const out: Record<string, PaymentHistoryCode> = {};
  for (const s of statements) {
    const views = evaluateStatements(statements, payments, s.periodEnd);
    const dpd = views.reduce((m, v) => Math.max(m, v.daysPastDue), 0);
    out[monthKeyOf(s.periodEnd)] = paymentHistoryCodeFor({ daysPastDue: dpd, balanceCents: s.statementBalanceCents });
  }
  return out;
}

/**
 * Balance on the reporting date: the latest closed statement's balance less
 * payments received since that close. Reporting the live balance instead
 * would leak post-period activity into a past period.
 */
export function balanceAsOf(statements: readonly StatementRecord[], payments: readonly PaymentRecord[], asOf: string | Date): number {
  const asOfDay = utcDay(asOf);
  const closed = statements.filter((s) => utcDay(s.periodEnd) <= asOfDay).sort((a, b) => utcDay(a.periodEnd) - utcDay(b.periodEnd));
  const latest = closed[closed.length - 1];
  if (!latest) return 0;
  const since = payments
    .filter((p) => p.status === "succeeded" && utcDay(p.paidAt) > utcDay(latest.periodEnd) && utcDay(p.paidAt) <= asOfDay)
    .reduce((n, p) => n + p.amountCents, 0);
  return Math.max(0, latest.statementBalanceCents - since);
}

/**
 * Build the Metro 2 account for the reporting date `asOf` (the statement
 * close / Date of Account Information).
 */
export function buildMetro2Account(input: ReportableLine, asOf: string | Date): Metro2Account {
  const asOfDay = utcDay(asOf);
  const statements = input.statements.filter((s) => utcDay(s.periodEnd) <= asOfDay);
  const payments = input.payments.filter((p) => p.status === "succeeded" && utcDay(p.paidAt) <= asOfDay);
  const views = evaluateStatements(statements, payments, asOf);

  const dpd = views.reduce((m, v) => Math.max(m, v.daysPastDue), 0);
  const chargedOff = Boolean(input.chargedOffAt && utcDay(input.chargedOffAt) <= asOfDay);
  const closed = Boolean(input.closedAt && utcDay(input.closedAt) <= asOfDay) || chargedOff;
  const balance = statements.length ? balanceAsOf(statements, payments, asOf) : Math.max(0, input.line.balanceCents);

  const status = accountStatusFor({ daysPastDue: dpd, balanceCents: balance, closed, chargedOff });

  const pastDue = views.filter((v) => v.status === "past_due");
  // The newest past-due statement already carries every older unpaid amount.
  const amountPastDue = pastDue.length ? pastDue[pastDue.length - 1]!.remainingDueCents : 0;
  const oldestUnpaid = pastDue[0];
  const delinquent = /^(71|78|80|82|83|84|97)$/.test(status);
  const dofd = delinquent && oldestUnpaid ? addDays(oldestUnpaid.dueDate, 30) : null;

  const latest = statements.length ? [...statements].sort((a, b) => utcDay(a.periodEnd) - utcDay(b.periodEnd))[statements.length - 1]! : null;
  const previousClose = statements.length > 1
    ? [...statements].sort((a, b) => utcDay(a.periodEnd) - utcDay(b.periodEnd))[statements.length - 2]!.periodEnd
    : null;
  const periodPayments = payments.filter((p) => !previousClose || utcDay(p.paidAt) > utcDay(previousClose));
  const lastPayment = payments.length ? payments.reduce((a, b) => (utcDay(a.paidAt) >= utcDay(b.paidAt) ? a : b)) : null;

  const highest = Math.max(balance, ...statements.map((s) => s.statementBalanceCents));

  return {
    consumerAccountNumber: input.accountNumber,
    ...LINE_CLASSIFICATION,
    dateOpened: input.line.openedAt,
    creditLimitCents: input.line.limitCents || CREDIT.defaultLimitCents,
    highestCreditCents: highest,
    scheduledMonthlyPaymentCents: latest?.minimumDueCents ?? 0,
    actualPaymentCents: periodPayments.reduce((n, p) => n + p.amountCents, 0),
    accountStatus: status,
    paymentRating: paymentRatingFor(status, dpd, chargedOff),
    paymentHistoryProfile: buildPaymentHistoryProfile({
      dateOfAccountInformation: new Date(asOfDay),
      dateOpened: new Date(utcDay(input.line.openedAt)),
      months: historyCodesByMonth(statements, payments),
    }),
    complianceConditionCode: complianceConditionFor(input.dispute, input.closedAtConsumerRequest && closed),
    currentBalanceCents: balance,
    amountPastDueCents: amountPastDue,
    originalChargeOffCents: chargedOff ? (input.chargeOffAmountCents ?? balance) : 0,
    dateOfAccountInformation: new Date(asOfDay),
    dateOfFirstDelinquency: dofd,
    dateClosed: closed ? (input.closedAt ?? input.chargedOffAt) : null,
    dateOfLastPayment: lastPayment?.paidAt ?? null,
    consumerTransactionType: input.firstReport ? "1" : "",
    consumer: input.consumer,
  };
}
