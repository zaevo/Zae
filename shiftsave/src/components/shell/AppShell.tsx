"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Briefcase, CreditCard, Gauge, House, ShieldCheck, Zap } from "lucide-react";
import { cn } from "@/components/ui/cn";
import type { NavItem } from "./nav";
import { RoleSwitcher } from "./RoleSwitcher";
import type { Role } from "@/lib/types";

const ICONS = {
  home: House,
  credit: Gauge,
  wallet: CreditCard,
  shifts: Zap,
  business: Briefcase,
  admin: ShieldCheck,
} as const;

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({
  nav,
  userName,
  role,
  demo,
  children,
}: {
  nav: NavItem[];
  userName: string;
  role: Role;
  demo: boolean;
  children: ReactNode;
}) {
  const pathname = usePathname();
  return (
    <div className="min-h-dvh md:flex">
      {/* Desktop side rail */}
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-line bg-surface px-4 py-6 md:flex">
        <Link href="/" className="mb-8 flex items-center gap-2 px-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-accent to-accent-2 text-sm font-black text-white">
            S
          </span>
          <span className="text-lg font-bold tracking-tight">ShiftSave</span>
        </Link>
        <nav className="flex flex-col gap-1">
          {nav.map((item) => {
            const Icon = ICONS[item.icon];
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition",
                  active ? "bg-surface-2 text-ink" : "text-muted hover:bg-surface-2 hover:text-ink",
                )}
              >
                <Icon size={18} aria-hidden />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto space-y-3 px-2">
          {demo ? <RoleSwitcher current={role} /> : null}
          <div className="text-xs text-muted">Signed in as {userName}</div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-canvas/85 px-4 py-3 backdrop-blur md:hidden">
          <Link href="/" className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent-2 text-xs font-black text-white">
              S
            </span>
            <span className="font-bold tracking-tight">ShiftSave</span>
          </Link>
          {demo ? <RoleSwitcher current={role} compact /> : null}
        </header>

        <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-28 pt-6 md:px-8 md:pb-12">{children}</main>

        {/* Mobile bottom tab bar */}
        <nav
          className="fixed inset-x-0 bottom-0 z-30 flex justify-around border-t border-line bg-surface/95 px-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-2 backdrop-blur md:hidden"
          aria-label="Primary"
        >
          {nav.map((item) => {
            const Icon = ICONS[item.icon];
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex min-w-14 flex-col items-center gap-0.5 rounded-xl px-2 py-1 text-[11px] font-medium",
                  active ? "text-accent" : "text-muted",
                )}
              >
                <Icon size={20} aria-hidden />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
