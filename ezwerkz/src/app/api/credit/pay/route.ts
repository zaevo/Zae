import { z } from "zod";
import { requireRole } from "@/lib/auth";
import { handleCredit } from "@/lib/credit/errors";
import { payStatement } from "@/lib/credit/service";

const Body = z.object({
  statementId: z.string().min(1).max(100),
  method: z.enum(["card", "ach", "wallet"]),
});

/**
 * Pay a statement. Wallet payments settle immediately (live: wallet_post_entry
 * + record_membership_payment); card/ACH return a Stripe Checkout URL whose
 * PaymentIntent is recorded by the Stripe webhook.
 */
export async function POST(req: Request) {
  return handleCredit(async () => {
    const user = await requireRole("member", "worker", "admin");
    const body = Body.parse(await req.json());
    return payStatement(user, body);
  });
}
