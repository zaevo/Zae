import { NextResponse } from "next/server";
import { requireRole } from "@/lib/auth";
import { env } from "@/lib/env";
import { handleCredit } from "@/lib/credit/errors";
import { recordOfferClick } from "@/lib/credit/service";

/** Record an affiliate click, then redirect to the offer's stored URL (never a caller-supplied one). */
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  return handleCredit(async () => {
    const user = await requireRole("member", "worker", "admin");
    const { id } = await params;
    const url = await recordOfferClick(user, id);
    return NextResponse.redirect(url ?? new URL("/credit", env.appUrl), 303);
  });
}
