import { requireRole } from "@/lib/auth";
import { getCreditSummary } from "@/lib/credit/queries";
import { handleCredit } from "@/lib/credit/errors";

export const dynamic = "force-dynamic";

export async function GET() {
  return handleCredit(async () => {
    const user = await requireRole("member", "worker", "admin");
    return { summary: await getCreditSummary(user) };
  });
}
