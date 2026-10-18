/**
 * Server-side Credit Builder actions (demo or live). Route handlers stay
 * thin and call these; business rules come from engine.ts.
 *
 * Live mode leans on the database's own guarantees (0003_credit.sql): store
 * purchases are inserted through RLS and the line trigger enforces the limit
 * atomically; record_membership_payment debits the Wallet and records the
 * payment in one transaction; the payment trigger updates the balance and
 * statement, writes treasury_allocations, awards badges, applies the
 * level-up and rewards referrals. Demo mode emulates the same effects.
 */
import { CONSENTS } from "@/content/consents";
import { env, isDemoMode } from "@/lib/env";
import { getStripe } from "@/lib/integrations/stripe";
import { CREDIT } from "@/lib/pricing";
import { createSupabaseServerClient, createSupabaseServiceClient } from "@/lib/supabase/server";
import type { SessionUser } from "@/lib/types";
import { getWalletSummary } from "@/lib/wallet/queries";
import { getDemoCreditState, nextDemoId, type DemoCreditState } from "@/lib/demo/credit";
import {
  applyPayment,
  badgesToAward,
  canPurchase,
  evaluateStatements,
  levelUpProgress,
  onTimeStreak,
  utcDay,
  type BadgeKey,
  type PaymentMethod,
  type PaymentRecord,
  type StatementView,
} from "./engine";
import { CreditActionError, type CreditErrorCode } from "./errors";
import {
  getStoreProduct,
  loadCreditData,
  loadLiveCreditData,
  mapLine,
  mapPayment,
  mapStatement,
  type CreditLineRow,
  type PaymentRow,
  type StatementRow,
  type TransactionRow,
} from "./queries";
import { isAddonKey, type AddonKey, type CreditData, type CreditTransactionRecord } from "./summary";

type ServiceClient = ReturnType<typeof createSupabaseServiceClient>;

const PURCHASE_REJECTIONS = {
  LINE_NOT_OPEN: "Your credit line is closed.",
  MEMBERSHIP_INACTIVE: "Store purchases need an active membership.",
  INSUFFICIENT_CREDIT: "That's more than your available credit.",
  PAST_DUE: "Pay your past-due statement before making new purchases.",
  INVALID_PRICE: "This product isn't available right now.",
} as const;

/** Database exceptions (raised by name in 0003_credit.sql / 0002_wallet.sql) → member-facing errors. */
const DB_ERRORS: Record<string, { code: CreditErrorCode; message: string; status: 402 | 404 | 409 }> = {
  INSUFFICIENT_FUNDS: { code: "INSUFFICIENT_FUNDS", message: "Your Wallet balance is too low for this payment.", status: 402 },
  WALLET_FROZEN: { code: "INSUFFICIENT_FUNDS", message: "Your Wallet is frozen. Unfreeze it or pay by card.", status: 402 },
  WALLET_CLOSED: { code: "INSUFFICIENT_FUNDS", message: "Your Wallet is closed. Pay by card or bank instead.", status: 402 },
  WALLET_NOT_FOUND: { code: "INSUFFICIENT_FUNDS", message: "Set up your Wallet first, or pay by card or bank.", status: 402 },
  OVERPAYMENT: { code: "ALREADY_PAID", message: "That's more than you owe right now.", status: 409 },
  CREDIT_LIMIT_EXCEEDED: { code: "INSUFFICIENT_CREDIT", message: PURCHASE_REJECTIONS.INSUFFICIENT_CREDIT, status: 402 },
  CREDIT_LINE_NOT_OPEN: { code: "LINE_NOT_OPEN", message: PURCHASE_REJECTIONS.LINE_NOT_OPEN, status: 409 },
  PRODUCT_NOT_AVAILABLE: { code: "NOT_FOUND", message: "Product not found.", status: 404 },
  STATEMENT_NOT_FOUND: { code: "NOT_FOUND", message: "Statement not found.", status: 404 },
};

function fromDbError(error: { message: string }, fallback: string): never {
  const known = DB_ERRORS[error.message.trim()];
  if (known) throw new CreditActionError(known.code, known.message, known.status);
  throw new Error(`${fallback}: ${error.message}`);
}

/* ------------------------------------------------------------------ */
/* Post-payment effects                                                */
/* ------------------------------------------------------------------ */

export interface PaymentEffects {
  statements: StatementView[];
  levelUp: boolean;
  newBadges: BadgeKey[];
  closeLine: boolean;
  streak: number;
}

/**
 * What a settled payment unlocks: level-up, badges, and closing a line whose
 * membership was canceled once it's paid off. In live mode the payment
 * trigger does the first two; demo mode applies all three from this.
 */
export function computePaymentEffects(data: CreditData, now: Date): PaymentEffects {
  if (!data.line) return { statements: [], levelUp: false, newBadges: [], closeLine: false, streak: 0 };
  const statements = evaluateStatements(data.statements, data.payments, now);
  const level = levelUpProgress(data.line, statements);
  const streak = onTimeStreak(statements);
  return {
    statements,
    levelUp: level.eligible,
    newBadges: badgesToAward(
      data.badges.map((b) => b.key),
      { streak, leveledUp: level.leveledUp || level.eligible },
    ),
    closeLine: data.membership?.status === "canceled" && data.line.balanceCents <= 0 && data.line.status === "open",
    streak: streak.current,
  };
}

function applyDemoEffects(state: DemoCreditState, now: Date): PaymentEffects {
  const effects = computePaymentEffects(state, now);
  if (!state.line) return effects;
  if (effects.levelUp) state.line.limitCents = CREDIT.levelUpLimitCents;
  for (const key of effects.newBadges) state.badges.push({ key, awardedAt: now.toISOString() });
  if (effects.closeLine) {
    state.line.status = "closed";
    state.line.closedAt = now.toISOString();
    state.line.closedAtConsumerRequest = true;
  }
  return effects;
}

/**
 * Live follow-up after any payment is recorded (Wallet here; card/ACH from
 * the Stripe webhook): close the line once a canceled member has paid it off.
 * Badges, level-up and referral rewards are handled by the payment trigger.
 */
export async function afterStatementPaid(service: ServiceClient, userId: string): Promise<{ lineClosed: boolean }> {
  const [lineRes, subRes] = await Promise.all([
    service.from("virtual_credit_lines").select("id, balance_cents, status").eq("user_id", userId).maybeSingle(),
    service.from("membership_subscriptions").select("status").eq("user_id", userId).maybeSingle(),
  ]);
  const line = lineRes.data as { id: string; balance_cents: number; status: string } | null;
  const sub = subRes.data as { status: string } | null;
  if (!line || line.status !== "open" || Number(line.balance_cents) > 0 || sub?.status !== "canceled") return { lineClosed: false };
  const upd = await service.from("virtual_credit_lines").update({ status: "closed" }).eq("id", line.id).eq("status", "open");
  if (upd.error) throw new Error(`Failed to close credit line: ${upd.error.message}`);
  return { lineClosed: true };
}

/* ------------------------------------------------------------------ */
/* Pay a statement                                                     */
/* ------------------------------------------------------------------ */

export type PayResult =
  | { kind: "paid"; paymentId: string; amountCents: number; status: PaymentRecord["status"]; newBadges: BadgeKey[]; leveledUp: boolean; streak: number }
  | { kind: "redirect"; checkoutUrl: string; amountCents: number };

function payableAmount(views: readonly StatementView[], payments: readonly PaymentRecord[], statementId: string): { statement: StatementView; amountCents: number } {
  const statement = views.find((s) => s.id === statementId);
  if (!statement) throw new CreditActionError("NOT_FOUND", "Statement not found.", 404);
  if (statement.remainingDueCents <= 0) throw new CreditActionError("ALREADY_PAID", "This statement is already paid.", 409);
  const pending = payments
    .filter((p) => p.status === "pending" && utcDay(p.paidAt) > utcDay(statement.periodEnd))
    .reduce((n, p) => n + p.amountCents, 0);
  const amountCents = statement.remainingDueCents - pending;
  if (amountCents <= 0) throw new CreditActionError("PAYMENT_PENDING", "A payment for this statement is already processing.", 409);
  return { statement, amountCents };
}

/** Friendly pre-check; the database re-checks the balance inside the payment transaction. */
async function assertWalletCovers(user: SessionUser, amountCents: number): Promise<void> {
  const { wallet } = await getWalletSummary(user);
  if (wallet.status !== "active") throw new CreditActionError("INSUFFICIENT_FUNDS", "Your Wallet isn't active.", 402);
  if (wallet.availableCents < amountCents) throw new CreditActionError("INSUFFICIENT_FUNDS", "Your Wallet balance is too low for this payment.", 402);
}

export async function payStatement(user: SessionUser, input: { statementId: string; method: PaymentMethod }): Promise<PayResult> {
  return isDemoMode() ? demoPayStatement(user, input) : livePayStatement(user, input);
}

async function demoPayStatement(user: SessionUser, input: { statementId: string; method: PaymentMethod }): Promise<PayResult> {
  const state = getDemoCreditState(user);
  if (!state.line) throw new CreditActionError("NOT_ENROLLED", "Open a credit line first.", 404);
  const now = new Date();
  const views = evaluateStatements(state.statements, state.payments, now);
  const { amountCents } = payableAmount(views, state.payments, input.statementId);
  if (input.method === "wallet") await assertWalletCovers(user, amountCents);

  // ACH settles in a few business days; card and Wallet settle immediately.
  const payment: PaymentRecord = {
    id: nextDemoId(state, "pay"),
    amountCents,
    paidAt: now.toISOString(),
    method: input.method,
    status: input.method === "ach" ? "pending" : "succeeded",
  };
  const applied = applyPayment({ line: state.line, statements: state.statements, payments: state.payments, payment });
  state.payments.push(payment);
  state.line.balanceCents = applied.lineBalanceCents;

  const effects = applyDemoEffects(state, now);
  return { kind: "paid", paymentId: payment.id, amountCents, status: payment.status, newBadges: effects.newBadges, leveledUp: effects.levelUp, streak: effects.streak };
}

async function livePayStatement(user: SessionUser, input: { statementId: string; method: PaymentMethod }): Promise<PayResult> {
  const supabase = await createSupabaseServerClient();
  const before = await loadLiveCreditData(supabase, user.id);
  if (!before.line) throw new CreditActionError("NOT_ENROLLED", "Open a credit line first.", 404);
  const now = new Date();
  const { statement, amountCents } = payableAmount(evaluateStatements(before.statements, before.payments, now), before.payments, input.statementId);

  if (input.method === "wallet") {
    await assertWalletCovers(user, amountCents);
    // Called as the member: the function debits their own Wallet and records the payment atomically.
    const res = await supabase.rpc("record_membership_payment", {
      p_statement_id: statement.id,
      p_amount_cents: amountCents,
      p_method: "wallet",
      p_provider_payment_id: null,
    });
    if (res.error) fromDbError(res.error, "Failed to record Wallet payment");
    await afterStatementPaid(createSupabaseServiceClient(), user.id);

    const after = await loadLiveCreditData(supabase, user.id);
    const held = new Set(before.badges.map((b) => b.key));
    return {
      kind: "paid",
      paymentId: String(res.data),
      amountCents,
      status: "succeeded",
      newBadges: after.badges.map((b) => b.key).filter((k) => !held.has(k)),
      leveledUp: (after.line?.limitCents ?? 0) > before.line.limitCents,
      streak: onTimeStreak(evaluateStatements(after.statements, after.payments, new Date())).current,
    };
  }

  let stripe: ReturnType<typeof getStripe>;
  try {
    stripe = getStripe();
  } catch {
    throw new CreditActionError("NOT_CONFIGURED", "Card and bank payments aren't available right now. Try paying from your Wallet.", 503);
  }
  const metadata = { kind: "credit_statement_payment", statement_id: statement.id, user_id: user.id, method: input.method };
  // Hosted Checkout collects card/bank details so no PAN touches our servers. The
  // PaymentIntent it creates carries this metadata to the Stripe webhook, which
  // records it with record_membership_payment(statement_id, amount, method, pi.id).
  const session = await stripe.checkout.sessions.create(
    {
      mode: "payment",
      payment_method_types: [input.method === "ach" ? "us_bank_account" : "card"],
      line_items: [
        {
          quantity: 1,
          price_data: {
            currency: "usd",
            unit_amount: amountCents,
            product_data: { name: "EzWerkz credit line payment", description: `Statement ${statement.periodStart} – ${statement.periodEnd}` },
          },
        },
      ],
      customer_email: user.email,
      client_reference_id: user.id,
      metadata,
      payment_intent_data: { metadata },
      success_url: `${env.appUrl}/credit?payment=processing`,
      cancel_url: `${env.appUrl}/credit?payment=canceled`,
    },
    { idempotencyKey: `credit-pay:${statement.id}:${amountCents}:${input.method}:${now.toISOString().slice(0, 10)}` },
  );
  if (!session.url) throw new CreditActionError("PROVIDER_ERROR", "We couldn't start checkout. Please try again.", 502);
  return { kind: "redirect", checkoutUrl: session.url, amountCents };
}

/* ------------------------------------------------------------------ */
/* Store purchase                                                      */
/* ------------------------------------------------------------------ */

export interface PurchaseResult {
  transaction: CreditTransactionRecord;
  balanceCents: number;
  availableCents: number;
}

export async function purchaseProduct(user: SessionUser, productId: string): Promise<PurchaseResult> {
  const product = await getStoreProduct(productId);
  if (!product) throw new CreditActionError("NOT_FOUND", "Product not found.", 404);
  const data = await loadCreditData(user);
  if (!data.line || !data.membership) throw new CreditActionError("NOT_ENROLLED", "Open a credit line first.", 404);
  const now = new Date();
  const hasPastDue = evaluateStatements(data.statements, data.payments, now).some((s) => s.status === "past_due");
  const check = canPurchase({ line: data.line, membership: data.membership, priceCents: product.priceCents, hasPastDue });
  if (!check.ok) {
    throw new CreditActionError(check.reason, PURCHASE_REJECTIONS[check.reason], check.reason === "INSUFFICIENT_CREDIT" ? 402 : 409);
  }

  if (isDemoMode()) {
    const state = data as DemoCreditState;
    const transaction: CreditTransactionRecord = {
      id: nextDemoId(state, "txn"),
      kind: "purchase",
      amountCents: product.priceCents,
      description: product.name,
      occurredAt: now.toISOString(),
    };
    state.transactions.push(transaction);
    state.line!.balanceCents = check.balanceAfterCents;
    return { transaction, balanceCents: check.balanceAfterCents, availableCents: check.availableAfterCents };
  }

  // The insert runs as the member. The database prices it server-side and the
  // line trigger locks the row and rejects anything over the limit.
  const supabase = await createSupabaseServerClient();
  const ins = await supabase
    .from("credit_transactions")
    .insert({ credit_line_id: data.line.id, user_id: user.id, product_id: product.id, kind: "purchase", amount_cents: product.priceCents, description: product.name })
    .select("id, amount_cents, description, posted_at")
    .single();
  if (ins.error) fromDbError(ins.error, "Failed to record purchase");
  const row = ins.data as { id: string; amount_cents: number; description: string; posted_at: string };
  const lineRes = await supabase.from("virtual_credit_lines").select("limit_cents, balance_cents").eq("id", data.line.id).single();
  const line = lineRes.data as { limit_cents: number; balance_cents: number } | null;
  const balance = line ? Number(line.balance_cents) : check.balanceAfterCents;
  return {
    transaction: { id: row.id, kind: "purchase", amountCents: Number(row.amount_cents), description: row.description, occurredAt: row.posted_at },
    balanceCents: balance,
    availableCents: line ? Number(line.limit_cents) - balance : check.availableAfterCents,
  };
}

/* ------------------------------------------------------------------ */
/* Soft-pull consent                                                   */
/* ------------------------------------------------------------------ */

export async function recordSoftPullConsent(
  user: SessionUser,
  context: { ipAddress: string | null; userAgent: string | null },
): Promise<{ consentedAt: string; textVersion: string; score: number | null }> {
  const consent = CONSENTS.soft_pull;
  const now = new Date().toISOString();
  if (isDemoMode()) {
    const state = getDemoCreditState(user);
    state.softPullConsentAt = now;
    // The demo partner answers instantly; live scores arrive from the soft-inquiry partner.
    if (!state.scores.length) state.scores.push({ score: 668, pulledAt: now, source: "Soft-inquiry partner (demo)" });
    return { consentedAt: now, textVersion: consent.version, score: state.scores.at(-1)?.score ?? null };
  }
  const supabase = await createSupabaseServerClient();
  const res = await supabase.from("consents").insert({
    user_id: user.id,
    kind: "soft_pull",
    text_version: consent.version,
    accepted_at: now,
    ip_address: context.ipAddress?.slice(0, 64) ?? null,
    user_agent: context.userAgent?.slice(0, 512) ?? null,
  });
  if (res.error) throw new Error(`Failed to record consent: ${res.error.message}`);
  return { consentedAt: now, textVersion: consent.version, score: null };
}

/* ------------------------------------------------------------------ */
/* Add-ons and membership                                              */
/* ------------------------------------------------------------------ */

export async function subscribeAddon(user: SessionUser, key: string): Promise<{ key: AddonKey; active: true }> {
  if (!isAddonKey(key)) throw new CreditActionError("NOT_FOUND", "Unknown add-on.", 404);
  const data = await loadCreditData(user);
  if (data.membership?.status !== "active") throw new CreditActionError("MEMBERSHIP_INACTIVE", "Add-ons need an active membership.", 409);
  if (data.addons.some((a) => a.key === key && a.status === "active")) throw new CreditActionError("ALREADY_ACTIVE", "You already have this add-on.", 409);
  const now = new Date().toISOString();
  if (isDemoMode()) {
    (data as DemoCreditState).addons.push({ key, status: "active", startedAt: now, canceledAt: null });
  } else {
    // price_cents is set by the database from platform_config.
    const supabase = await createSupabaseServerClient();
    const res = await supabase.from("addon_subscriptions").insert({ user_id: user.id, addon_key: key });
    if (res.error) {
      if (res.error.code === "23505") throw new CreditActionError("ALREADY_ACTIVE", "You already have this add-on.", 409);
      throw new Error(`Failed to add ${key}: ${res.error.message}`);
    }
  }
  return { key, active: true };
}

/** One tap, no retention detour (SPEC §2 rule 15). */
export async function cancelAddon(user: SessionUser, key: string): Promise<{ key: AddonKey; active: false }> {
  if (!isAddonKey(key)) throw new CreditActionError("NOT_FOUND", "Unknown add-on.", 404);
  const now = new Date().toISOString();
  if (isDemoMode()) {
    const rec = getDemoCreditState(user).addons.find((a) => a.key === key && a.status === "active");
    if (!rec) throw new CreditActionError("NOT_ACTIVE", "This add-on isn't active.", 409);
    rec.status = "canceled";
    rec.canceledAt = now;
  } else {
    const supabase = await createSupabaseServerClient();
    const res = await supabase
      .from("addon_subscriptions")
      .update({ status: "canceled" })
      .eq("user_id", user.id)
      .eq("addon_key", key)
      .eq("status", "active")
      .select("id");
    if (res.error) throw new Error(`Failed to cancel ${key}: ${res.error.message}`);
    if (!res.data?.length) throw new CreditActionError("NOT_ACTIVE", "This add-on isn't active.", 409);
  }
  return { key, active: false };
}

export interface MembershipChange {
  status: "active" | "canceled";
  lineStatus: "open" | "closed" | "charged_off";
  balanceCents: number;
}

/**
 * Cancel the membership: no more monthly fees from today, and add-ons stop
 * too. The line stays open only until any remaining balance is paid, then
 * closes and is reported as closed at the member's request.
 */
export async function cancelMembership(user: SessionUser): Promise<MembershipChange> {
  const now = new Date().toISOString();
  if (isDemoMode()) {
    const state = getDemoCreditState(user);
    if (!state.membership || !state.line) throw new CreditActionError("NOT_ENROLLED", "You don't have a membership.", 404);
    if (state.membership.status === "canceled") throw new CreditActionError("NOT_ACTIVE", "Your membership is already canceled.", 409);
    state.membership.status = "canceled";
    state.membership.canceledAt = now;
    for (const a of state.addons) {
      if (a.status === "active") {
        a.status = "canceled";
        a.canceledAt = now;
      }
    }
    if (state.line.balanceCents <= 0) {
      state.line.status = "closed";
      state.line.closedAt = now;
      state.line.closedAtConsumerRequest = true;
    }
    return { status: "canceled", lineStatus: state.line.status, balanceCents: state.line.balanceCents };
  }

  const supabase = await createSupabaseServerClient();
  const res = await supabase.from("membership_subscriptions").update({ status: "canceled" }).eq("user_id", user.id).neq("status", "canceled").select("id");
  if (res.error) throw new Error(`Failed to cancel membership: ${res.error.message}`);
  if (!res.data?.length) throw new CreditActionError("NOT_ACTIVE", "Your membership is already canceled.", 409);
  const addons = await supabase.from("addon_subscriptions").update({ status: "canceled" }).eq("user_id", user.id).eq("status", "active");
  if (addons.error) throw new Error(`Failed to cancel add-ons: ${addons.error.message}`);
  // Members can't edit their line directly; closing a paid-off line is a server action.
  const { lineClosed } = await afterStatementPaid(createSupabaseServiceClient(), user.id);
  const lineRes = await supabase.from("virtual_credit_lines").select("status, balance_cents").eq("user_id", user.id).maybeSingle();
  const line = lineRes.data as { status: MembershipChange["lineStatus"]; balance_cents: number } | null;
  return { status: "canceled", lineStatus: lineClosed ? "closed" : (line?.status ?? "closed"), balanceCents: Number(line?.balance_cents ?? 0) };
}

/** Undo a cancellation while the line is still open. */
export async function resumeMembership(user: SessionUser): Promise<MembershipChange> {
  if (isDemoMode()) {
    const state = getDemoCreditState(user);
    if (!state.membership || !state.line) throw new CreditActionError("NOT_ENROLLED", "You don't have a membership.", 404);
    if (state.line.status !== "open") throw new CreditActionError("LINE_NOT_OPEN", "Your line is closed. Contact support to reopen it.", 409);
    if (state.membership.status === "active") throw new CreditActionError("ALREADY_ACTIVE", "Your membership is already active.", 409);
    state.membership.status = "active";
    state.membership.canceledAt = null;
    return { status: "active", lineStatus: state.line.status, balanceCents: state.line.balanceCents };
  }
  const supabase = await createSupabaseServerClient();
  const lineRes = await supabase.from("virtual_credit_lines").select("status, balance_cents").eq("user_id", user.id).maybeSingle();
  const line = lineRes.data as { status: MembershipChange["lineStatus"]; balance_cents: number } | null;
  if (!line) throw new CreditActionError("NOT_ENROLLED", "You don't have a membership.", 404);
  // A closed line can only be reopened by support (enforced by the database too).
  if (line.status !== "open") throw new CreditActionError("LINE_NOT_OPEN", "Your line is closed. Contact support to reopen it.", 409);
  const res = await supabase.from("membership_subscriptions").update({ status: "active" }).eq("user_id", user.id).eq("status", "canceled").select("id");
  if (res.error) throw new Error(`Failed to resume membership: ${res.error.message}`);
  if (!res.data?.length) throw new CreditActionError("ALREADY_ACTIVE", "Your membership is already active.", 409);
  return { status: "active", lineStatus: line.status, balanceCents: Number(line.balance_cents) };
}

/* ------------------------------------------------------------------ */
/* Enrollment                                                          */
/* ------------------------------------------------------------------ */

/**
 * Open a credit builder line (idempotent). Subscribing is the member's own
 * request: inserting the membership as the member makes the database open
 * the line the fee is charged to.
 */
export async function enroll(user: SessionUser): Promise<{ lineId: string; limitCents: number; created: boolean }> {
  if (isDemoMode()) {
    const state = getDemoCreditState(user);
    return { lineId: state.line!.id, limitCents: state.line!.limitCents, created: false };
  }
  const supabase = await createSupabaseServerClient();
  const existing = await supabase.from("membership_subscriptions").select("status").eq("user_id", user.id).maybeSingle();
  if (existing.error) throw new Error(`Failed to load membership: ${existing.error.message}`);
  let created = false;
  if (!existing.data) {
    const ins = await supabase.from("membership_subscriptions").insert({ user_id: user.id });
    if (ins.error && ins.error.code !== "23505") throw new Error(`Failed to start membership: ${ins.error.message}`);
    created = !ins.error;
  } else if ((existing.data as { status: string }).status === "canceled") {
    await resumeMembership(user);
  }
  const modules = await supabase.from("user_modules").upsert({ user_id: user.id, module: "credit" }, { onConflict: "user_id,module", ignoreDuplicates: true });
  if (modules.error) console.error("user_modules upsert failed", modules.error.message);
  const lineRes = await supabase.from("virtual_credit_lines").select("*").eq("user_id", user.id).single();
  if (lineRes.error) throw new Error(`Failed to open credit line: ${lineRes.error.message}`);
  const line = mapLine(lineRes.data as CreditLineRow);
  return { lineId: line.id, limitCents: line.limitCents, created };
}

/* ------------------------------------------------------------------ */
/* Affiliate click tracking                                            */
/* ------------------------------------------------------------------ */

/** Returns the stored offer URL to redirect to (never a caller-supplied URL). */
export async function recordOfferClick(user: SessionUser, offerId: string): Promise<string | null> {
  const data = await loadCreditData(user);
  const offer = data.offers.find((o) => o.id === offerId);
  if (!offer) return null;
  if (!isDemoMode()) {
    const supabase = await createSupabaseServerClient();
    const res = await supabase.from("affiliate_clicks").insert({ user_id: user.id, offer_id: offer.id });
    if (res.error) console.error("affiliate click not recorded", res.error.message);
  }
  return offer.url;
}

/* ------------------------------------------------------------------ */
/* Ledger for reporting (service role, admin flows only)               */
/* ------------------------------------------------------------------ */

export async function loadLineLedger(service: ServiceClient, lineId: string) {
  const [s, p, t] = await Promise.all([
    service.from("credit_statements").select("*").eq("credit_line_id", lineId).order("period_end", { ascending: true }),
    service.from("credit_payments").select("*").eq("credit_line_id", lineId).order("paid_at", { ascending: true }),
    service.from("credit_transactions").select("id, kind, amount_cents, description, posted_at, statement_id").eq("credit_line_id", lineId),
  ]);
  if (s.error) throw new Error(`Failed to load statements: ${s.error.message}`);
  if (p.error) throw new Error(`Failed to load payments: ${p.error.message}`);
  if (t.error) throw new Error(`Failed to load transactions: ${t.error.message}`);
  const transactions = (t.data ?? []) as TransactionRow[];
  return {
    statements: ((s.data ?? []) as StatementRow[]).map((row) => mapStatement(row, transactions)),
    payments: ((p.data ?? []) as PaymentRow[]).map(mapPayment),
  };
}
