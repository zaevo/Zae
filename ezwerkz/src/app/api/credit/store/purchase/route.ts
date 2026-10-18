import { z } from "zod";
import { requireRole } from "@/lib/auth";
import { handleCredit } from "@/lib/credit/errors";
import { purchaseProduct } from "@/lib/credit/service";

const Body = z.object({ productId: z.string().min(1).max(100) });

/** Spend the credit line in the EzWerkz store. Never exceeds available credit. */
export async function POST(req: Request) {
  return handleCredit(async () => {
    const user = await requireRole("member", "worker", "admin");
    const { productId } = Body.parse(await req.json());
    return purchaseProduct(user, productId);
  });
}
