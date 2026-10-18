import { NextResponse } from "next/server";
import { handle } from "@/lib/http";
import { IssuingError } from "@/lib/integrations/issuing";

export type WalletErrorCode =
  | "NOT_FOUND"
  | "WALLET_NOT_FOUND"
  | "WALLET_INACTIVE"
  | "INSUFFICIENT_FUNDS"
  | "CARD_CANCELED"
  | "CARD_LIMIT_REACHED"
  | "INVALID_REQUEST"
  | "BILLING_ADDRESS_REQUIRED"
  | "CONSENT_VERSION_MISMATCH"
  | "AUTOPAY_NOT_ACTIVE"
  | "FORBIDDEN"
  | "UNAUTHORIZED"
  | "ISSUER_NOT_CONFIGURED"
  | "ISSUER_ERROR"
  | "DATABASE_ERROR";

/** A failure with a stable code and a message that is safe to show the member. */
export class WalletError extends Error {
  constructor(
    public readonly code: WalletErrorCode,
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "WalletError";
  }
}

interface DbError {
  message: string;
  code?: string;
  details?: string | null;
}

/** Map the RAISE codes from supabase/migrations/0002_wallet.sql to friendly API errors. */
export function walletDbError(error: DbError, fallback = "Something went wrong with your Wallet. Please try again."): WalletError {
  const m = error.message;
  if (m.includes("INSUFFICIENT_FUNDS")) return new WalletError("INSUFFICIENT_FUNDS", "Your Wallet balance is too low.", 402);
  if (m.includes("WALLET_FROZEN") || m.includes("WALLET_CLOSED")) return new WalletError("WALLET_INACTIVE", "Your Wallet isn't active right now.", 409);
  if (m.includes("CARD_CANCELED")) return new WalletError("CARD_CANCELED", "This card is canceled. Create a new card instead.", 409);
  if (m.includes("WALLET_NOT_FOUND")) return new WalletError("WALLET_NOT_FOUND", "We couldn't find your Wallet.", 404);
  if (m.includes("FORBIDDEN") || error.code === "42501") return new WalletError("FORBIDDEN", "You can't do that with this Wallet.", 403);
  // Log the database message server-side only; it never contains card numbers (none are stored).
  console.error("[wallet] database error", { code: error.code, message: m });
  return new WalletError("DATABASE_ERROR", fallback, 500);
}

/** handle() plus WalletError/IssuingError → { error, message } JSON with the right status. */
export function walletHandle<T>(fn: () => Promise<T>): Promise<NextResponse> {
  return handle(async () => {
    try {
      return await fn();
    } catch (err) {
      if (err instanceof WalletError) {
        return NextResponse.json({ error: err.code, message: err.message }, { status: err.status });
      }
      if (err instanceof IssuingError) {
        const status = err.code === "BILLING_ADDRESS_REQUIRED" ? 422 : err.code === "NOT_CONFIGURED" ? 503 : 502;
        const code = err.code === "BILLING_ADDRESS_REQUIRED" ? "BILLING_ADDRESS_REQUIRED" : err.code === "NOT_CONFIGURED" ? "ISSUER_NOT_CONFIGURED" : "ISSUER_ERROR";
        return NextResponse.json({ error: code, message: err.publicMessage }, { status });
      }
      throw err;
    }
  });
}
