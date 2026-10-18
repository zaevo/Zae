import type { ReactNode } from "react";
import { getSessionUser } from "@/lib/auth";
import { CreditTabs } from "@/components/credit/CreditTabs";
import { canUseCredit } from "@/components/credit/CreditGate";

export default async function CreditLayout({ children }: { children: ReactNode }) {
  const user = await getSessionUser();
  return (
    <div>
      {user && canUseCredit(user) ? <CreditTabs /> : null}
      {children}
    </div>
  );
}
