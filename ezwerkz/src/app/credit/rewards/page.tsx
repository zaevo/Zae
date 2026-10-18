import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { HeartHandshake } from "lucide-react";
import { getSessionUser } from "@/lib/auth";
import { env } from "@/lib/env";
import { formatCents } from "@/lib/money";
import { CREDIT, MEMBERSHIP_SPLIT, REFERRAL } from "@/lib/pricing";
import { getCreditSummary, getImpactSummary } from "@/lib/credit/queries";
import { referralLink } from "@/lib/credit/summary";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { AddonsList } from "@/components/credit/AddonsList";
import { BadgesGrid } from "@/components/credit/BadgesGrid";
import { CreditNotAvailable, CreditNotEnrolled, canUseCredit } from "@/components/credit/CreditGate";
import { MembershipCard } from "@/components/credit/MembershipCard";
import { ReferralCard } from "@/components/credit/ReferralCard";
import { StreakCalendar } from "@/components/credit/StreakCalendar";
import { StreakCard } from "@/components/credit/StreakCard";

export const metadata: Metadata = { title: "Rewards" };
export const dynamic = "force-dynamic";

export default async function RewardsPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  if (!canUseCredit(user)) return <CreditNotAvailable />;

  const summary = await getCreditSummary(user);
  if (!summary.enrolled || !summary.line || !summary.membership) {
    return (
      <>
        <PageHeader eyebrow="Credit Builder" title="Rewards" />
        <CreditNotEnrolled />
      </>
    );
  }
  // Impact copy only exists when the split is on and real allocations exist.
  const impact = MEMBERSHIP_SPLIT.impactCents > 0 ? await getImpactSummary(user) : null;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Credit Builder" title="Rewards" subtitle="Celebrate your progress, invite friends, and manage your plan." />

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="min-w-0 space-y-6">
          <StreakCard summary={summary} />
          <BadgesGrid badges={summary.badges} />
          <StreakCalendar history={summary.history} />
        </div>
        <div className="min-w-0 space-y-6">
          <ReferralCard
            link={summary.referral.code ? referralLink(env.appUrl, summary.referral.code) : null}
            rewardMonths={REFERRAL.rewardMonths}
            referrals={summary.referral.referrals}
            freeMonthsRemaining={summary.referral.freeMonthsRemaining}
          />
          <AddonsList addons={summary.addons} membershipActive={summary.membership.status === "active"} />
          <MembershipCard
            status={summary.membership.status}
            feeCents={CREDIT.membershipFeeCents}
            startedAt={summary.membership.startedAt}
            canceledAt={summary.membership.canceledAt}
            balanceCents={summary.line.balanceCents}
            lineOpen={summary.line.status === "open"}
          />
          {impact ? (
            <Card className="flex items-start gap-3">
              <HeartHandshake size={20} aria-hidden className="mt-0.5 shrink-0 text-accent" />
              <p className="text-sm">
                {formatCents(impact.totalImpactCents)} of your membership payments has gone to {impact.partnerName}.
              </p>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}
