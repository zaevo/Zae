/**
 * Pure rules for virtual cards: status transitions, spend limits and expiry.
 * The database enforces the same invariants (a canceled card can never be
 * reactivated); these give users a friendly answer before we call the issuer.
 */
import type { CardAction, CardKind, CardStatus } from "./types";

/** Product guardrails (not prices), so they live here rather than in @/lib/pricing. */
export const CARD_RULES = {
  maxOpenCards: 5,
  minSpendLimitCents: 1_00,
  maxSpendLimitCents: 5_000_00,
  temporaryMinHours: 1,
  temporaryMaxDays: 90,
  temporaryDefaultDays: 7,
  nicknameMaxLength: 40,
} as const;

export type TransitionResult =
  | { ok: true; status: CardStatus; changed: boolean }
  | { ok: false; code: "CARD_CANCELED" | "INVALID_TRANSITION"; message: string };

const TARGET: Record<CardAction, CardStatus> = { freeze: "frozen", unfreeze: "active", cancel: "canceled" };

/** Idempotent: freezing a frozen card is a no-op success, so retries are safe. */
export function nextCardStatus(current: CardStatus, action: CardAction): TransitionResult {
  if (current === "canceled") {
    return { ok: false, code: "CARD_CANCELED", message: "This card is canceled. Create a new card instead." };
  }
  const target = TARGET[action];
  return { ok: true, status: target, changed: target !== current };
}

export function isCardExpired(card: { kind: CardKind; expiresAt: string | null }, now: Date = new Date()): boolean {
  return card.kind === "temporary" && card.expiresAt !== null && Date.parse(card.expiresAt) <= now.getTime();
}

export function countsTowardCardLimit(card: { status: CardStatus; kind: CardKind; expiresAt: string | null }, now: Date = new Date()): boolean {
  return card.status !== "canceled" && !isCardExpired(card, now);
}

export type Validation<T> = { ok: true; value: T } | { ok: false; message: string };

export function validateSpendLimit(cents: number | null | undefined): Validation<number | null> {
  if (cents === null || cents === undefined) return { ok: true, value: null };
  if (!Number.isInteger(cents)) return { ok: false, message: "Spend limit must be a whole number of cents." };
  if (cents < CARD_RULES.minSpendLimitCents || cents > CARD_RULES.maxSpendLimitCents) {
    return { ok: false, message: "Spend limit is outside the allowed range." };
  }
  return { ok: true, value: cents };
}

/**
 * Temporary cards need an expiry between 1 hour and 90 days out; other kinds
 * must not have one. Returns the normalized ISO string (or null).
 */
export function resolveExpiry(kind: CardKind, expiresAt: string | null | undefined, now: Date = new Date()): Validation<string | null> {
  if (kind !== "temporary") {
    return expiresAt ? { ok: false, message: "Only temporary cards have an expiry date." } : { ok: true, value: null };
  }
  if (!expiresAt) return { ok: false, message: "Choose when this temporary card should expire." };
  const at = Date.parse(expiresAt);
  if (Number.isNaN(at)) return { ok: false, message: "Expiry date is not valid." };
  const min = now.getTime() + CARD_RULES.temporaryMinHours * 3_600_000;
  const max = now.getTime() + CARD_RULES.temporaryMaxDays * 86_400_000;
  if (at < min) return { ok: false, message: "Expiry must be at least an hour from now." };
  if (at > max) return { ok: false, message: `Temporary cards can last up to ${CARD_RULES.temporaryMaxDays} days.` };
  return { ok: true, value: new Date(at).toISOString() };
}

/**
 * Which window a spend limit applies to at the issuer. Permanent cards reset
 * monthly; single-use and temporary cards get a lifetime cap.
 */
export function spendLimitWindow(kind: CardKind): "monthly" | "all_time" {
  return kind === "permanent" ? "monthly" : "all_time";
}

/**
 * Single-use cards always carry a cap at the issuer, so a leaked number can't
 * be drained between the first charge and our auto-cancel.
 */
export function effectiveSpendLimit(kind: CardKind, cents: number | null): number | null {
  if (cents !== null) return cents;
  return kind === "single_use" ? CARD_RULES.maxSpendLimitCents : null;
}
