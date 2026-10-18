"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { CircleCheck, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { formatCents } from "@/lib/money";
import { Sheet } from "./Sheet";
import { errorMessage, sendJson } from "./api";

interface PurchaseResponse {
  balanceCents: number;
  availableCents: number;
}

/** Confirm-then-charge to the credit line. The server re-checks available credit. */
export function BuyButton({
  product,
  availableCents,
  disabledReason,
}: {
  product: { id: string; name: string; priceCents: number; fulfillment: "digital" | "shipped" };
  availableCents: number;
  disabledReason: string | null;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<PurchaseResponse | null>(null);
  const [pending, start] = useTransition();

  const close = () => {
    setOpen(false);
    if (done) router.refresh();
    setDone(null);
    setError(null);
  };

  return (
    <>
      <Button
        variant="secondary"
        disabled={Boolean(disabledReason)}
        onClick={() => setOpen(true)}
        className="w-full"
        aria-describedby={disabledReason ? `why-${product.id}` : undefined}
      >
        {formatCents(product.priceCents)} · Buy
      </Button>
      {disabledReason ? (
        <p id={`why-${product.id}`} className="mt-1.5 text-center text-xs text-muted">
          {disabledReason}
        </p>
      ) : null}
      <Sheet open={open} onClose={close} title={done ? "Purchase complete" : "Confirm purchase"}>
        {done ? (
          <div className="space-y-4 text-center" role="status">
            <CircleCheck size={40} aria-hidden className="mx-auto text-positive" />
            <p className="text-sm text-muted">
              Order confirmed: {product.name}. It&apos;s on your credit line and will show on your next statement. You have{" "}
              {formatCents(done.availableCents)} available.
            </p>
            <Button onClick={close} className="w-full">
              Done
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <dl className="space-y-2 rounded-2xl bg-surface-2 p-4 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Item</dt>
                <dd className="text-right font-medium">{product.name}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Charged to your credit line</dt>
                <dd className="font-semibold">{formatCents(product.priceCents)}</dd>
              </div>
              <div className="flex justify-between gap-4 border-t border-line pt-2">
                <dt className="text-muted">Available after</dt>
                <dd className="font-medium">{formatCents(availableCents - product.priceCents)}</dd>
              </div>
            </dl>
            <p className="text-xs text-muted">It will appear on your next statement. Paying the statement in full by the due date keeps it on-time.</p>
            {error ? (
              <p role="alert" className="rounded-2xl bg-danger/10 p-3 text-sm text-danger">
                {error}
              </p>
            ) : null}
            <Button
              disabled={pending}
              className="w-full"
              onClick={() =>
                start(async () => {
                  setError(null);
                  try {
                    setDone(await sendJson<PurchaseResponse>("/api/credit/store/purchase", { method: "POST", body: { productId: product.id } }));
                  } catch (err) {
                    setError(errorMessage(err));
                  }
                })
              }
            >
              {pending ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : null}
              Buy for {formatCents(product.priceCents)}
            </Button>
          </div>
        )}
      </Sheet>
    </>
  );
}
