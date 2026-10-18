import Link from "next/link";
import { EmptyState } from "@/components/ui/EmptyState";
import { CREDIT } from "@/lib/pricing";
import { formatCents } from "@/lib/money";
import type { SessionUser } from "@/lib/types";
import { EnrollButton } from "./EnrollButton";

export const CREDIT_ROLES = ["member", "worker", "admin"] as const;

export function canUseCredit(user: SessionUser): boolean {
  return (CREDIT_ROLES as readonly string[]).includes(user.role);
}

/** Shown to business accounts, which don't have the Credit Builder. */
export function CreditNotAvailable() {
  return (
    <EmptyState
      title="Credit Builder is for personal accounts"
      body="Business manager accounts don't include a credit builder line."
      action={
        <Link href="/" className="text-sm font-semibold text-accent underline-offset-4 hover:underline">
          Back to home
        </Link>
      }
    />
  );
}

/** Shown to members who haven't opened a line yet. */
export function CreditNotEnrolled() {
  return (
    <EmptyState
      title="Open your credit builder line"
      body={`Get a ${formatCents(CREDIT.defaultLimitCents)} line you can spend in the EzWerkz store, reported monthly through our furnisher partner. ${formatCents(CREDIT.membershipFeeCents)}/month, cancel any time.`}
      action={<EnrollButton label="Open my line" />}
    />
  );
}
