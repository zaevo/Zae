"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/components/ui/cn";

const TABS = [
  { href: "/credit", label: "Overview" },
  { href: "/credit/store", label: "Store" },
  { href: "/credit/bills", label: "Bills" },
  { href: "/credit/rewards", label: "Rewards" },
] as const;

/** Segmented sub-navigation for the Credit Builder module. */
export function CreditTabs() {
  const pathname = usePathname();
  return (
    <nav aria-label="Credit Builder" className="-mx-4 mb-6 overflow-x-auto px-4 md:mx-0 md:px-0">
      <ul className="flex w-max gap-1 rounded-full bg-surface-2 p-1">
        {TABS.map((tab) => {
          const active = tab.href === "/credit" ? pathname === "/credit" : pathname.startsWith(tab.href);
          return (
            <li key={tab.href}>
              <Link
                href={tab.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "block rounded-full px-4 py-1.5 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
                  active ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink",
                )}
              >
                {tab.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
