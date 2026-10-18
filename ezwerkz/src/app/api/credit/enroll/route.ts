import { requireRole } from "@/lib/auth";
import { handleCredit } from "@/lib/credit/errors";
import { enroll } from "@/lib/credit/service";

/** Open a credit builder line and membership (idempotent). */
export async function POST() {
  return handleCredit(async () => {
    const user = await requireRole("member", "worker", "admin");
    return enroll(user);
  });
}
