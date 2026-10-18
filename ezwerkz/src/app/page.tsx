import { redirect } from "next/navigation";
import { ArrowRight, Briefcase, CreditCard, Gauge, Repeat, Zap } from "lucide-react";
import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { getSessionUser } from "@/lib/auth";
import { CREDIT, TIER_RATES } from "@/lib/pricing";
import { formatCents } from "@/lib/money";

const DOORS = [
  {
    href: "/credit",
    icon: Gauge,
    title: "Credit Builder",
    body: `A ${formatCents(CREDIT.defaultLimitCents)} store credit line reported to the bureaus. ${formatCents(CREDIT.membershipFeeCents)}/mo, cancel any time.`,
    roles: ["member", "worker", "admin"],
  },
  {
    href: "/wallet",
    icon: CreditCard,
    title: "Wallet & Cards",
    body: "Same-day shift pay lands here. Spin up virtual cards for subscriptions or one-time buys.",
    roles: ["member", "worker", "admin"],
  },
  {
    href: "/shifts",
    icon: Zap,
    title: "Pick up shifts",
    body: `Emergency call-outs near you from ${formatCents(TIER_RATES[1].payRateCents)}/hr. Get certified for ${formatCents(TIER_RATES[2].payRateCents)}/hr.`,
    roles: ["worker", "admin"],
  },
  {
    href: "/business",
    icon: Briefcase,
    title: "Fill a call-out",
    body: "Post an urgent shift and vetted local stand-ins get a text in seconds.",
    roles: ["client_manager", "admin"],
  },
] as const;

export default async function Home() {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  const doors = DOORS.filter((d) => (d.roles as readonly string[]).includes(user.role));
  const firstName = user.fullName.split(" ")[0];

  return (
    <div className="space-y-8">
      <section>
        <p className="text-sm text-muted">Good to see you,</p>
        <h1 className="text-3xl font-bold tracking-tight">{firstName}</h1>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        {doors.map(({ href, icon: Icon, title, body }) => (
          <Link key={href} href={href} className="group">
            <Card className="h-full transition group-hover:-translate-y-0.5 group-hover:shadow-md">
              <div className="flex items-start justify-between">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-accent to-accent-2 text-white">
                  <Icon size={20} aria-hidden />
                </span>
                <ArrowRight size={18} className="text-muted transition group-hover:translate-x-0.5" aria-hidden />
              </div>
              <h2 className="mt-4 text-lg font-semibold">{title}</h2>
              <p className="mt-1 text-sm text-muted">{body}</p>
            </Card>
          </Link>
        ))}
      </section>

      {user.role !== "client_manager" ? (
        <Card className="bg-gradient-to-br from-accent to-accent-2 text-white">
          <div className="flex items-center gap-2">
            <Repeat size={18} aria-hidden />
            <Badge className="bg-white/20 text-white">Self-funding</Badge>
          </div>
          <h2 className="mt-3 text-xl font-semibold">Let your shifts pay for your credit</h2>
          <p className="mt-1 max-w-xl text-sm text-white/85">
            Work a shift, get paid to your Wallet the same day, and turn on Autopay so your{" "}
            {formatCents(CREDIT.membershipFeeCents)} membership is covered from your balance. You choose this and can
            switch it off any time in Wallet → Autopay.
          </p>
        </Card>
      ) : null}
    </div>
  );
}
