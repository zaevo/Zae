import { z } from "zod";
import { requireRole } from "@/lib/auth";
import { handleCredit } from "@/lib/credit/errors";
import { exportMetro2 } from "@/lib/credit/metro2Export";

export const runtime = "nodejs";

const Body = z.object({
  periodEnd: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Use YYYY-MM-DD"),
  deliver: z.boolean().optional().default(false),
});

/**
 * Admin only. Builds the Metro 2 file for a period and records it in
 * metro2_exports. The file is prepared for delivery to a credentialed
 * furnisher partner, who validates against the current CRRG; with
 * `deliver: true` it is sent to that partner (never to the bureaus).
 * Responses include only a redacted preview — never SSNs.
 */
export async function POST(req: Request) {
  return handleCredit(async () => {
    const admin = await requireRole("admin");
    const body = Body.parse(await req.json());
    return { export: await exportMetro2(admin, body) };
  });
}
