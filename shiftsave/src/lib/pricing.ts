/**
 * Single source of truth for every price, rate and split in ShiftSave.
 * All money is integer cents. The SQL migrations mirror these values in
 * `platform_config` — if you change a number here, change it there too
 * (supabase/migrations/0001_core.sql seeds it).
 */

export type Tier = 1 | 2;

export interface TierRate {
  tier: Tier;
  name: string;
  positions: string[];
  billRateCents: number; // what the client pays per hour
  payRateCents: number; // what the worker earns per hour
}

export const TIER_RATES: Record<Tier, TierRate> = {
  1: {
    tier: 1,
    name: "Standard Stand-In",
    positions: ["Stocking", "Lot maintenance", "General labor"],
    billRateCents: 22_00,
    payRateCents: 15_00,
  },
  2: {
    tier: 2,
    name: "Corporate Certified",
    positions: ["Cashier", "Register handling", "Keyholder", "Night shift operator", "Forklift"],
    billRateCents: 35_00,
    payRateCents: 18_00,
  },
};

/** Platform gross markup per hour for a tier (bill − pay). Tier 1 = $7, Tier 2 = $17. */
export function markupCents(tier: Tier): number {
  return TIER_RATES[tier].billRateCents - TIER_RATES[tier].payRateCents;
}

/** Tier 2 upgrade rules (self-funding vetting loop). */
export const TIER2_UPGRADE = {
  qualifyingShifts: 2, // completed, on-time Tier 1 shifts
  minRating: 4.5, // client rating average required to be invited
  backgroundCheckCostCents: 25_00, // platform-paid out of margin, never deducted from worker pay
  drugScreenKitCostCents: 5_00,
} as const;

/** Dispatch rules for emergency call-outs. */
export const DISPATCH = {
  radiusMiles: 15,
  claimCodeLength: 4, // the shortcode a worker texts back to claim
  smsTtlMinutes: 30, // claim codes expire after this
} as const;

/** Module A — closed-loop credit builder. */
export const CREDIT = {
  defaultLimitCents: 500_00,
  levelUpLimitCents: 1_000_00,
  levelUpAfterOnTimeMonths: 3,
  membershipFeeCents: 5_00,
  affiliateScoreThreshold: 660,
  streakBadgeMonths: 6,
} as const;

/**
 * Split of each $5 membership payment. Every cent is accounted for in the
 * `treasury_allocations` table. `impact` is OFF (0) by default: only turn it
 * on with a real donation partner, because the UI tells members exactly
 * where that money went (see docs/COMPLIANCE.md §Impact claims).
 */
export const MEMBERSHIP_SPLIT = {
  reportingVendorCents: 1_50,
  impactCents: 0,
} as const;

/** Add-ons (opt-in, cancel any time). */
export const ADDONS = {
  rentReporting: { key: "rent_reporting", priceCents: 4_00, name: "Rent & utility reporting" },
  aiCoach: { key: "ai_coach", priceCents: 10_00, name: "AI financial coach" },
} as const;

/** Referral: each referred friend who completes their first on-time payment = 1 free month. */
export const REFERRAL = { rewardMonths: 1 } as const;

/** Section 8 conversion fee (MSA). Shown conspicuously everywhere it applies. */
export const CONVERSION_FEE_CENTS = 4_500_00;
export const NON_CIRCUMVENTION_MONTHS = 12;

export interface ShiftQuote {
  hours: number;
  billTotalCents: number;
  workerPayCents: number;
  platformMarginCents: number;
}

/** Price a shift. Hours are rounded to the nearest quarter hour. */
export function quoteShift(tier: Tier, start: Date, end: Date): ShiftQuote {
  const ms = end.getTime() - start.getTime();
  if (!(ms > 0)) throw new Error("Shift end must be after start");
  const hours = Math.round((ms / 3_600_000) * 4) / 4;
  const rate = TIER_RATES[tier];
  const billTotalCents = Math.round(rate.billRateCents * hours);
  const workerPayCents = Math.round(rate.payRateCents * hours);
  return { hours, billTotalCents, workerPayCents, platformMarginCents: billTotalCents - workerPayCents };
}

/** Split a membership payment into vendor / impact / platform buckets. */
export function splitMembershipPayment(amountCents: number) {
  const vendor = Math.min(MEMBERSHIP_SPLIT.reportingVendorCents, amountCents);
  const impact = Math.min(MEMBERSHIP_SPLIT.impactCents, amountCents - vendor);
  return { reportingVendorCents: vendor, impactCents: impact, platformCents: amountCents - vendor - impact };
}
