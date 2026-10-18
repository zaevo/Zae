# EzWerkz database (Supabase)

Postgres schema, RLS, RPCs and seed data for EzWerkz. The full reference
(ER diagrams, RPC table, RLS model) is in [`docs/DATA_MODEL.md`](../docs/DATA_MODEL.md).

```
supabase/
  migrations/
    0001_core.sql      extensions, users/orgs, platform_config, notifications, audit_log, consents, RLS helpers
    0002_wallet.sql    wallets, append-only ledger, virtual cards, income streams, autopay authorizations
    0003_credit.sql    credit line, store, statements, payments, treasury split, Metro 2, scores, offers, rewards
    0004_shifts.sql    shifts, dispatch, compliance (FCRA/drug screens), payouts, MSA signatures, chat, realtime, storage
    0005_leads.sql     lead sources, runs, targets, outreach drafts, suppressions
  seed.sql             demo org + Atlanta location, store products, card offers, MSA version, lead sources
  validation/          throwaway-Postgres harness (stub + 237-assertion test suite + race test)
```

## Apply

**Local (Supabase CLI)**

```bash
supabase init            # only if supabase/config.toml does not exist yet; keeps migrations/
supabase start
supabase db reset        # applies migrations/ in order, then seed.sql
```

**Hosted project**

```bash
supabase link --project-ref <ref>
supabase db push                       # migrations only
psql "$DATABASE_URL" -f supabase/seed.sql   # optional demo/reference data (idempotent)
```

Or paste each migration into the SQL editor in order (0001 → 0005), then `seed.sql`.

PostGIS and pgcrypto are created in the `extensions` schema (Supabase's default).
Migration 0004 adds `shifts` and `chat_messages` to the `supabase_realtime`
publication and creates the private buckets `bill-uploads` and
`drug-screen-evidence` with their storage policies.

Then set `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` and
`SUPABASE_SERVICE_ROLE_KEY` (see `.env.example`); the app leaves demo mode.

## First accounts

Sign-up always creates a `member` (with the `credit` and `wallet` modules and a
wallet). `raw_user_meta_data` can set `full_name` but never a role. Promote
people from the SQL editor (a trusted session):

```sql
-- first admin
update public.users set role = 'admin' where email = 'ops@yourcompany.com';

-- a client manager for the seeded demo store
update public.users
   set role = 'client_manager', organization_id = '00000000-0000-4000-8000-0000000000c1'
 where email = 'manager@example.com';
```

Users can also self-serve: `rpc('enroll_module', { p_module: 'shifts' })` turns a
member into a Tier 1 worker; `rpc('register_business', { p_name })` creates a
company and makes the caller its manager (posting still requires the MSA).

## Calling conventions

| Client | Use for |
|---|---|
| `createSupabaseServerClient()` (user session, RLS) | everything a signed-in user does for themselves: reading their rows, store purchases, subscribing/canceling, consents, cards, chat, `claim_shift`, `approve_shift`, `record_drug_screen` (admin), wallet payments |
| `createSupabaseServiceClient()` (service role, after your own role check) | `create_dispatches` / `workers_within_radius` (they return phone numbers), `claim_shift_by_code` (Twilio), card/ACH `record_membership_payment` after Stripe confirms, payout status updates, `cut_credit_statement` / `post_membership_charge` / `sweep_membership_from_wallet` cron jobs, score snapshots, background-check provider webhooks, the lead scraper |

RPCs raise errors whose `message` is a stable code (`TIER_REQUIRED`,
`MSA_REQUIRED`, `INSUFFICIENT_FUNDS`, `FCRA_CONSENT_REQUIRED`, …) with a human
sentence in `details`. `claim_shift` returns `false` only when someone else won
the race (map to 409 `ALREADY_CLAIMED`).

Things the database enforces even if app code forgets:

- Balances (`wallets.available_cents`, `virtual_credit_lines.balance_cents/limit_cents`)
  and compliance statuses (`worker_compliance.*_status`, `compliance_tier`) cannot
  be written directly by anyone, including the service role. They change only
  through ledger entries, credit transactions/payments, `background_checks`,
  `drug_screen_logs` and `approve_shift`.
- `ledger_entries`, `drug_screen_logs`, `audit_log`, `treasury_allocations` and
  `contract_signatures` are append-only; consents only accept `revoked_at`.
- Shift rates come from `platform_config`; store prices from `credit_store_products`.
- Hard-deleting a user who has financial or compliance history fails by design
  (retention). Deactivate instead.

## Pricing mirror

`platform_config` mirrors `src/lib/pricing.ts`. If a number changes there, add a
migration that updates the matching key (changes are audited in `audit_log`).

## Validate locally

Needs only a Postgres 15+ server you can reach as a superuser (no Supabase CLI,
PostGIS optional):

```bash
PGHOST=localhost PGPORT=5432 PGUSER=postgres supabase/validation/run.sh
```

It creates a throwaway database, applies a Supabase stand-in (roles, `auth`,
`storage`, realtime publication; a PostGIS stub if PostGIS is missing), every
migration, the seed twice, the functional test suite, and a two-session
`claim_shift` race. Never apply `validation/supabase_stub.sql` to a real project.
