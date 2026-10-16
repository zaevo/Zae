"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

export function LoginForm() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setState("sending");
        const supabase = createSupabaseBrowserClient();
        const { error } = await supabase.auth.signInWithOtp({
          email,
          options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
        });
        if (error) {
          setError(error.message);
          setState("error");
        } else {
          setState("sent");
        }
      }}
    >
      <label className="block text-sm font-medium">
        Email
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1 w-full rounded-xl border border-line bg-surface px-3 py-2.5 text-sm"
          autoComplete="email"
        />
      </label>
      <Button type="submit" className="w-full" disabled={state === "sending"}>
        {state === "sending" ? "Sending…" : "Email me a link"}
      </Button>
      {state === "sent" ? <p className="text-sm text-positive">Check your inbox for the sign-in link.</p> : null}
      {state === "error" ? <p className="text-sm text-danger">{error}</p> : null}
    </form>
  );
}
