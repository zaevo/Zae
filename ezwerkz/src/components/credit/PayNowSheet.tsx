"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { CreditCard, Landmark, LoaderCircle, PartyPopper, Wallet } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { formatCents } from "@/lib/money";
import { BADGES, type BadgeKey } from "@/lib/credit/engine";
import { Sheet } from "./Sheet";
import { errorMessage, sendJson } from "./api";
import { formatLongDate, formatShortDate } from "./format";

type Method = "wallet" | "card" | "ach";

type PayResponse =
  | { kind: "paid"; paymentId: string; amountCents: number; status: "succeeded" | "pending" | "failed"; newBadges: BadgeKey[]; leveledUp: boolean; streak: number }
  | { kind: "redirect"; checkoutUrl: string; amountCents: number };

export interface PayNowStatement {
  id: string;
  periodStart: string;
  periodEnd: string;
  dueDate: string;
  amountCents: number;
}

export interface PayNowWallet {
  availableCents: number;
  autopayActive: boolean;
  active: boolean;
}

export function PayNowSheet({ statement, wallet }: { statement: PayNowStatement; wallet: PayNowWallet | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const walletUsable = Boolean(wallet && wallet.active && wallet.availableCents >= statement.amountCents);
  const [method, setMethod] = useState<Method>(walletUsable ? "wallet" : "card");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Extract<PayResponse, { kind: "paid" }> | null>(null);
  const [pending, start] = useTransition();

  const close = () => {
    setOpen(false);
    if (result) router.refresh();
    setResult(null);
    setError(null);
  };

  const pay = () => {
    setError(null);
    start(async () => {
      try {
        const res = await sendJson<PayResponse>("/api/credit/pay", { method: "POST", body: { statementId: statement.id, method } });
        if (res.kind === "redirect") {
          window.location.assign(res.checkoutUrl);
          return;
        }
        setResult(res);
      } catch (err) {
        setError(errorMessage(err));
      }
    });
  };

  const options: Array<{ value: Method; label: string; hint: string; icon: typeof Wallet; disabled: boolean }> = [
    {
      value: "wallet",
      label: "EzWerkz Wallet",
      hint: wallet
        ? wallet.active
          ? `${formatCents(wallet.availableCents)} available${walletUsable ? "" : " — not enough for this payment"}`
          : "Wallet isn't active"
        : "Wallet unavailable",
      icon: Wallet,
      disabled: !walletUsable,
    },
    { value: "card", label: "Card", hint: "Debit or credit card, settles right away", icon: CreditCard, disabled: false },
    { value: "ach", label: "Bank transfer (ACH)", hint: "Usually 1–3 business days", icon: Landmark, disabled: false },
  ];

  return (
    <>
      <Button onClick={() => setOpen(true)} className="w-full sm:w-auto">
        Pay now
      </Button>
      <Sheet
        open={open}
        onClose={close}
        title={result ? "Payment received" : `Pay ${formatCents(statement.amountCents)}`}
        description={
          result ? undefined : (
            <>
              Statement {formatShortDate(statement.periodStart)} – {formatShortDate(statement.periodEnd)} · due {formatLongDate(statement.dueDate)}
            </>
          )
        }
      >
        {result ? (
          <div className="space-y-4 text-center" role="status">
            <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-positive/15 text-positive">
              <PartyPopper size={26} aria-hidden />
            </span>
            {result.status === "pending" ? (
              <p className="text-sm text-muted">
                Your {formatCents(result.amountCents)} bank transfer is on its way. We&apos;ll mark the statement paid as soon as it settles,
                usually within 1–3 business days.
              </p>
            ) : (
              <p className="text-sm text-muted">
                Thanks! {formatCents(result.amountCents)} is paid.
                {result.streak > 1 ? ` That's ${result.streak} on-time payments in a row.` : ""}
              </p>
            )}
            {result.leveledUp ? (
              <p className="rounded-2xl bg-accent/10 p-3 text-sm font-medium text-accent">Your limit just leveled up. Nice work!</p>
            ) : null}
            {result.newBadges.length ? (
              <ul className="flex flex-wrap justify-center gap-2">
                {result.newBadges.map((b) => (
                  <li key={b} className="rounded-full bg-surface-2 px-3 py-1 text-xs font-semibold">
                    New badge: {BADGES[b].title}
                  </li>
                ))}
              </ul>
            ) : null}
            <Button onClick={close} className="w-full">
              Done
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <fieldset>
              <legend className="mb-2 text-sm font-medium">Pay with</legend>
              <div className="space-y-2">
                {options.map((o) => (
                  <label
                    key={o.value}
                    className={cn(
                      "flex cursor-pointer items-center gap-3 rounded-2xl border p-3 transition has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent",
                      method === o.value ? "border-accent bg-accent/5" : "border-line hover:bg-surface-2",
                      o.disabled && "cursor-not-allowed opacity-50 hover:bg-transparent",
                    )}
                  >
                    <input
                      type="radio"
                      name="pay-method"
                      value={o.value}
                      checked={method === o.value}
                      disabled={o.disabled}
                      onChange={() => setMethod(o.value)}
                      className="sr-only"
                    />
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface-2">
                      <o.icon size={18} aria-hidden />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold">{o.label}</span>
                      <span className="block text-xs text-muted">{o.hint}</span>
                    </span>
                    <span
                      aria-hidden
                      className={cn("h-4 w-4 shrink-0 rounded-full border-2", method === o.value ? "border-accent bg-accent shadow-[inset_0_0_0_3px_var(--color-surface)]" : "border-line")}
                    />
                  </label>
                ))}
              </div>
            </fieldset>

            {wallet ? (
              <p className="rounded-2xl bg-surface-2 p-3 text-xs text-muted">
                {wallet.autopayActive
                  ? "Autopay is on: we'll pay future statements from your Wallet on their due date. You can turn it off any time in Wallet."
                  : "Want this handled automatically? Turn on Autopay in Wallet to pay statements from your balance on the due date."}
              </p>
            ) : null}

            {error ? (
              <p role="alert" className="rounded-2xl bg-danger/10 p-3 text-sm text-danger">
                {error}
              </p>
            ) : null}

            <Button onClick={pay} disabled={pending} className="w-full">
              {pending ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : null}
              {pending ? "Processing…" : `Pay ${formatCents(statement.amountCents)}`}
            </Button>
            <p className="text-center text-xs text-muted">Card and bank details are entered on Stripe&apos;s secure checkout page.</p>
          </div>
        )}
      </Sheet>
    </>
  );
}
