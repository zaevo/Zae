"use client";

import { useRouter } from "next/navigation";
import { useId, useState, useTransition } from "react";
import { LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { errorMessage, sendJson } from "./api";

/** Standalone soft-inquiry consent: full text, an unchecked box, then the action. */
export function SoftPullConsent({ title, body, version }: { title: string; body: string[]; version: string }) {
  const router = useRouter();
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const textId = useId();

  return (
    <div className="mt-3 space-y-3">
      <div id={textId} className="max-h-40 space-y-2 overflow-y-auto rounded-2xl bg-surface-2 p-3 text-xs text-muted" tabIndex={0} aria-label={title}>
        <p className="font-semibold text-ink">{title}</p>
        {body.map((p, i) => (
          <p key={i}>{p}</p>
        ))}
        <p className="text-[11px]">Version {version}</p>
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          aria-describedby={textId}
          className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-accent)]"
        />
        <span>I agree to a soft inquiry so EzWerkz can show my score. This doesn&apos;t affect my score.</span>
      </label>
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
      <Button
        disabled={!agreed || pending}
        onClick={() =>
          start(async () => {
            setError(null);
            try {
              await sendJson("/api/credit/score/consent", { method: "POST", body: { accepted: true } });
              router.refresh();
            } catch (err) {
              setError(errorMessage(err));
            }
          })
        }
        className="w-full"
      >
        {pending ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : null}
        Check my score
      </Button>
    </div>
  );
}
