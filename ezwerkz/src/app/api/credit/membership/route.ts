import { requireRole } from "@/lib/auth";
import { handleCredit } from "@/lib/credit/errors";
import { cancelMembership, resumeMembership } from "@/lib/credit/service";

/** Cancel the membership. The UI reaches this in two taps with no retention detour. */
export async function DELETE() {
  return handleCredit(async () => {
    const user = await requireRole("member", "worker", "admin");
    return cancelMembership(user);
  });
}

/** Undo a cancellation while the line is still open. */
export async function POST() {
  return handleCredit(async () => {
    const user = await requireRole("member", "worker", "admin");
    return resumeMembership(user);
  });
}
