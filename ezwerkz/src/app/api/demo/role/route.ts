import { NextResponse } from "next/server";
import { z } from "zod";
import { DEMO_ROLE_COOKIE } from "@/lib/auth";
import { isDemoMode } from "@/lib/env";

const Body = z.object({ role: z.enum(["member", "worker", "client_manager", "admin"]) });

export async function POST(req: Request) {
  if (!isDemoMode()) return NextResponse.json({ error: "Demo mode is off" }, { status: 404 });
  const parsed = Body.safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "Invalid role" }, { status: 400 });
  const res = NextResponse.json({ ok: true });
  res.cookies.set(DEMO_ROLE_COOKIE, parsed.data.role, { path: "/", sameSite: "lax", httpOnly: true });
  return res;
}
