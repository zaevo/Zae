"use client";

import { useEffect, useState } from "react";
import { Gift, Share2 } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Card, CardTitle } from "@/components/ui/Card";
import type { ReferralRecord } from "@/lib/credit/engine";
import { CopyButton } from "./CopyButton";

export function ReferralCard({
  link,
  rewardMonths,
  referrals,
  freeMonthsRemaining,
}: {
  link: string | null;
  rewardMonths: number;
  referrals: ReferralRecord[];
  freeMonthsRemaining: number;
}) {
  const [shareError, setShareError] = useState(false);
  // Decided after mount so server and client render the same markup.
  const [canShare, setCanShare] = useState(false);
  useEffect(() => setCanShare(typeof navigator.share === "function"), []);
  const reward = `${rewardMonths} free month${rewardMonths === 1 ? "" : "s"}`;
  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>Invite friends</CardTitle>
        <Gift size={18} aria-hidden className="text-accent" />
      </div>
      <p className="mt-2 font-semibold">Get {reward} for every friend</p>
      <p className="mt-1 text-sm text-muted">When a friend you invite makes their first on-time payment, your next membership fee is on us.</p>
      {freeMonthsRemaining > 0 ? (
        <p className="mt-2 text-sm">
          <span className="font-semibold text-positive">
            {freeMonthsRemaining} free month{freeMonthsRemaining === 1 ? "" : "s"}
          </span>{" "}
          banked for your next statement{freeMonthsRemaining === 1 ? "" : "s"}.
        </p>
      ) : null}

      {link ? (
        <div className="mt-4 space-y-2">
          <label className="block text-xs font-medium text-muted" htmlFor="referral-link">
            Your invite link
          </label>
          <input
            id="referral-link"
            readOnly
            value={link}
            onFocus={(e) => e.currentTarget.select()}
            className="w-full truncate rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm"
          />
          <div className="flex flex-wrap gap-2">
            <CopyButton text={link} label="Copy link" />
            {canShare ? (
              <button
                type="button"
                onClick={async () => {
                  setShareError(false);
                  try {
                    await navigator.share({ title: "EzWerkz", text: "I'm building credit with EzWerkz. Join with my link:", url: link });
                  } catch (err) {
                    if ((err as DOMException).name !== "AbortError") setShareError(true);
                  }
                }}
                className="inline-flex items-center gap-1.5 rounded-full bg-surface-2 px-3 py-1.5 text-xs font-semibold transition hover:bg-line focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                <Share2 size={14} aria-hidden /> Share
              </button>
            ) : null}
          </div>
          {shareError ? (
            <p role="alert" className="text-xs text-danger">
              Sharing didn&apos;t work. Copy the link instead.
            </p>
          ) : null}
        </div>
      ) : null}

      {referrals.length ? (
        <ul className="mt-4 divide-y divide-line border-t border-line">
          {referrals.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
              <span>{r.referredName}</span>
              {r.status === "qualified" ? (
                <Badge tone="positive">+{r.rewardMonths} free month{r.rewardMonths === 1 ? "" : "s"}</Badge>
              ) : (
                <Badge>Waiting for first payment</Badge>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
