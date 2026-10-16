import { cookies } from "next/headers";
import { isDemoMode } from "@/lib/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import type { ModuleKey, Role, SessionUser } from "@/lib/types";

export const DEMO_ROLE_COOKIE = "ss_demo_role";
const ROLES: Role[] = ["member", "worker", "client_manager", "admin"];

export const DEMO_USERS: Record<Role, SessionUser> = {
  member: {
    id: "00000000-0000-4000-8000-000000000001",
    email: "maya@example.com",
    fullName: "Maya Johnson",
    role: "member",
    organizationId: null,
    modules: ["credit", "wallet"],
    demo: true,
  },
  worker: {
    id: "00000000-0000-4000-8000-000000000002",
    email: "devon@example.com",
    fullName: "Devon Carter",
    role: "worker",
    organizationId: null,
    modules: ["credit", "wallet", "shifts"],
    demo: true,
  },
  client_manager: {
    id: "00000000-0000-4000-8000-000000000003",
    email: "store1142@example.com",
    fullName: "Priya Patel",
    role: "client_manager",
    organizationId: "00000000-0000-4000-8000-0000000000c1",
    modules: ["shifts"],
    demo: true,
  },
  admin: {
    id: "00000000-0000-4000-8000-000000000004",
    email: "ops@shiftsave.example",
    fullName: "ShiftSave Ops",
    role: "admin",
    organizationId: null,
    modules: ["credit", "wallet", "shifts"],
    demo: true,
  },
};

/** The signed-in user, or null. In demo mode the role comes from a cookie (default: worker). */
export async function getSessionUser(): Promise<SessionUser | null> {
  if (isDemoMode()) {
    const store = await cookies();
    const raw = store.get(DEMO_ROLE_COOKIE)?.value as Role | undefined;
    return DEMO_USERS[raw && ROLES.includes(raw) ? raw : "worker"];
  }
  const supabase = await createSupabaseServerClient();
  const { data: auth } = await supabase.auth.getUser();
  if (!auth.user) return null;
  const { data: profile } = await supabase
    .from("users")
    .select("id, email, full_name, role, organization_id, user_modules(module)")
    .eq("id", auth.user.id)
    .single();
  if (!profile) return null;
  const modules = ((profile.user_modules as { module: ModuleKey }[] | null) ?? []).map((m) => m.module);
  return {
    id: profile.id,
    email: profile.email,
    fullName: profile.full_name,
    role: profile.role as Role,
    organizationId: profile.organization_id,
    modules,
    demo: false,
  };
}

export class AuthError extends Error {
  constructor(public status: 401 | 403, message: string) {
    super(message);
  }
}

/** Throws AuthError unless the signed-in user has one of the given roles. */
export async function requireRole(...roles: Role[]): Promise<SessionUser> {
  const user = await getSessionUser();
  if (!user) throw new AuthError(401, "Sign in required");
  if (roles.length && !roles.includes(user.role)) throw new AuthError(403, "Not allowed for your role");
  return user;
}
