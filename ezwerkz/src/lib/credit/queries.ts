/**
 * Server-only data access for the Credit Builder, demo or live.
 *
 * Live reads go through the RLS-bound client (members only ever see their
 * own rows). Row → domain mapping is centralized here and follows
 * supabase/migrations/0003_credit.sql.
 */
import type { SupabaseClient } from "@supabase/supabase-js";
import { isDemoMode } from "@/lib/env";
import { CREDIT, MEMBERSHIP_SPLIT } from "@/lib/pricing";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import type { AffiliateOffer, SessionUser } from "@/lib/types";
import { BillAnalysisModelSchema, finalizeBillAnalysis, type BillAnalysis } from "@/lib/ai/billAnalysis";
import { demoStoreProducts, getDemoCreditState } from "@/lib/demo/credit";
import type { BadgeKey, CreditTransactionKind, PaymentMethod, PaymentRecord, ReferralRecord, StatementRecord } from "./engine";
import {
  buildCreditSummary,
  isAddonKey,
  type AddonRecord,
  type CreditData,
  type CreditLineRecord,
  type CreditSummary,
  type MembershipRecord,
  type ScoreSnapshot,
  type StoreProduct,
} from "./summary";

/* ---------- row shapes (snake_case, as stored) ---------- */

export interface CreditLineRow {
  id: string;
  user_id: string;
  limit_cents: number;
  balance_cents: number;
  status: "open" | "closed" | "charged_off";
  account_number: string;
  opened_at: string;
  closed_at: string | null;
  level_up_applied_at?: string | null;
}

export interface StatementRow {
  id: string;
  credit_line_id: string;
  period_start: string;
  period_end: string;
  statement_balance_cents: number;
  minimum_due_cents: number;
  amount_paid_cents?: number | null;
  due_date: string;
  paid_at: string | null;
  paid_on_time: boolean | null;
  days_past_due: number | null;
}

export interface PaymentRow {
  id: string;
  statement_id: string | null;
  amount_cents: number;
  method: PaymentMethod;
  status: "pending" | "succeeded" | "failed" | "reversed";
  provider_payment_id: string | null;
  paid_at: string | null;
  created_at: string;
}

export interface TransactionRow {
  id: string;
  kind: CreditTransactionKind;
  amount_cents: number;
  description: string | null;
  posted_at: string;
  statement_id: string | null;
}

interface MembershipRow {
  status: "active" | "past_due" | "canceled";
  free_months_remaining: number | null;
  canceled_at: string | null;
  created_at: string;
}

interface OfferRow {
  id: string;
  issuer: string;
  product_name: string;
  min_score: number;
  annual_fee_cents: number;
  apr_text: string | null;
  highlights: string[] | null;
  bounty_cents: number;
  url: string;
}

interface ProductRow {
  id: string;
  name: string;
  description: string | null;
  kind: "membership" | "course" | "ebook" | "tool";
  price_cents: number;
  billing_interval: "one_time" | "monthly";
}

export interface ReferralRow {
  id: string;
  referrer_id: string;
  referred_user_id: string | null;
  referred_email: string | null;
  status: "invited" | "signed_up" | "rewarded" | "void";
  reward_months: number | null;
  rewarded_at: string | null;
  referred?: { full_name: string | null } | Array<{ full_name: string | null }> | null;
}

export interface BillAnalysisRow {
  id: string;
  provider_name: string | null;
  billed_amount_cents: number | null;
  findings: unknown;
  negotiation_script: string | null;
  model: string | null;
}

/* ---------- mappers ---------- */

export function mapLine(row: CreditLineRow, closedAtConsumerRequest = false): CreditLineRecord {
  return {
    id: row.id,
    userId: row.user_id,
    limitCents: Number(row.limit_cents),
    balanceCents: Number(row.balance_cents),
    status: row.status,
    openedAt: row.opened_at,
    accountNumber: row.account_number,
    closedAt: row.closed_at,
    closedAtConsumerRequest: row.status === "closed" && closedAtConsumerRequest,
  };
}

/** Statement breakdown (fee / purchases / credits) comes from the transactions attached to it. */
export function mapStatement(row: StatementRow, transactions: readonly TransactionRow[] = []): StatementRecord {
  let fee = 0;
  let purchases = 0;
  let credits = 0;
  for (const t of transactions) {
    if (t.statement_id !== row.id) continue;
    const amount = Number(t.amount_cents);
    if (t.kind === "membership_fee") fee += amount;
    else if (t.kind === "refund") credits += amount;
    else purchases += amount;
  }
  return {
    id: row.id,
    creditLineId: row.credit_line_id,
    periodStart: row.period_start,
    periodEnd: row.period_end,
    statementBalanceCents: Number(row.statement_balance_cents),
    minimumDueCents: Number(row.minimum_due_cents),
    dueDate: row.due_date,
    paidAt: row.paid_at,
    paidOnTime: row.paid_on_time,
    daysPastDue: row.days_past_due ?? 0,
    previousBalanceCents: Math.max(0, Number(row.statement_balance_cents) - fee - purchases + credits),
    purchasesCents: purchases,
    membershipFeeCents: fee,
    paymentsCents: 0,
    creditsCents: credits,
  };
}

export function mapPayment(row: PaymentRow): PaymentRecord {
  return {
    id: row.id,
    amountCents: Number(row.amount_cents),
    paidAt: row.paid_at ?? row.created_at,
    method: row.method,
    // A reversed payment no longer counts toward any statement.
    status: row.status === "reversed" ? "failed" : row.status,
  };
}

export function mapOffer(row: OfferRow): AffiliateOffer {
  return {
    id: row.id,
    issuer: row.issuer,
    productName: row.product_name,
    minScore: row.min_score,
    annualFeeCents: Number(row.annual_fee_cents),
    aprText: row.apr_text ?? "",
    highlights: row.highlights ?? [],
    bountyCents: Number(row.bounty_cents),
    url: row.url,
  };
}

export function mapProduct(row: ProductRow): StoreProduct {
  return {
    id: row.id,
    name: row.name,
    description: row.description ?? "",
    priceCents: Number(row.price_cents),
    category: row.kind === "course" ? "course" : "digital",
    fulfillment: "digital",
  };
}

/** The database names badges by what earned them; the UI uses short keys. */
export function mapBadgeKey(key: string): BadgeKey | null {
  switch (key) {
    case "first_on_time_payment":
      return "first_on_time_payment";
    case "on_time_streak_3":
    case "streak_3":
      return "streak_3";
    case `on_time_streak_${CREDIT.streakBadgeMonths}`:
    case "streak_6":
      return "streak_6";
    case "limit_level_up":
    case "level_up":
      return "level_up";
    default:
      return null;
  }
}

/** "Jordan Rivera" → "Jordan R." — referrers see friends by first name only. */
export function shortName(fullName: string): string {
  const [first, ...rest] = fullName.trim().split(/\s+/);
  const last = rest.at(-1);
  return last ? `${first} ${last[0]!.toUpperCase()}.` : (first ?? "A friend");
}

/** "jordan@example.com" → "jo•••@example.com" for invites not yet accepted. */
export function maskEmail(email: string): string {
  const [local, domain] = email.split("@");
  if (!local || !domain) return "Invited friend";
  return `${local.slice(0, 2)}•••@${domain}`;
}

export function mapReferral(row: ReferralRow): ReferralRecord | null {
  if (row.status === "void") return null;
  const referred = Array.isArray(row.referred) ? row.referred[0] : row.referred;
  return {
    id: row.id,
    referrerId: row.referrer_id,
    referredId: row.referred_user_id ?? "",
    referredName: referred?.full_name ? shortName(referred.full_name) : row.referred_email ? maskEmail(row.referred_email) : "A friend",
    status: row.status === "rewarded" ? "qualified" : "pending",
    qualifiedAt: row.status === "rewarded" ? row.rewarded_at : null,
    rewardMonths: row.status === "rewarded" ? (row.reward_months ?? 0) : 0,
  };
}

function must<T>(result: { data: unknown; error: { message: string } | null }, what: string): T {
  if (result.error) throw new Error(`Failed to load ${what}: ${result.error.message}`);
  return result.data as T;
}

/* ---------- loaders ---------- */

export async function loadLiveCreditData(supabase: SupabaseClient, userId: string): Promise<CreditData> {
  const [lineRes, membershipRes] = await Promise.all([
    supabase.from("virtual_credit_lines").select("*").eq("user_id", userId).maybeSingle(),
    supabase.from("membership_subscriptions").select("status, free_months_remaining, canceled_at, created_at").eq("user_id", userId).maybeSingle(),
  ]);
  const lineRow = must<CreditLineRow | null>(lineRes, "credit line");
  const membershipRow = must<MembershipRow | null>(membershipRes, "membership");
  const membership: MembershipRecord | null = membershipRow
    ? {
        // past_due still means an active membership; the statement shows what's owed.
        status: membershipRow.status === "canceled" ? "canceled" : "active",
        freeMonthsRemaining: membershipRow.free_months_remaining ?? 0,
        startedAt: membershipRow.created_at,
        canceledAt: membershipRow.canceled_at,
      }
    : null;
  const line = lineRow ? mapLine(lineRow, membership?.status === "canceled") : null;
  const none = { data: [], error: null };

  const [statementsRes, paymentsRes, txRes, scoresRes, consentRes, badgesRes, referralsRes, addonsRes, offersRes, userRes] = await Promise.all([
    line ? supabase.from("credit_statements").select("*").eq("credit_line_id", line.id).order("period_end", { ascending: true }).limit(36) : none,
    line ? supabase.from("credit_payments").select("*").eq("credit_line_id", line.id).order("paid_at", { ascending: true }).limit(300) : none,
    line
      ? supabase
          .from("credit_transactions")
          .select("id, kind, amount_cents, description, posted_at, statement_id")
          .eq("credit_line_id", line.id)
          .order("posted_at", { ascending: false })
          .limit(500)
      : none,
    supabase.from("credit_score_snapshots").select("score, model, provider, pulled_at").eq("user_id", userId).order("pulled_at", { ascending: true }).limit(24),
    supabase
      .from("consents")
      .select("accepted_at")
      .eq("user_id", userId)
      .eq("kind", "soft_pull")
      .is("revoked_at", null)
      .order("accepted_at", { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase.from("user_badges").select("badge_key, awarded_at").eq("user_id", userId),
    supabase
      .from("referrals")
      .select("id, referrer_id, referred_user_id, referred_email, status, reward_months, rewarded_at, referred:users!referred_user_id(full_name)")
      .eq("referrer_id", userId)
      .order("created_at", { ascending: false })
      .limit(50),
    supabase.from("addon_subscriptions").select("addon_key, status, started_at, canceled_at").eq("user_id", userId),
    supabase.from("affiliate_offers").select("*").eq("active", true),
    supabase.from("users").select("referral_code").eq("id", userId).maybeSingle(),
  ]);

  const transactions = must<TransactionRow[]>(txRes, "transactions");

  const scores: ScoreSnapshot[] = must<Array<{ score: number; model: string | null; provider: string; pulled_at: string }>>(scoresRes, "scores").map((r) => ({
    score: r.score,
    pulledAt: r.pulled_at,
    source: r.model ? `${r.provider} (${r.model})` : r.provider,
  }));

  const badges: CreditData["badges"] = [];
  for (const b of must<Array<{ badge_key: string; awarded_at: string }>>(badgesRes, "badges")) {
    const key = mapBadgeKey(b.badge_key);
    if (key && !badges.some((x) => x.key === key)) badges.push({ key, awardedAt: b.awarded_at });
  }

  const addons: AddonRecord[] = must<Array<{ addon_key: string; status: "active" | "canceled"; started_at: string; canceled_at: string | null }>>(
    addonsRes,
    "add-ons",
  )
    .filter((a) => isAddonKey(a.addon_key))
    .map((a) => ({ key: a.addon_key as AddonRecord["key"], status: a.status, startedAt: a.started_at, canceledAt: a.canceled_at }));

  return {
    line,
    membership,
    statements: must<StatementRow[]>(statementsRes, "statements").map((s) => mapStatement(s, transactions)),
    payments: must<PaymentRow[]>(paymentsRes, "payments").map(mapPayment),
    transactions: transactions.map((t) => ({
      id: t.id,
      kind: t.kind,
      amountCents: Number(t.amount_cents),
      description: t.description ?? "",
      occurredAt: t.posted_at,
    })),
    scores,
    softPullConsentAt: must<{ accepted_at: string } | null>(consentRes, "consent")?.accepted_at ?? null,
    badges,
    referralCode: must<{ referral_code: string | null } | null>(userRes, "referral code")?.referral_code ?? null,
    referrals: must<ReferralRow[]>(referralsRes, "referrals")
      .map(mapReferral)
      .filter((r): r is ReferralRecord => r !== null),
    addons,
    offers: must<OfferRow[]>(offersRes, "offers").map(mapOffer),
  };
}

export async function loadCreditData(user: SessionUser): Promise<CreditData> {
  if (isDemoMode()) return getDemoCreditState(user);
  const supabase = await createSupabaseServerClient();
  return loadLiveCreditData(supabase, user.id);
}

export async function getCreditSummary(user: SessionUser): Promise<CreditSummary> {
  return buildCreditSummary(await loadCreditData(user));
}

const PRODUCT_COLUMNS = "id, name, description, kind, price_cents, billing_interval";

export async function listStoreProducts(): Promise<StoreProduct[]> {
  if (isDemoMode()) return demoStoreProducts;
  const supabase = await createSupabaseServerClient();
  const res = await supabase
    .from("credit_store_products")
    .select(PRODUCT_COLUMNS)
    .eq("active", true)
    .eq("billing_interval", "one_time")
    .neq("kind", "membership")
    .gt("price_cents", 0)
    .order("sort_order")
    .order("price_cents");
  return must<ProductRow[]>(res, "store products").map(mapProduct);
}

export async function getStoreProduct(id: string): Promise<StoreProduct | null> {
  if (isDemoMode()) return demoStoreProducts.find((p) => p.id === id) ?? null;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return null;
  const supabase = await createSupabaseServerClient();
  const res = await supabase.from("credit_store_products").select(PRODUCT_COLUMNS).eq("id", id).eq("active", true).neq("kind", "membership").maybeSingle();
  const row = must<ProductRow | null>(res, "store product");
  return row ? mapProduct(row) : null;
}

/**
 * bill_analyses keeps the flagged issues in `findings` and the rest of the
 * result (script, letter, questions, line items, period, summary) as a JSON
 * bundle in the `negotiation_script` text column.
 */
const BillBundleSchema = BillAnalysisModelSchema.pick({
  isBill: true,
  category: true,
  billingPeriodStart: true,
  billingPeriodEnd: true,
  lineItems: true,
  negotiationScript: true,
  letterDraft: true,
  questionsToAsk: true,
  summary: true,
}).extend({ fileName: BillAnalysisModelSchema.shape.provider.nullable(), analyzedAt: BillAnalysisModelSchema.shape.provider });

export function billAnalysisBundle(a: BillAnalysis): string {
  return JSON.stringify({
    isBill: a.isBill,
    category: a.category,
    billingPeriodStart: a.billingPeriodStart,
    billingPeriodEnd: a.billingPeriodEnd,
    lineItems: a.lineItems,
    negotiationScript: a.negotiationScript,
    letterDraft: a.letterDraft,
    questionsToAsk: a.questionsToAsk,
    summary: a.summary,
    fileName: a.fileName,
    analyzedAt: a.analyzedAt,
  });
}

export function mapBillAnalysisRow(row: BillAnalysisRow): BillAnalysis | null {
  let bundleJson: unknown = null;
  try {
    bundleJson = row.negotiation_script ? JSON.parse(row.negotiation_script) : null;
  } catch {
    return null;
  }
  const bundle = BillBundleSchema.safeParse(bundleJson);
  const findings = BillAnalysisModelSchema.shape.flaggedIssues.safeParse(row.findings);
  if (!bundle.success || !findings.success) return null;
  const { fileName, analyzedAt, ...rest } = bundle.data;
  return finalizeBillAnalysis(
    { ...rest, provider: row.provider_name ?? "Your provider", totalDueCents: Number(row.billed_amount_cents ?? 0), flaggedIssues: findings.data },
    { id: row.id, source: "claude", model: row.model, fileName, analyzedAt },
  );
}

export async function listBillAnalyses(user: SessionUser): Promise<BillAnalysis[]> {
  if (isDemoMode()) return [...getDemoCreditState(user).billAnalyses].reverse();
  const supabase = await createSupabaseServerClient();
  const res = await supabase
    .from("bill_analyses")
    .select("id, provider_name, billed_amount_cents, findings, negotiation_script, model")
    .eq("user_id", user.id)
    .eq("status", "complete")
    .order("created_at", { ascending: false })
    .limit(10);
  return must<BillAnalysisRow[]>(res, "bill analyses")
    .map(mapBillAnalysisRow)
    .filter((a): a is BillAnalysis => a !== null);
}

export interface ImpactSummary {
  partnerName: string;
  totalImpactCents: number;
}

/**
 * Real impact only (SPEC §2 rule 9): nothing unless the impact split is on
 * and money has actually been allocated from this member's payments to a
 * named partner (the database refuses impact rows without one).
 */
export async function getImpactSummary(user: SessionUser): Promise<ImpactSummary | null> {
  if (MEMBERSHIP_SPLIT.impactCents <= 0 || isDemoMode()) return null;
  const supabase = await createSupabaseServerClient();
  const res = await supabase.from("treasury_allocations").select("amount_cents, partner_name").eq("bucket", "impact").eq("user_id", user.id);
  if (res.error) return null;
  const rows = (res.data ?? []) as Array<{ amount_cents: number; partner_name: string | null }>;
  const total = rows.reduce((n, r) => n + Number(r.amount_cents), 0);
  const partnerName = rows.find((r) => r.partner_name)?.partner_name ?? null;
  return total > 0 && partnerName ? { partnerName, totalImpactCents: total } : null;
}
