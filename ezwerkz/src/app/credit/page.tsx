import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/auth";
import { getCreditSummary } from "@/lib/credit/queries";
import { getWalletSummary } from "@/lib/wallet/queries";
import type { SessionUser } from "@/lib/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { CreditLineCard } from "@/components/credit/CreditLineCard";
import { CreditNotAvailable, CreditNotEnrolled, canUseCredit } from "@/components/credit/CreditGate";
import { OffersWidget } from "@/components/credit/OffersWidget";
import { PaymentHistoryDots } from "@/components/credit/PaymentHistoryDots";
import type { PayNowWallet } from "@/components/credit/PayNowSheet";
import { ScoreTile } from "@/components/credit/ScoreTile";
import { StatementCard } from "@/components/credit/StatementCard";
import { StreakCard } from "@/components/credit/StreakCard";

export const metadata: Metadata = { title: "Credit Builder" };
export const dynamic = "force-dynamic";

async function walletFor(user: SessionUser): Promise<PayNowWallet | null> {
  try {
    const { wallet, autopayActive } = await getWalletSummary(user);
    return { availableCents: wallet.availableCents, autopayActive, active: wallet.status === "active" };
  } catch {
    // The credit page still works without the Wallet module; Pay now falls back to card/ACH.
    return null;
  }
}

const PAYMENT_NOTICES: Record<string, { tone: "positive" | "neutral"; text: string }> = {
  processing: { tone: "positive", text: "Thanks! Your payment is processing. We'll update your statement as soon as it settles." },
  canceled: { tone: "neutral", text: "Checkout was canceled. Nothing was charged." },
};

export default async function CreditPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  if (!canUseCredit(user)) return <CreditNotAvailable />;

  const [summary, wallet, params] = await Promise.all([getCreditSummary(user), walletFor(user), searchParams]);
  const notice = typeof params.payment === "string" ? PAYMENT_NOTICES[params.payment] : undefined;

  if (!summary.enrolled) {
    return (
      <>
        <PageHeader eyebrow="Credit Builder" title="Build credit with every on-time payment" />
        <CreditNotEnrolled />
      </>
    );
  }

  const canceled = summary.membership?.status === "canceled";

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Credit Builder"
        title="Your credit line"
        subtitle="Spend it in the EzWerkz store, pay it off each month, and we report your payments through our credentialed furnisher partner."
      />

      {notice ? (
        <p
          role="status"
          className={notice.tone === "positive" ? "rounded-2xl bg-positive/10 p-3 text-sm text-positive" : "rounded-2xl bg-surface-2 p-3 text-sm text-muted"}
        >
          {notice.text}
        </p>
      ) : null}

      {canceled ? (
        <p className="rounded-2xl bg-warning/10 p-3 text-sm text-ink">
          Your membership is canceled, so there are no more monthly fees.
          {summary.line && summary.line.balanceCents > 0 ? " Your line closes once the remaining balance is paid." : ""}
        </p>
      ) : null}

      {/* DOM order is the mobile reading order; on wide screens score and streak move to a side column. */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem] xl:items-start">
        <div className="min-w-0 xl:col-start-1 xl:row-start-1">
          <CreditLineCard summary={summary} />
        </div>
        <div className="min-w-0 xl:col-start-1 xl:row-start-2">
          <StatementCard summary={summary} wallet={wallet} />
        </div>
        <div className="min-w-0 xl:col-start-2 xl:row-start-1">
          <ScoreTile summary={summary} />
        </div>
        <div className="min-w-0 xl:col-start-1 xl:row-start-3">
          <PaymentHistoryDots history={summary.history} />
        </div>
        <div className="min-w-0 xl:col-start-2 xl:row-start-2 xl:row-span-2">
          <StreakCard summary={summary} />
        </div>
      </div>

      <OffersWidget summary={summary} />
    </div>
  );
}
