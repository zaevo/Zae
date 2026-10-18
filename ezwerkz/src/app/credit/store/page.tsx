import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { GraduationCap, HardHat, Package, Sparkles, Truck } from "lucide-react";
import { getSessionUser } from "@/lib/auth";
import { formatCents } from "@/lib/money";
import { getCreditSummary, listStoreProducts } from "@/lib/credit/queries";
import type { StoreProduct } from "@/lib/credit/summary";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatTile } from "@/components/ui/StatTile";
import { BuyButton } from "@/components/credit/BuyButton";
import { CreditNotAvailable, CreditNotEnrolled, canUseCredit } from "@/components/credit/CreditGate";

export const metadata: Metadata = { title: "Credit Store" };
export const dynamic = "force-dynamic";

const CATEGORY_ICON: Record<StoreProduct["category"], typeof Package> = {
  course: GraduationCap,
  gear: HardHat,
  digital: Sparkles,
};

export default async function CreditStorePage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  if (!canUseCredit(user)) return <CreditNotAvailable />;

  const [summary, products] = await Promise.all([getCreditSummary(user), listStoreProducts()]);
  if (!summary.enrolled || !summary.line) {
    return (
      <>
        <PageHeader eyebrow="Credit Builder" title="Store" />
        <CreditNotEnrolled />
      </>
    );
  }

  const blocked =
    summary.line.status !== "open"
      ? "Your credit line is closed."
      : summary.membership?.status !== "active"
        ? "Purchases need an active membership."
        : summary.hasPastDue
          ? "Pay your past-due statement first."
          : null;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Credit Builder"
        title="Store"
        subtitle="Use your credit line on things that help at work. Purchases go on your next statement; there's no interest."
      />

      <div className="grid grid-cols-2 gap-3">
        <StatTile label="Available credit" value={formatCents(summary.availableCents)} />
        <StatTile label="Credit limit" value={formatCents(summary.line.limitCents)} hint={`${formatCents(summary.line.balanceCents)} used`} />
      </div>

      {blocked ? (
        <p role="status" className="rounded-2xl bg-warning/10 p-3 text-sm">
          {blocked}
        </p>
      ) : null}

      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {products.map((p) => {
          const Icon = CATEGORY_ICON[p.category];
          const reason = blocked ?? (p.priceCents > summary.availableCents ? "More than your available credit" : null);
          return (
            <li key={p.id}>
              <Card className="flex h-full flex-col">
                <div className="flex items-start justify-between gap-3">
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent/10 text-accent">
                    <Icon size={20} aria-hidden />
                  </span>
                  <span className="text-lg font-semibold">{formatCents(p.priceCents)}</span>
                </div>
                <h2 className="mt-3 font-semibold">{p.name}</h2>
                <p className="mt-1 flex-1 text-sm text-muted">{p.description}</p>
                <p className="mt-3 flex items-center gap-1.5 text-xs text-muted">
                  {p.fulfillment === "shipped" ? <Truck size={14} aria-hidden /> : <Sparkles size={14} aria-hidden />}
                  {p.fulfillment === "shipped" ? "Ships free" : "Instant digital access"}
                </p>
                <div className="mt-4">
                  <BuyButton
                    product={{ id: p.id, name: p.name, priceCents: p.priceCents, fulfillment: p.fulfillment }}
                    availableCents={summary.availableCents}
                    disabledReason={reason}
                  />
                </div>
              </Card>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
