import { NextResponse } from "next/server";
import { handle } from "@/lib/http";

export type CreditErrorCode =
  | "NOT_ENROLLED"
  | "NOT_FOUND"
  | "ALREADY_PAID"
  | "PAYMENT_PENDING"
  | "INSUFFICIENT_FUNDS"
  | "INSUFFICIENT_CREDIT"
  | "MEMBERSHIP_INACTIVE"
  | "LINE_NOT_OPEN"
  | "PAST_DUE"
  | "INVALID_PRICE"
  | "CONFLICT"
  | "ALREADY_ACTIVE"
  | "NOT_ACTIVE"
  | "CONSENT_REQUIRED"
  | "UPLOAD_INVALID"
  | "ANALYSIS_FAILED"
  | "PROVIDER_ERROR"
  | "NOT_CONFIGURED";

/** A user-facing failure with a stable code (for the UI) and an HTTP status. */
export class CreditActionError extends Error {
  constructor(
    public readonly code: CreditErrorCode,
    message: string,
    public readonly status: 400 | 402 | 403 | 404 | 409 | 413 | 415 | 422 | 502 | 503 = 400,
  ) {
    super(message);
    this.name = "CreditActionError";
  }
}

/** handle() plus CreditActionError → `{ error: code, message }` with its status. */
export function handleCredit<T>(fn: () => Promise<T>): Promise<NextResponse> {
  return handle(async () => {
    try {
      return await fn();
    } catch (err) {
      if (err instanceof CreditActionError) {
        return NextResponse.json({ error: err.code, message: err.message }, { status: err.status });
      }
      throw err;
    }
  });
}
