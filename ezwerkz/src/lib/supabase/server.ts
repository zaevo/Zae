import { createServerClient } from "@supabase/ssr";
import { createClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";
import { env, requireEnv } from "@/lib/env";

/** Supabase client bound to the signed-in user's session (RLS applies). */
export async function createSupabaseServerClient() {
  const cookieStore = await cookies();
  return createServerClient(env.supabaseUrl, env.supabaseAnonKey, {
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll: (toSet) => {
        try {
          toSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
        } catch {
          // Called from a Server Component: cookies are read-only there; the proxy refreshes them.
        }
      },
    },
  });
}

/**
 * Service-role client that BYPASSES RLS. Server-only: use it for webhooks
 * (Twilio, Stripe), cron jobs and admin actions after you have checked the
 * caller's role yourself. Never import this from a client component.
 */
export function createSupabaseServiceClient() {
  return createClient(env.supabaseUrl, requireEnv("supabaseServiceRoleKey"), {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
