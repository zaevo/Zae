import { describe, expect, it } from "vitest";
import {
  CARD_RULES,
  countsTowardCardLimit,
  effectiveSpendLimit,
  isCardExpired,
  nextCardStatus,
  resolveExpiry,
  spendLimitWindow,
  validateSpendLimit,
} from "./cardRules";

const now = new Date("2026-10-18T12:00:00Z");
const hours = (h: number) => new Date(now.getTime() + h * 3_600_000).toISOString();

describe("nextCardStatus", () => {
  it("freezes, unfreezes and cancels open cards", () => {
    expect(nextCardStatus("active", "freeze")).toEqual({ ok: true, status: "frozen", changed: true });
    expect(nextCardStatus("frozen", "unfreeze")).toEqual({ ok: true, status: "active", changed: true });
    expect(nextCardStatus("frozen", "cancel")).toEqual({ ok: true, status: "canceled", changed: true });
  });

  it("is idempotent for repeated actions", () => {
    expect(nextCardStatus("frozen", "freeze")).toEqual({ ok: true, status: "frozen", changed: false });
    expect(nextCardStatus("active", "unfreeze")).toEqual({ ok: true, status: "active", changed: false });
  });

  it("never reactivates a canceled card", () => {
    for (const action of ["freeze", "unfreeze", "cancel"] as const) {
      const result = nextCardStatus("canceled", action);
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.code).toBe("CARD_CANCELED");
    }
  });
});

describe("expiry", () => {
  it("requires an expiry only for temporary cards, within 1 hour to 90 days", () => {
    expect(resolveExpiry("permanent", undefined, now)).toEqual({ ok: true, value: null });
    expect(resolveExpiry("single_use", hours(48), now).ok).toBe(false);
    expect(resolveExpiry("temporary", undefined, now).ok).toBe(false);
    expect(resolveExpiry("temporary", hours(0.5), now).ok).toBe(false);
    expect(resolveExpiry("temporary", hours(24 * 91), now).ok).toBe(false);
    expect(resolveExpiry("temporary", "not a date", now).ok).toBe(false);
    expect(resolveExpiry("temporary", hours(24 * 7), now)).toEqual({ ok: true, value: hours(24 * 7) });
  });

  it("treats a temporary card past its expiry as expired and no longer counting toward the limit", () => {
    const expired = { kind: "temporary" as const, status: "active" as const, expiresAt: hours(-1) };
    expect(isCardExpired(expired, now)).toBe(true);
    expect(countsTowardCardLimit(expired, now)).toBe(false);
    expect(isCardExpired({ kind: "permanent", expiresAt: hours(-1) }, now)).toBe(false);
    expect(countsTowardCardLimit({ kind: "permanent", status: "frozen", expiresAt: null }, now)).toBe(true);
    expect(countsTowardCardLimit({ kind: "permanent", status: "canceled", expiresAt: null }, now)).toBe(false);
  });
});

describe("spend limits", () => {
  it("accepts null or whole cents within range", () => {
    expect(validateSpendLimit(undefined)).toEqual({ ok: true, value: null });
    expect(validateSpendLimit(2500)).toEqual({ ok: true, value: 2500 });
    expect(validateSpendLimit(25.5).ok).toBe(false);
    expect(validateSpendLimit(CARD_RULES.minSpendLimitCents - 1).ok).toBe(false);
    expect(validateSpendLimit(CARD_RULES.maxSpendLimitCents + 1).ok).toBe(false);
  });

  it("resets permanent cards monthly and caps others for their lifetime", () => {
    expect(spendLimitWindow("permanent")).toBe("monthly");
    expect(spendLimitWindow("single_use")).toBe("all_time");
    expect(spendLimitWindow("temporary")).toBe("all_time");
  });

  it("always caps single-use cards at the issuer", () => {
    expect(effectiveSpendLimit("single_use", null)).toBe(CARD_RULES.maxSpendLimitCents);
    expect(effectiveSpendLimit("single_use", 1500)).toBe(1500);
    expect(effectiveSpendLimit("permanent", null)).toBeNull();
  });
});
