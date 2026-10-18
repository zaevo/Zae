/**
 * Monthly statement close (live). Run daily by an admin-triggered job
 * (POST /api/credit/statements/run). For every open line whose current
 * period has ended it charges the membership to the line (or spends a
 * referral free month) via post_membership_charge, then cuts the statement
 * via cut_credit_statement — minimum due = statement balance, due date
 * STATEMENT_DUE_DAYS after the close. Both RPCs are idempotent.
 */
import { createSupabaseServiceClient } from "@/lib/supabase/server";
import { STATEMENT_DUE_DAYS, addDays, isoDate, nextStatementPeriod, utcDay } from "./engine";

type ServiceClient = ReturnType<typeof createSupabaseServiceClient>;

export interface StatementRunResult {
  linesChecked: number;
  statementsCreated: number;
  feesCharged: number;
  errors: Array<{ creditLineId: string; message: string }>;
}

async function closeOne(
  service: ServiceClient,
  line: { id: string; user_id: string; opened_at: string },
  today: number,
  result: StatementRunResult,
): Promise<void> {
  const lastRes = await service.from("credit_statements").select("period_end").eq("credit_line_id", line.id).order("period_end", { ascending: false }).limit(1).maybeSingle();
  if (lastRes.error) throw new Error(lastRes.error.message);
  const last = lastRes.data as { period_end: string } | null;
  const { periodStart, periodEnd } = nextStatementPeriod(line.opened_at, last?.period_end ?? null);
  if (utcDay(periodEnd) >= today) return;

  // Charge first so the fee lands on the statement being cut.
  const fee = await service.rpc("post_membership_charge", { p_user_id: line.user_id });
  if (fee.error) throw new Error(`post_membership_charge: ${fee.error.message}`);
  if (fee.data) result.feesCharged++;

  const cut = await service.rpc("cut_credit_statement", {
    p_credit_line_id: line.id,
    p_period_start: isoDate(periodStart),
    p_period_end: isoDate(periodEnd),
    p_due_date: isoDate(addDays(periodEnd, STATEMENT_DUE_DAYS)),
  });
  if (cut.error) throw new Error(`cut_credit_statement: ${cut.error.message}`);
  result.statementsCreated++;
}

export async function runStatementClose(now: Date = new Date()): Promise<StatementRunResult> {
  const service = createSupabaseServiceClient();
  const today = utcDay(now);
  const res = await service.from("virtual_credit_lines").select("id, user_id, opened_at").eq("status", "open");
  if (res.error) throw new Error(`Failed to load credit lines: ${res.error.message}`);
  const rows = (res.data ?? []) as Array<{ id: string; user_id: string; opened_at: string }>;
  const result: StatementRunResult = { linesChecked: rows.length, statementsCreated: 0, feesCharged: 0, errors: [] };
  for (const row of rows) {
    try {
      await closeOne(service, row, today, result);
    } catch (err) {
      result.errors.push({ creditLineId: row.id, message: err instanceof Error ? err.message : "Unknown error" });
    }
  }
  return result;
}
