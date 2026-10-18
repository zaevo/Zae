/**
 * Wallet-module types (Module B). Shared shapes (Wallet, LedgerEntry,
 * VirtualCard) live in @/lib/types; these extend them with fields only the
 * wallet UI and API need. Nothing here ever carries a PAN or CVV.
 */
import type { LedgerEntry, VirtualCard, Wallet } from "@/lib/types";

export type CardKind = VirtualCard["kind"];
export type CardStatus = VirtualCard["status"];
export type CardAction = "freeze" | "unfreeze" | "cancel";
export type IssuingProviderName = "stripe_issuing" | "lithic" | "demo";

export interface WalletCard extends VirtualCard {
  provider: IssuingProviderName;
  createdAt: string;
}

export type IncomeSourceType = "ezwerkz_payouts" | "employer_direct_deposit" | "gig_platform" | "benefits" | "other";
export type IncomeFrequency = "weekly" | "biweekly" | "semimonthly" | "monthly" | "irregular";

export interface IncomeStream {
  id: string;
  label: string;
  sourceType: IncomeSourceType;
  expectedAmountCents: number | null;
  frequency: IncomeFrequency;
  /** Share of this income routed to the Wallet (1–100). */
  allocationPercent: number;
  isActive: boolean;
  lastDepositAt: string | null;
}

export type AutopayPurpose = "membership_fee" | "addon_fee";

/** Reg E style record: who (the owner), when, how much, and which text version. */
export interface AutopayAuthorization {
  id: string;
  purpose: AutopayPurpose;
  maxAmountCents: number;
  frequency: "monthly";
  authorizationTextVersion: string;
  authorizedAt: string;
  revokedAt: string | null;
  lastSweptAt: string | null;
}

export interface AutopayReceipt {
  id: string;
  amountCents: number;
  body: string;
  createdAt: string;
}

export interface WalletSummary {
  wallet: Wallet;
  autopayActive: boolean;
}

export interface WalletOverview extends WalletSummary {
  entries: LedgerEntry[];
  cards: WalletCard[];
  incomeStreams: IncomeStream[];
  autopay: AutopayAuthorization | null;
  lastReceipt: AutopayReceipt | null;
}

export const INCOME_SOURCE_LABELS: Record<IncomeSourceType, string> = {
  ezwerkz_payouts: "EzWerkz shift pay",
  employer_direct_deposit: "Employer direct deposit",
  gig_platform: "Gig platform",
  benefits: "Benefits",
  other: "Other",
};

export const INCOME_FREQUENCY_LABELS: Record<IncomeFrequency, string> = {
  weekly: "Weekly",
  biweekly: "Every 2 weeks",
  semimonthly: "Twice a month",
  monthly: "Monthly",
  irregular: "When I work",
};

export const CARD_KIND_LABELS: Record<CardKind, string> = {
  permanent: "Permanent",
  single_use: "Single-use",
  temporary: "Temporary",
};
