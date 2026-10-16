# ShiftSave — Build Spec (contract for every builder)

This is the single contract all modules are built against. If something you
need is not here, choose the simplest option that fits these conventions and
note it in your final report. **Do not edit files you do not own** (see §6);
if you need a change in a shared file, describe it in your report instead.

## 1. Product (consolidated from the founder's briefs)

ShiftSave is one app with four decoupled modules. A user can enter through any
door; the modules link up so shift earnings can fund credit-building.

| Module | What it is |
|---|---|
| **A — Credit Engine** | Kikoff-style closed-loop credit builder. Each member gets a `virtual_credit_line` ($500 default limit) usable only in the ShiftSave store. The $5/mo membership is charged to the line; the member repays it in real money (card, ACH, or ShiftSave Wallet). Statements/payments are formatted as Metro 2® records and handed to a credentialed data-furnisher partner. Gamification: on-time streaks, badges, a limit "level-up" to $1,000 after 3 on-time months, referrals ("1 free month per friend"). At a 660 score, a card-matching widget unlocks (affiliate offers). AI Bill Negotiator: upload a bill → Claude vision finds overcharges → negotiation script. Add-ons: rent/utility reporting ($4/mo), AI coach ($10/mo). |
| **B — Wallet & Cards** | Revolut-style wallet: balance, ledger, income streams/direct-deposit targets, virtual cards (permanent, single-use, temporary) via a card-issuing provider (Stripe Issuing or Lithic). Shift pay lands here same-day; membership fee can auto-sweep from the balance. |
| **C — Shift Marketplace** | B2B emergency staffing. Tier 1 ($22 bill / $15 pay) and Tier 2 ($35 / $18). Managers post a call-out → SMS blast to opted-in, eligible workers within 15 miles → first valid shortcode reply claims it (atomic). Tier 1 → Tier 2 after 2 on-time, well-rated shifts; platform pays the $25 background check out of margin; admin logs an oral-fluid swab in the Swab Verification panel. MSA with Section 8 non-circumvention / $4,500 conversion fee. Chat poach filter flags "hire you directly", "pay you cash", phone-number swaps, etc. and shows the client a Section 8 reminder. Manager approval → Stripe charge → worker paid (Stripe Connect or Wallet) → margin to platform. |
| **D — Lead Engine** | Python job, daily at 04:00, pulls retail/c-store/warehouse postings with urgency words from **permitted** sources, extracts company + public business contact, drafts a tailored outreach email with Claude, and queues it for human approval. |

Money flows: membership $5.00 → $1.50 reporting vendor + $0.00 impact (off by default) + remainder platform, recorded per payment in `treasury_allocations`.

## 2. Non-negotiable compliance rules (the "legal engineering" layer)

These come from a review of the briefs. They are design requirements, not suggestions — build them in.

1. **Section 8 is conspicuous, not hidden.** Its own heading, visually boxed, listed in the MSA summary, and acknowledged with a separate checkbox + initials at signing. Courts refuse to enforce buried fee clauses (procedural unconscionability, lack of assent), so burying it would defeat it. Wording: client may not hire/engage introduced Personnel off-platform for the term + 12 months; $4,500 per person as liquidated damages / conversion fee, a reasonable pre-estimate of recruiting/screening/lost-margin costs, not a penalty; client may instead convert a worker by paying the fee. **Never** describe people as "assets of the platform". The clause binds the **client** only — workers stay free to work anywhere (no worker non-compete). Everything is a template marked "have a licensed attorney review before use".
2. **Chat monitoring is disclosed** (thread header + MSA/ToS). The poach filter warns and flags for admin review; it never auto-fines anyone.
3. **SMS (TCPA/CTIA):** only to workers with `sms_opt_in = true` (timestamped consent). Honor STOP/START/HELP keywords. Every blast includes "Reply STOP to opt out".
4. **Background checks (FCRA):** order only after the worker accepts a standalone disclosure + authorization (timestamp stored). Platform pays — **never deduct the fee from worker pay**. A `consider` result goes to admin review → pre-adverse-action notice → wait 5 business days → final notice. No automated rejection.
5. **Drug screens:** worker consent recorded before collection. The admin panel records a result with collector, kit lot number and a photo of the test device; there is **no "override to passed"** — a result can only be entered as a new append-only `drug_screen_logs` row, collector ≠ worker, evidence required. A rapid oral-fluid **non-negative** is presumptive: status becomes `pending` (lab confirmation), not `failed`.
6. **Credit line is real.** The line can actually be spent in the ShiftSave store, so the reported limit is true. A level-up raises a real, spendable limit. Metro 2 records report only actual balances, payment history and status; FCRA dispute intake exists (`credit_reporting_disputes`). Data goes to a credentialed furnisher partner — the export is "prepared for delivery", never sent to bureaus directly.
7. **No credit-repair claims (CROA).** Copy says "credit builder", never "repair/fix your credit"; no promised score gains; show "Results vary. Late payments can lower your score." near score UI.
8. **Affiliate offers:** "ShiftSave may earn a commission" disclosure on the widget; offers ranked by fit (score, annual fee), **never** by bounty. Scores come from a soft-inquiry partner with recorded consent.
9. **Impact/charity claims** only if real: the impact split is 0 by default; when non-zero, UI copy is computed from actual `treasury_allocations` and names the real partner.
10. **Autopay sweeps** need a stored, revocable authorization (Reg E style): who, when, amount, text version. Receipt after each sweep.
11. **Cards:** never store PAN/CVV. Show last4 only; full details only via the issuer's PCI-compliant UI component (stub in demo).
12. **Bill negotiator** suggests scripts; it never contacts providers or impersonates the member.
13. **Lead engine:** only official APIs, RSS feeds, or pages whose robots.txt allows the path; identifying User-Agent; rate limits; no CAPTCHA/anti-bot evasion or login-walled scraping. Indeed/ZipRecruiter/Craigslist terms prohibit scraping — ship those as disabled adapters that require a licensed feed/API. Only business contact info published in the posting. Drafts require human approval; CAN-SPAM footer (physical address + opt-out) and suppression-list check before any send.
14. **Worker classification:** `worker_compliance.engagement_type` (`contractor_1099` | `w2_eor`). Tier 2 register/keyholder roles carry high misclassification risk — docs recommend W-2 via an Employer-of-Record; code supports both.
15. **No dark patterns:** cancel membership/add-ons in ≤2 taps; streak copy celebrates, never threatens.

## 3. Conventions

- **Next.js 16 App Router**, React 19, TypeScript strict, Tailwind v4. In pages and route handlers `params`/`searchParams` are **Promises** (`const { id } = await params`). Middleware is `src/proxy.ts` (already written).
- **Demo mode** (`isDemoMode()` from `@/lib/env`): when Supabase env is missing, pages read from `src/lib/demo/<module>.ts` and API routes return realistic mocks (no network calls to Stripe/Twilio/Anthropic unless their key is set). Every page must render in demo mode. In live mode, use `createSupabaseServerClient()` (RLS) or `createSupabaseServiceClient()` (webhooks/admin after role check) from `@/lib/supabase/server`.
- **Auth:** `getSessionUser()` / `requireRole(...roles)` from `@/lib/auth`. Wrap route handlers with `handle()` from `@/lib/http`; validate bodies with `zod`.
- **Money:** integer cents everywhere (`*_cents` columns, `*Cents` fields). Format with `formatCents` from `@/lib/money`. All rates/fees come from `@/lib/pricing` — never hard-code a dollar figure.
- **UI kit** (`@/components/ui/*`): `Card`, `CardTitle`, `Button`, `ButtonLink`, `ActionCircle`, `Badge`, `StatTile`, `PageHeader`, `EmptyState`, `cn`. Semantic colors only: `bg-canvas`, `bg-surface`, `bg-surface-2`, `text-ink`, `text-muted`, `border-line`, `bg-accent`/`text-accent`, `from-accent to-accent-2`, `text-positive|warning|danger`. Icons: `lucide-react`. Mobile-first: works at 375px wide, no horizontal scroll; the shell adds bottom padding for the tab bar. Modals = bottom sheets on mobile (`animate-sheet-up`).
- **Demo state:** demo-mode actions (claim a shift, create a card, sign the MSA …) may mutate state so the UI reflects them during a session. Keep that state in `demoStore(key, init)` from `@/lib/demo/store` (globalThis-backed), never in plain module variables. The Legal builder owns `src/lib/demo/msa.ts` exporting `getDemoMsaSignature(): { signerName: string; signedAt: string; version: string } | null` and `setDemoMsaSignature(sig)`; demo starts **unsigned** so the signing flow is visible; C-BE's `hasSignedMsa` uses it in demo mode.
- Do **not** run `next build` (other builders are writing files concurrently and it writes `.next/`); use `npx tsc --noEmit` and `npx vitest run <your test files>`. Type errors in files you do not own may be other builders' work in progress — ignore those, fix yours.
- Server Components by default; `"use client"` only for interactive leaves.
- Shared domain types: `@/lib/types` (read-only for builders). Module-local types live in your own files.
- Tests: vitest, files `src/**/*.test.ts`. Pure logic (parsers, formatters, pricing, state machines) must have tests.
- Claude API code: TypeScript SDK `@anthropic-ai/sdk` (installed) / Python SDK `anthropic`. Model `claude-opus-5-5`, adaptive thinking is default (do not send `budget_tokens` or `thinking: {type:"disabled"}`), structured outputs via `output_config.format`. Read the skill docs at `/tmp/claude-0/bundled-skills/2.1.301/37923907d9151f5cd19ff1fbe63ef3dc/claude-api/{typescript|python}/claude-api/README.md` and `tool-use.md` (structured outputs section) before writing that code; do not guess SDK APIs. Enable server-side refusal fallbacks per that doc.

## 4. Route map

| Route | Owner | Purpose |
|---|---|---|
| `/` | shell (done) | Hub with module "doors" |
| `/credit` | A | Credit line card, utilization, statement, pay now, streak, score + disclaimer, 660 offers widget |
| `/credit/store` | A | Closed-loop store (spend the line) |
| `/credit/bills` | A | AI Bill Negotiator upload + results |
| `/credit/rewards` | A | Streaks, badges, level-up progress, referrals, add-ons |
| `/wallet` | B | Balance hero, actions, ledger, income streams, autopay authorization |
| `/wallet/cards` | B | Virtual card carousel, create/freeze/cancel |
| `/shifts` | C-UI | Worker dispatch feed (map + card stack + claim sheet), Tier 2 upgrade invite, compliance status |
| `/shifts/[id]` | C-UI | Shift detail + worker↔client chat |
| `/business` | C-UI | Manager dashboard: week calendar grid, post emergency call-out, active stand-ins, history, invoices; MSA gate |
| `/business/shifts/[id]` | C-UI | Manager shift detail: chat (with Section 8 warning), approve & rate |
| `/business/msa` | Legal | MSA reader + signing (Section 8 acknowledgment) |
| `/admin` | C-UI | Admin overview: poach flags queue, Swab Verification panel, Tier 2 queue, background check reviews |
| `/admin/leads` | D | Lead targets + outreach draft review/approve |

API routes (all under `src/app/api/`):

| Route | Owner |
|---|---|
| `shifts` (GET list for viewer / POST create emergency shift → dispatch), `shifts/[id]/claim`, `shifts/[id]/approve` | C-BE |
| `twilio/inbound` (claim by SMS code, STOP/START/HELP) | C-BE |
| `chat/messages` (GET `?threadId=`, POST `{threadId, body}`) | C-BE |
| `admin/poach-flags` (GET, PATCH status), `admin/drug-screens` (POST record), `admin/background-checks` (POST order, PATCH review) | C-BE |
| `stripe/webhook` | C-BE |
| `msa/sign` | Legal |
| `credit/*`, `bills/analyze` | A |
| `wallet/*` | B |
| `leads/*` | D |

## 5. Data model (Supabase / Postgres)

Owner: DB. All tables in `public`, uuid PKs (`gen_random_uuid()`), `created_at timestamptz default now()`, money as `bigint` cents, RLS **enabled on every table**. PostGIS `geography(Point,4326)` for locations.

Migration files: `0001_core.sql`, `0002_wallet.sql`, `0003_credit.sql`, `0004_shifts.sql`, `0005_leads.sql`, `0006_rls.sql`, `0007_functions.sql` (or fold functions into their module file), plus `supabase/seed.sql`.

**Core:** `organizations`(kind `client_company`), `users` (id = `auth.users.id`, email, full_name, phone_e164, role `member|worker|client_manager|admin`, organization_id, home_geo, sms_opt_in, sms_opt_in_at), `user_modules`(user_id, module `credit|wallet|shifts`), `platform_config` (key/value mirror of `src/lib/pricing.ts`), `notifications`, `audit_log` (append-only), `consents` (user_id, kind `fcra_disclosure|drug_screen|sms|autopay|soft_pull|esign`, text_version, accepted_at, ip_address, revoked_at).

**Wallet (B):** `wallets`, `ledger_entries` (append-only; direction `credit|debit`, amount_cents > 0, category per `LedgerCategory`), `virtual_cards` (provider_card_id, last4, brand, kind, status, nickname, spend_limit_cents, expires_at — **no PAN/CVV columns**), `income_streams`, `autopay_authorizations`.

**Credit (A):** `virtual_credit_lines` (limit_cents default 50000, balance_cents, status, account_number for Metro 2), `credit_store_products`, `credit_transactions`, `credit_statements`, `credit_payments`, `membership_subscriptions` (free_months_remaining for referrals), `treasury_allocations` (bucket `reporting_vendor|impact|platform|background_check|drug_screen`), `metro2_exports`, `credit_score_snapshots`, `credit_reporting_disputes`, `affiliate_offers`, `affiliate_unlocks`, `affiliate_clicks`, `user_badges`, `referrals`, `addon_subscriptions`, `bill_analyses`.

**Shifts (C):** `client_locations`, `shifts` (client_id, organization_id, location_id, location, geo, position_title, tier_required 1|2, hourly_billing_rate_cents, hourly_pay_rate_cents, scheduled_start, scheduled_end, status per `ShiftStatus`, is_emergency, claimed_by, claimed_at, approved_at), `shift_dispatches` (claim_code, expires_at, twilio_sid, outcome), `worker_compliance` (fields per `WorkerCompliance` + stripe_connect_account_id, background_check_provider_id), `background_checks`, `drug_screen_logs` (append-only), `shift_ratings`, `payouts`, `msa_versions`, `contract_signatures` (company_id → organizations, signer_id, msa_version, msa_signed, section8_acknowledged, section8_initials, signed_at, ip_address, user_agent, document_sha256), `chat_threads`, `chat_messages`, `poach_flags`.

**Leads (D):** `lead_sources`, `scrape_runs`, `lead_targets` (dedupe_hash unique), `outreach_drafts`, `email_suppressions`.

**RPC functions** (security definer where noted; builders call these via `supabase.rpc(name, args)` in live mode):

| Function | Returns | Notes |
|---|---|---|
| `workers_within_radius(p_shift_id uuid, p_miles numeric default 15)` | table(user_id, full_name, phone_e164, distance_miles) | opted-in workers whose `compliance_tier >= tier_required` |
| `create_dispatches(p_shift_id uuid, p_miles numeric default 15)` | table(dispatch_id, user_id, phone_e164, claim_code) | inserts a unique 4-digit code per worker, 30-min expiry |
| `claim_shift(p_shift_id uuid, p_worker_id uuid)` | boolean | atomic (`update … where status='open'`), checks tier |
| `claim_shift_by_code(p_phone text, p_code text)` | uuid (shift id) or null | for Twilio inbound |
| `approve_shift(p_shift_id uuid, p_rating int, p_on_time boolean)` | uuid (payout id) | caller must be the shift's manager; computes totals from rates × hours; inserts rating + pending payout; updates worker stats; calls tier-2 eligibility |
| `evaluate_tier2_eligibility(p_worker_id uuid)` | boolean | sets `tier2_invited_at` + notification when rules in `TIER2_UPGRADE` met |
| `record_drug_screen(p_worker_id uuid, p_kit_lot text, p_result text, p_evidence_path text, p_collected_at timestamptz, p_notes text)` | uuid | admin only; collector = auth.uid() ≠ worker; requires drug_screen consent + evidence; non_negative → `pending` |
| `wallet_post_entry(p_wallet_id uuid, p_direction text, p_amount_cents bigint, p_category text, p_description text, p_reference_type text, p_reference_id uuid)` | uuid | updates cached balance; debit cannot overdraw |
| `record_membership_payment(p_statement_id uuid, p_amount_cents bigint, p_method text, p_provider_payment_id text)` | uuid | inserts payment; trigger writes `treasury_allocations` split |
| `sweep_membership_from_wallet(p_user_id uuid)` | uuid or null | needs active autopay authorization + balance |
| `apply_credit_level_up(p_credit_line_id uuid)` | boolean | raises limit when 3 consecutive on-time statements |
| trigger on `credit_score_snapshots` | — | first score ≥ 660 → `affiliate_unlocks` row + notification |

Realtime: add `shifts` and `chat_messages` to the `supabase_realtime` publication. Storage buckets (private): `bill-uploads`, `drug-screen-evidence`.

## 6. File ownership

| Builder | Owns (create/edit only these) |
|---|---|
| **DB** | `supabase/**`, `docs/DATA_MODEL.md` |
| **A (Credit)** | `src/lib/credit/**`, `src/lib/ai/**`, `src/lib/demo/credit.ts`, `src/app/credit/**`, `src/app/api/credit/**`, `src/app/api/bills/**`, `src/components/credit/**` |
| **B (Wallet)** | `src/lib/wallet/**`, `src/lib/integrations/issuing.ts`, `src/lib/demo/wallet.ts`, `src/app/wallet/**`, `src/app/api/wallet/**`, `src/components/wallet/**` |
| **C-BE (Shifts backend)** | `src/lib/shifts/**` (incl. `antiPoach.ts`, `dispatch.ts`, tests), `src/lib/integrations/{twilio,stripe,checkr}.ts`, `src/lib/demo/shifts.ts`, `src/app/api/{shifts,twilio,chat,admin,stripe}/**` |
| **C-UI (Shifts UI)** | `src/app/shifts/**`, `src/app/business/**` **except** `src/app/business/msa/**`, `src/app/admin/page.tsx` + `src/app/admin/(components)` if needed, `src/components/shifts/**`, `src/components/admin/**`, `src/components/chat/**` |
| **Legal** | `src/content/**`, `src/lib/demo/msa.ts`, `src/components/legal/**`, `src/app/business/msa/**`, `src/app/api/msa/**`, `docs/COMPLIANCE.md`, `docs/legal/**` |
| **D (Leads)** | `scraper/**`, `src/app/admin/leads/**`, `src/app/api/leads/**`, `src/lib/demo/leads.ts` |

Shared, already written, read-only: `src/lib/{types,pricing,money,env,auth,http}.ts`, `src/lib/supabase/*`, `src/components/ui/*`, `src/components/shell/*`, `src/app/{layout,template,page}.tsx`, `src/proxy.ts`, `src/app/globals.css`.

## 7. Cross-module contracts (exact exports)

C-UI and Legal code against these before they exist — implement them exactly.

```ts
// src/lib/shifts/antiPoach.ts  (C-BE)
export interface PoachMatch { ruleId: string; label: string; excerpt: string; severity: PoachSeverity }
export interface PoachScanResult { flagged: boolean; severity: PoachSeverity | null; matches: PoachMatch[]; redactedText: string }
// redactedText = the message with phone numbers / emails / payment & social handles replaced by "[contact info hidden]".
// The chat API stores and delivers redactedText (that is the "block"); phrase-only matches are delivered as-is but flagged.
export function scanMessage(text: string): PoachScanResult;

// src/lib/integrations/stripe.ts (C-BE) — shared Stripe client (B's issuing.ts imports it)
export function getStripe(): Stripe; // throws a clear error when STRIPE_SECRET_KEY is missing

// src/lib/demo/shifts.ts  (C-BE) — demo fixtures used by C-UI pages
export const demoShifts: Shift[];
export const demoWorkerCompliance: WorkerCompliance[];
export const demoPoachFlags: PoachFlag[];
export const demoDrugScreenLogs: DrugScreenLog[];
export const demoChat: Record<string /* threadId */, ChatMessage[]>;
export const demoThreadForShift: Record<string /* shiftId */, string /* threadId */>;
export const demoPayouts: Payout[];

// src/lib/shifts/queries.ts  (C-BE) — server-only data access, demo or live
export async function listShiftsForWorker(user: SessionUser): Promise<Shift[]>;   // open + mine, with distanceMiles
export async function listShiftsForManager(user: SessionUser): Promise<Shift[]>;
export async function getShift(id: string, user: SessionUser): Promise<Shift | null>;
export async function getWorkerCompliance(userId: string): Promise<WorkerCompliance | null>;
export async function listComplianceQueue(): Promise<WorkerCompliance[]>;         // admin
export async function listPoachFlags(): Promise<PoachFlag[]>;                      // admin
export async function listDrugScreenLogs(workerId?: string): Promise<DrugScreenLog[]>;
export async function getThreadMessages(threadId: string, user: SessionUser): Promise<ChatMessage[]>;
export async function threadIdForShift(shiftId: string): Promise<string | null>;
export async function hasSignedMsa(organizationId: string): Promise<boolean>;

// HTTP (C-BE)
// POST /api/shifts            {positionTitle, tierRequired, locationId?, location, lat, lng, scheduledStart, scheduledEnd, notes?, isEmergency}
//                             -> { shift: Shift, dispatched: number, quote: ShiftQuote }   (403 {error:"MSA_REQUIRED"} if org hasn't signed)
// POST /api/shifts/[id]/claim -> { ok: true, shift: Shift } | 409 { error: "ALREADY_CLAIMED" } | 403 { error: "TIER_REQUIRED" }
// POST /api/shifts/[id]/approve {rating: 1-5, onTime: boolean} -> { payout: Payout }
// GET  /api/chat/messages?threadId=  -> { messages: ChatMessage[] }
// POST /api/chat/messages {threadId, body} -> { message: ChatMessage, scan: PoachScanResult, showSection8Warning: boolean }
//      showSection8Warning is true only when the SENDER is a client_manager and scan.flagged
// PATCH /api/admin/poach-flags {id, status} -> { flag: PoachFlag }
// POST /api/admin/drug-screens {workerId, kitLotNumber, result, evidencePath, collectedAt, notes?} -> { log: DrugScreenLog, compliance: WorkerCompliance }
//      (demo mode: accept evidencePath as any non-empty string; live: path in drug-screen-evidence bucket)
// POST /api/admin/background-checks {workerId} -> { status } (409 if no FCRA consent); PATCH {workerId, decision: "clear"|"pre_adverse"|"final_adverse"}

// src/content/msa.ts  (Legal)
export const MSA_VERSION: string;            // e.g. "2026-10-16"
export interface MsaSection { id: string; number: string; title: string; paragraphs: string[]; conspicuous?: boolean }
export const MSA_SECTIONS: MsaSection[];
export const SECTION_8_PLAIN_SUMMARY: string; // one-paragraph plain-English summary
export function msaDocumentText(): string;    // canonical text that is hashed at signing

// src/components/legal/Section8Notice.tsx  (Legal) — client component OK
export function Section8Notice(props: { variant: "inline" | "chat-warning"; matchedLabels?: string[]; onDismiss?: () => void }): JSX.Element;
// src/components/legal/ChatMonitoringNotice.tsx (Legal)
export function ChatMonitoringNotice(): JSX.Element;

// src/content/consents.ts (Legal) — exact consent texts + versions
export const CONSENTS: Record<"fcra_disclosure" | "drug_screen" | "sms" | "autopay" | "soft_pull" | "esign", { version: string; title: string; body: string[] }>;

// src/lib/wallet/queries.ts (B) — used by A for the autopay toggle display
export async function getWalletSummary(user: SessionUser): Promise<{ wallet: Wallet; autopayActive: boolean }>;
```
