import { NextResponse } from "next/server";
import { requireRole } from "@/lib/auth";
import { isDemoMode } from "@/lib/env";
import { handleCredit } from "@/lib/credit/errors";
import { runStatementClose } from "@/lib/credit/statementRun";

export const runtime = "nodejs";

/** Admin/cron: close statements for every line whose period has ended. */
export async function POST() {
  return handleCredit(async () => {
    await requireRole("admin");
    if (isDemoMode()) {
      return NextResponse.json({ result: { linesChecked: 0, statementsCreated: 0, feesCharged: 0, errors: [] }, demo: true });
    }
    return { result: await runStatementClose() };
  });
}
