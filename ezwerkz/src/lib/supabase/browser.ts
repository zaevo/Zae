"use client";

import { createBrowserClient } from "@supabase/ssr";

/** Browser Supabase client (anon key + user session; RLS applies). */
export function createSupabaseBrowserClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "",
  );
}
