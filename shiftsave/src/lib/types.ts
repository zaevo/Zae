/**
 * Shared domain types. These mirror the Supabase tables in
 * supabase/migrations (snake_case columns -> camelCase fields). Module-specific
 * types that only one module uses live next to that module's code.
 */
import type { Tier } from "./pricing";

export type Role = "member" | "worker" | "client_manager" | "admin";
export type ModuleKey = "credit" | "wallet" | "shifts";

export interface SessionUser {
  id: string;
  email: string;
  fullName: string;
  role: Role;
  organizationId: string | null;
  modules: ModuleKey[];
  demo: boolean;
}

/* ---------- Module C: shifts ---------- */

export type ShiftStatus = "open" | "claimed" | "in_progress" | "completed" | "approved" | "canceled";

export interface Shift {
  id: string;
  clientId: string;
  organizationId: string;
  organizationName: string;
  locationId: string | null;
  location: string; // human-readable address
  lat: number;
  lng: number;
  positionTitle: string;
  tierRequired: Tier;
  hourlyBillingRateCents: number;
  hourlyPayRateCents: number;
  scheduledStart: string; // ISO
  scheduledEnd: string; // ISO
  status: ShiftStatus;
  isEmergency: boolean;
  claimedBy: string | null;
  claimedByName?: string | null;
  notes?: string | null;
  distanceMiles?: number; // computed for the viewing worker
}

export type BackgroundCheckStatus = "not_started" | "pending" | "passed" | "failed" | "consider";
export type DrugScreenStatus = "not_tested" | "pending" | "passed" | "failed";
export type EngagementType = "contractor_1099" | "w2_eor";

export interface WorkerCompliance {
  userId: string;
  fullName: string;
  complianceTier: Tier;
  backgroundCheckStatus: BackgroundCheckStatus;
  fcraDisclosureAcceptedAt: string | null;
  drugScreenStatus: DrugScreenStatus;
  drugScreenDate: string | null;
  ratingAverage: number | null;
  completedShifts: number;
  onTimeShifts: number;
  tier2InvitedAt: string | null;
  engagementType: EngagementType;
}

export type DrugScreenResult = "negative" | "non_negative" | "invalid";

export interface DrugScreenLog {
  id: string;
  workerId: string;
  collectorId: string;
  collectedAt: string;
  kitLotNumber: string;
  result: DrugScreenResult;
  evidencePath: string | null;
  workerConsentAt: string;
  notes: string | null;
}

export interface Payout {
  id: string;
  shiftId: string;
  workerId: string;
  totalBilledCents: number;
  totalPaidToWorkerCents: number;
  agencyMarginCents: number;
  stripePaymentIntentId: string | null;
  stripeTransferId: string | null;
  destination: "stripe_connect" | "shiftsave_wallet";
  status: "pending" | "paid" | "failed";
  createdAt: string;
}

export interface ChatMessage {
  id: string;
  threadId: string;
  senderId: string;
  senderRole: Role;
  body: string;
  flagged: boolean;
  createdAt: string;
}

export type PoachSeverity = "low" | "medium" | "high";

export interface PoachFlag {
  id: string;
  messageId: string;
  threadId: string;
  senderId: string;
  senderName: string;
  matchedRules: string[];
  severity: PoachSeverity;
  excerpt: string;
  status: "open" | "reviewed" | "dismissed" | "escalated";
  createdAt: string;
}

/* ---------- Module B: wallet ---------- */

export type LedgerCategory =
  | "shift_earnings"
  | "membership_fee"
  | "addon_fee"
  | "card_spend"
  | "deposit"
  | "withdrawal"
  | "refund";

export interface LedgerEntry {
  id: string;
  walletId: string;
  direction: "credit" | "debit";
  amountCents: number; // always positive; direction gives the sign
  category: LedgerCategory;
  description: string;
  createdAt: string;
}

export interface Wallet {
  id: string;
  userId: string;
  availableCents: number;
  pendingCents: number;
  status: "active" | "frozen" | "closed";
}

export interface VirtualCard {
  id: string;
  walletId: string;
  last4: string;
  brand: "visa" | "mastercard";
  kind: "permanent" | "single_use" | "temporary";
  status: "active" | "frozen" | "canceled";
  nickname: string;
  spendLimitCents: number | null;
  expiresAt: string | null;
}

/* ---------- Module A: credit ---------- */

export interface CreditLine {
  id: string;
  userId: string;
  limitCents: number;
  balanceCents: number;
  status: "open" | "closed" | "charged_off";
  openedAt: string;
}

export interface CreditStatement {
  id: string;
  creditLineId: string;
  periodStart: string;
  periodEnd: string;
  statementBalanceCents: number;
  minimumDueCents: number;
  dueDate: string;
  paidAt: string | null;
  paidOnTime: boolean | null;
  daysPastDue: number;
}

export interface AffiliateOffer {
  id: string;
  issuer: string;
  productName: string;
  minScore: number;
  annualFeeCents: number;
  aprText: string;
  highlights: string[];
  bountyCents: number; // what ShiftSave earns — disclosed to the member
  url: string;
}

/* ---------- Module D: leads ---------- */

export interface LeadTarget {
  id: string;
  source: string;
  companyName: string;
  jobTitle: string;
  location: string;
  postedAt: string | null;
  url: string;
  urgencyKeywords: string[];
  contactEmail: string | null;
  createdAt: string;
}

export interface OutreachDraft {
  id: string;
  leadId: string;
  subject: string;
  body: string;
  status: "draft" | "approved" | "sent" | "suppressed";
  createdAt: string;
}
