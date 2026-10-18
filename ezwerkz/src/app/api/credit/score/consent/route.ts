import { z } from "zod";
import { requireRole } from "@/lib/auth";
import { clientIp } from "@/lib/http";
import { handleCredit } from "@/lib/credit/errors";
import { recordSoftPullConsent } from "@/lib/credit/service";

const Body = z.object({ accepted: z.literal(true) });

/** Record the member's consent to a soft inquiry (no score impact) by our score partner. */
export async function POST(req: Request) {
  return handleCredit(async () => {
    const user = await requireRole("member", "worker", "admin");
    Body.parse(await req.json());
    return recordSoftPullConsent(user, { ipAddress: clientIp(req), userAgent: req.headers.get("user-agent") });
  });
}
