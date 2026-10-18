-- =============================================================================
-- 0003_credit.sql — Module A: closed-loop credit builder.
--   virtual_credit_lines, store products, transactions, statements, payments,
--   membership + add-on subscriptions, treasury_allocations (append-only),
--   metro2_exports, score snapshots, FCRA disputes, affiliate offers/unlocks/
--   clicks, badges, referrals, bill_analyses.
--   RPCs: record_membership_payment, sweep_membership_from_wallet,
--   apply_credit_level_up (+ cut_credit_statement, post_membership_charge,
--   redeem_referral_code, credit_on_time_streak, ranked_affiliate_offers,
--   treasury_impact_summary).
--
-- Invariants enforced here:
--   * The line is real: purchases cannot exceed limit_cents; balance_cents and
--     limit_cents change only through transactions/payments/level-up code.
--   * Every succeeded payment is split into treasury_allocations
--     (reporting_vendor / impact / platform). Impact stays 0 unless a real
--     partner is configured.
--   * Scores require a recorded soft-pull consent.
--   * Metro 2 exports are "prepared for delivery" to a furnisher partner.
-- =============================================================================

create sequence public.credit_account_number_seq start with 1000000001;

alter table public.users
  add column referral_code text unique
    default upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 8))
    check (referral_code ~ '^[A-Z0-9]{6,12}$');

-- -----------------------------------------------------------------------------
-- Tables
-- -----------------------------------------------------------------------------

create table public.credit_store_products (
  id uuid primary key default gen_random_uuid(),
  sku text not null unique check (sku ~ '^[a-z0-9-]+$'),
  name text not null check (length(btrim(name)) between 1 and 120),
  description text not null default '',
  kind text not null check (kind in ('membership', 'course', 'ebook', 'tool')),
  price_cents bigint not null check (price_cents >= 0),
  billing_interval text not null default 'one_time' check (billing_interval in ('one_time', 'monthly')),
  active boolean not null default true,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table public.credit_store_products is 'The closed-loop store: the only place a virtual credit line can be spent.';

create table public.virtual_credit_lines (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() unique references public.users (id) on delete cascade,
  limit_cents bigint not null default 50000 check (limit_cents > 0),
  balance_cents bigint not null default 0 check (balance_cents >= 0),
  status text not null default 'open' check (status in ('open', 'closed', 'charged_off')),
  account_number text not null unique
    default ('SS' || lpad(nextval('public.credit_account_number_seq')::text, 12, '0')),
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  level_up_applied_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table public.virtual_credit_lines is
  'Real, spendable closed-loop line. The reported limit is the spendable limit (FCRA accuracy).';
comment on column public.virtual_credit_lines.account_number is 'Metro 2 consumer account number.';

create table public.credit_statements (
  id uuid primary key default gen_random_uuid(),
  credit_line_id uuid not null references public.virtual_credit_lines (id) on delete cascade,
  user_id uuid not null references public.users (id) on delete cascade,
  period_start date not null,
  period_end date not null,
  statement_balance_cents bigint not null check (statement_balance_cents >= 0),
  minimum_due_cents bigint not null check (minimum_due_cents >= 0),
  amount_paid_cents bigint not null default 0 check (amount_paid_cents >= 0),
  due_date date not null,
  paid_at timestamptz,
  paid_on_time boolean,
  days_past_due integer not null default 0 check (days_past_due >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (credit_line_id, period_start),
  constraint credit_statements_period check (period_end >= period_start),
  constraint credit_statements_due_after_period check (due_date >= period_end),
  constraint credit_statements_minimum check (minimum_due_cents <= statement_balance_cents)
);
comment on column public.credit_statements.paid_on_time is
  'null = nothing due / undecided; true/false once the minimum is met. Drives streaks and the level-up.';
create index credit_statements_user_idx on public.credit_statements (user_id, period_end desc);
create index credit_statements_line_period_idx on public.credit_statements (credit_line_id, period_end desc);
create index credit_statements_unpaid_idx on public.credit_statements (due_date) where paid_at is null;

create table public.credit_transactions (
  id uuid primary key default gen_random_uuid(),
  credit_line_id uuid not null references public.virtual_credit_lines (id) on delete cascade,
  user_id uuid not null references public.users (id) on delete cascade,
  product_id uuid references public.credit_store_products (id) on delete restrict,
  kind text not null check (kind in ('purchase', 'membership_fee', 'addon_fee', 'refund')),
  amount_cents bigint not null check (amount_cents > 0),
  description text not null default '' check (length(description) <= 300),
  statement_id uuid references public.credit_statements (id) on delete restrict,
  posted_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index credit_transactions_line_posted_idx on public.credit_transactions (credit_line_id, posted_at desc);
create index credit_transactions_user_idx on public.credit_transactions (user_id);
create index credit_transactions_product_idx on public.credit_transactions (product_id);
create index credit_transactions_statement_idx on public.credit_transactions (statement_id);
create index credit_transactions_unstatemented_idx on public.credit_transactions (credit_line_id) where statement_id is null;

create table public.credit_payments (
  id uuid primary key default gen_random_uuid(),
  credit_line_id uuid not null references public.virtual_credit_lines (id) on delete cascade,
  user_id uuid not null references public.users (id) on delete cascade,
  statement_id uuid references public.credit_statements (id) on delete restrict,
  amount_cents bigint not null check (amount_cents > 0),
  method text not null check (method in ('card', 'ach', 'wallet')),
  status text not null default 'succeeded' check (status in ('pending', 'succeeded', 'failed', 'reversed')),
  provider_payment_id text unique,
  paid_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index credit_payments_line_idx on public.credit_payments (credit_line_id, paid_at desc);
create index credit_payments_user_idx on public.credit_payments (user_id);
create index credit_payments_statement_idx on public.credit_payments (statement_id);

create table public.membership_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() unique references public.users (id) on delete cascade,
  credit_line_id uuid references public.virtual_credit_lines (id) on delete set null,
  status text not null default 'active' check (status in ('active', 'past_due', 'canceled')),
  price_cents bigint not null default 500 check (price_cents >= 0),
  free_months_remaining integer not null default 0 check (free_months_remaining >= 0),
  current_period_start date,
  current_period_end date,
  canceled_at timestamptz,
  cancel_reason text check (cancel_reason is null or length(cancel_reason) <= 500),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index membership_subscriptions_line_idx on public.membership_subscriptions (credit_line_id);

create table public.addon_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references public.users (id) on delete cascade,
  addon_key text not null check (addon_key in ('rent_reporting', 'ai_coach')),
  status text not null default 'active' check (status in ('active', 'canceled')),
  price_cents bigint not null check (price_cents >= 0),
  started_at timestamptz not null default now(),
  canceled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index addon_subscriptions_one_active on public.addon_subscriptions (user_id, addon_key) where status = 'active';
create index addon_subscriptions_user_idx on public.addon_subscriptions (user_id);

create table public.treasury_allocations (
  id uuid primary key default gen_random_uuid(),
  source_type text not null check (source_type in ('credit_payment', 'background_check', 'drug_screen', 'payout')),
  source_id uuid not null,
  credit_payment_id uuid references public.credit_payments (id) on delete restrict,
  user_id uuid references public.users (id) on delete restrict,
  bucket text not null check (bucket in ('reporting_vendor', 'impact', 'platform', 'background_check', 'drug_screen')),
  amount_cents bigint not null check (amount_cents <> 0),
  partner_name text,
  note text not null default '',
  created_at timestamptz not null default now(),
  -- Impact copy names the real partner, so an impact row without one is invalid.
  constraint treasury_impact_requires_partner check (bucket <> 'impact' or partner_name is not null),
  constraint treasury_payment_link check (source_type <> 'credit_payment' or credit_payment_id = source_id)
);
comment on table public.treasury_allocations is
  'Append-only accounting of where each cent goes. Negative rows are compensating entries for reversals.';
create index treasury_allocations_payment_idx on public.treasury_allocations (credit_payment_id);
create index treasury_allocations_user_idx on public.treasury_allocations (user_id);
create index treasury_allocations_source_idx on public.treasury_allocations (source_type, source_id);
create index treasury_allocations_bucket_idx on public.treasury_allocations (bucket, created_at);

create table public.metro2_exports (
  id uuid primary key default gen_random_uuid(),
  period_end date not null,
  status text not null default 'prepared' check (status in ('prepared', 'delivered', 'acknowledged', 'rejected')),
  record_count integer not null default 0 check (record_count >= 0),
  file_path text,
  file_sha256 text check (file_sha256 is null or file_sha256 ~ '^[0-9a-f]{64}$'),
  furnisher_reference text,
  prepared_by uuid,
  prepared_at timestamptz not null default now(),
  delivered_at timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table public.metro2_exports is
  'Metro 2(R) files prepared for delivery to the credentialed data-furnisher partner. EzWerkz never sends to bureaus directly.';
create index metro2_exports_period_idx on public.metro2_exports (period_end desc);

create table public.credit_score_snapshots (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users (id) on delete cascade,
  score smallint not null check (score between 300 and 850),
  model text not null default 'VantageScore 3.0' check (length(model) <= 64),
  provider text not null check (length(provider) between 1 and 64),
  consent_id uuid references public.consents (id) on delete restrict,
  pulled_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
comment on table public.credit_score_snapshots is 'Soft-inquiry scores; each row requires a recorded soft_pull consent.';
create index credit_score_snapshots_user_idx on public.credit_score_snapshots (user_id, pulled_at desc);
create index credit_score_snapshots_consent_idx on public.credit_score_snapshots (consent_id);

create table public.credit_reporting_disputes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references public.users (id) on delete cascade,
  credit_line_id uuid references public.virtual_credit_lines (id) on delete set null,
  statement_id uuid references public.credit_statements (id) on delete set null,
  dispute_type text not null check (dispute_type in ('balance', 'payment_history', 'account_status', 'identity', 'other')),
  description text not null check (length(btrim(description)) between 1 and 4000),
  status text not null default 'received' check (status in (
    'received', 'investigating', 'resolved_corrected', 'resolved_verified', 'rejected_frivolous')),
  received_at timestamptz not null default now(),
  due_at timestamptz not null default (now() + interval '30 days'),
  resolved_at timestamptz,
  resolution_notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table public.credit_reporting_disputes is 'FCRA dispute intake; due_at = 30-day investigation deadline.';
create index credit_reporting_disputes_user_idx on public.credit_reporting_disputes (user_id);
create index credit_reporting_disputes_open_idx on public.credit_reporting_disputes (due_at)
  where status in ('received', 'investigating');
create index credit_reporting_disputes_line_idx on public.credit_reporting_disputes (credit_line_id);
create index credit_reporting_disputes_statement_idx on public.credit_reporting_disputes (statement_id);

create table public.affiliate_offers (
  id uuid primary key default gen_random_uuid(),
  issuer text not null check (length(btrim(issuer)) between 1 and 120),
  product_name text not null check (length(btrim(product_name)) between 1 and 160),
  min_score smallint not null check (min_score between 300 and 850),
  annual_fee_cents bigint not null default 0 check (annual_fee_cents >= 0),
  apr_text text not null default '',
  highlights text[] not null default '{}',
  bounty_cents bigint not null default 0 check (bounty_cents >= 0),
  url text not null check (url ~ '^https://'),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on column public.affiliate_offers.bounty_cents is
  'What EzWerkz earns; disclosed to members and NEVER used for ranking (rank by fit: score, annual fee).';

create table public.affiliate_unlocks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references public.users (id) on delete cascade,
  score_snapshot_id uuid references public.credit_score_snapshots (id) on delete set null,
  score smallint not null,
  unlocked_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index affiliate_unlocks_snapshot_idx on public.affiliate_unlocks (score_snapshot_id);

create table public.affiliate_clicks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references public.users (id) on delete cascade,
  offer_id uuid not null references public.affiliate_offers (id) on delete cascade,
  clicked_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index affiliate_clicks_user_idx on public.affiliate_clicks (user_id);
create index affiliate_clicks_offer_idx on public.affiliate_clicks (offer_id, clicked_at);

create table public.user_badges (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users (id) on delete cascade,
  badge_key text not null check (badge_key ~ '^[a-z0-9_]+$'),
  metadata jsonb not null default '{}'::jsonb,
  awarded_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (user_id, badge_key)
);

create table public.referrals (
  id uuid primary key default gen_random_uuid(),
  referrer_id uuid not null default auth.uid() references public.users (id) on delete cascade,
  referred_user_id uuid unique references public.users (id) on delete set null,
  referral_code text not null,
  referred_email text check (referred_email is null or referred_email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  status text not null default 'invited' check (status in ('invited', 'signed_up', 'rewarded', 'void')),
  reward_months smallint not null default 1 check (reward_months > 0),
  signed_up_at timestamptz,
  rewarded_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint referrals_not_self check (referred_user_id is null or referred_user_id <> referrer_id)
);
create index referrals_referrer_idx on public.referrals (referrer_id);
create index referrals_email_idx on public.referrals (lower(referred_email)) where referred_user_id is null;

create table public.bill_analyses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references public.users (id) on delete cascade,
  storage_path text not null check (length(storage_path) between 3 and 500),
  provider_name text check (provider_name is null or length(provider_name) <= 120),
  bill_category text check (bill_category is null or length(bill_category) <= 60),
  status text not null default 'uploaded' check (status in ('uploaded', 'analyzing', 'complete', 'failed')),
  billed_amount_cents bigint check (billed_amount_cents is null or billed_amount_cents >= 0),
  potential_savings_cents bigint check (potential_savings_cents is null or potential_savings_cents >= 0),
  findings jsonb not null default '[]'::jsonb check (jsonb_typeof(findings) = 'array'),
  negotiation_script text,
  model text,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table public.bill_analyses is
  'AI Bill Negotiator results. The app only suggests scripts; it never contacts providers or impersonates the member.';
create index bill_analyses_user_idx on public.bill_analyses (user_id, created_at desc);

-- -----------------------------------------------------------------------------
-- Small helpers
-- -----------------------------------------------------------------------------

create function private.award_badge(p_user_id uuid, p_badge_key text, p_metadata jsonb default '{}'::jsonb)
returns boolean
language plpgsql security definer set search_path = '' as $$
declare
  v_id uuid;
begin
  insert into public.user_badges (user_id, badge_key, metadata)
  values (p_user_id, p_badge_key, coalesce(p_metadata, '{}'::jsonb))
  on conflict (user_id, badge_key) do nothing
  returning id into v_id;
  return v_id is not null;
end $$;

-- The member-facing calendar date of a timestamp (lenient US zone, configurable).
create function private.due_local_date(p_ts timestamptz) returns date
language sql stable set search_path = '' as $$
  select (p_ts at time zone coalesce(public.config_text('credit_due_timezone'), 'America/Los_Angeles'))::date;
$$;

-- Consecutive most-recent on-time statements (statements with nothing due are skipped).
-- SECURITY INVOKER: members can only measure their own line.
create function public.credit_on_time_streak(p_credit_line_id uuid) returns integer
language sql stable set search_path = '' as $$
  select count(*)::integer
    from (
      select s.paid_on_time,
             count(*) filter (where not s.paid_on_time) over (order by s.period_end desc
               rows between unbounded preceding and current row) as misses
        from public.credit_statements s
       where s.credit_line_id = p_credit_line_id and s.paid_on_time is not null
    ) ranked
   where ranked.misses = 0;
$$;

-- -----------------------------------------------------------------------------
-- Guards
-- -----------------------------------------------------------------------------

create function private.credit_lines_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  v_internal boolean := coalesce(current_setting('ezwerkz.internal', true), '') = 'on';
begin
  if tg_op = 'INSERT' then
    if not v_internal then
      new.limit_cents := public.config_int('credit_default_limit_cents');
      new.balance_cents := 0;
      new.status := 'open';
      new.level_up_applied_at := null;
      new.closed_at := null;
      new.opened_at := now();
    end if;
    return new;
  end if;

  if not v_internal and (new.balance_cents is distinct from old.balance_cents
      or new.limit_cents is distinct from old.limit_cents
      or new.level_up_applied_at is distinct from old.level_up_applied_at) then
    raise exception 'FORBIDDEN_COLUMN'
      using detail = 'balance_cents/limit_cents change only through transactions, payments and the level-up.', errcode = '42501';
  end if;
  if new.user_id is distinct from old.user_id or new.account_number is distinct from old.account_number
     or new.opened_at is distinct from old.opened_at then
    raise exception 'FORBIDDEN_COLUMN' using detail = 'user_id, account_number and opened_at are immutable.', errcode = '42501';
  end if;
  if new.status <> 'open' and old.status = 'open' then
    new.closed_at := coalesce(new.closed_at, now());
  elsif new.status = 'open' and old.status <> 'open' then
    if current_user in ('anon', 'authenticated') then
      raise exception 'FORBIDDEN' using detail = 'A closed line can only be reopened by EzWerkz support.', errcode = '42501';
    end if;
    new.closed_at := null;
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update on public.virtual_credit_lines
  for each row execute function private.credit_lines_guard();
create trigger t90_touch before update on public.virtual_credit_lines
  for each row execute function private.set_updated_at();

create function private.credit_transactions_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  v_product public.credit_store_products%rowtype;
begin
  if tg_op = 'DELETE' then
    raise exception 'APPEND_ONLY' using detail = 'Post a refund instead of deleting a transaction.', errcode = '55000';
  end if;

  if tg_op = 'UPDATE' then
    if current_user in ('anon', 'authenticated')
       or new.id is distinct from old.id or new.credit_line_id is distinct from old.credit_line_id
       or new.user_id is distinct from old.user_id or new.product_id is distinct from old.product_id
       or new.kind is distinct from old.kind or new.amount_cents is distinct from old.amount_cents
       or new.description is distinct from old.description or new.posted_at is distinct from old.posted_at
       or new.created_at is distinct from old.created_at then
      raise exception 'APPEND_ONLY' using detail = 'Only statement_id is assigned after posting.', errcode = '55000';
    end if;
    return new;
  end if;

  if current_user in ('anon', 'authenticated') then
    if new.kind <> 'purchase' then
      raise exception 'FORBIDDEN' using detail = 'Members can only make store purchases.', errcode = '42501';
    end if;
    if new.product_id is null then
      raise exception 'PRODUCT_REQUIRED' using errcode = '22023';
    end if;
    select * into v_product from public.credit_store_products p where p.id = new.product_id and p.active;
    if not found then
      raise exception 'PRODUCT_NOT_AVAILABLE' using errcode = 'P0002';
    end if;
    if v_product.kind = 'membership' then
      raise exception 'USE_MEMBERSHIP_SUBSCRIPTION'
        using detail = 'The membership is billed monthly through membership_subscriptions.';
    end if;
    -- Server-side price, never the client's.
    new.amount_cents := v_product.price_cents;
    new.description := v_product.name;
    new.statement_id := null;
    new.posted_at := now();
    if new.amount_cents <= 0 then
      raise exception 'PRODUCT_IS_FREE' using detail = 'Free products are not charged to the line.';
    end if;
  end if;
  return new;
end $$;

create function private.credit_transactions_apply() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_line public.virtual_credit_lines%rowtype;
  v_new bigint;
  v_prev text;
begin
  select * into v_line from public.virtual_credit_lines where id = new.credit_line_id for update;
  if not found then
    raise exception 'CREDIT_LINE_NOT_FOUND' using errcode = 'P0002';
  end if;
  new.user_id := v_line.user_id;

  if new.kind = 'refund' then
    v_new := greatest(v_line.balance_cents - new.amount_cents, 0);
  else
    if v_line.status <> 'open' then
      raise exception 'CREDIT_LINE_NOT_OPEN' using detail = 'This credit line is not open for new charges.';
    end if;
    if new.kind = 'purchase' and v_line.balance_cents + new.amount_cents > v_line.limit_cents then
      raise exception 'CREDIT_LIMIT_EXCEEDED'
        using detail = format('Available credit is %s.', private.fmt_cents(v_line.limit_cents - v_line.balance_cents));
    end if;
    v_new := v_line.balance_cents + new.amount_cents;
  end if;

  v_prev := private.enter_internal();
  update public.virtual_credit_lines set balance_cents = v_new where id = v_line.id;
  perform private.exit_internal(v_prev);
  return new;
end $$;

create trigger t10_guard before insert or update or delete on public.credit_transactions
  for each row execute function private.credit_transactions_guard();
create trigger t20_apply before insert on public.credit_transactions
  for each row execute function private.credit_transactions_apply();

create function private.credit_payments_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  v_line_user uuid;
begin
  if tg_op = 'DELETE' then
    raise exception 'APPEND_ONLY' using detail = 'Payments are financial records; mark them failed or reversed.', errcode = '55000';
  end if;

  if tg_op = 'INSERT' then
    select l.user_id into v_line_user from public.virtual_credit_lines l where l.id = new.credit_line_id;
    if v_line_user is null then
      raise exception 'CREDIT_LINE_NOT_FOUND' using errcode = 'P0002';
    end if;
    new.user_id := v_line_user;
    if new.statement_id is not null and not exists (
      select 1 from public.credit_statements s where s.id = new.statement_id and s.credit_line_id = new.credit_line_id) then
      raise exception 'STATEMENT_MISMATCH' using errcode = '22023';
    end if;
    return new;
  end if;

  if new.credit_line_id is distinct from old.credit_line_id or new.user_id is distinct from old.user_id
     or new.statement_id is distinct from old.statement_id or new.amount_cents is distinct from old.amount_cents
     or new.method is distinct from old.method or new.paid_at is distinct from old.paid_at
     or new.provider_payment_id is distinct from old.provider_payment_id then
    raise exception 'FORBIDDEN_COLUMN' using detail = 'Only a payment''s status can change.', errcode = '42501';
  end if;
  if new.status is distinct from old.status and not (
       (old.status = 'pending' and new.status in ('succeeded', 'failed'))
    or (old.status = 'succeeded' and new.status = 'reversed')) then
    raise exception 'INVALID_STATUS_TRANSITION'
      using detail = format('%s -> %s is not allowed.', old.status, new.status), errcode = '22023';
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update or delete on public.credit_payments
  for each row execute function private.credit_payments_guard();
create trigger t90_touch before update on public.credit_payments
  for each row execute function private.set_updated_at();

create function private.membership_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  v_end_user boolean := current_user in ('anon', 'authenticated');
begin
  if tg_op = 'INSERT' then
    if new.credit_line_id is null then
      -- Subscribing is the member's own request to open the line the fee is
      -- charged to. Server-side inserts (e.g. a banked referral reward) never
      -- open a credit account on someone's behalf.
      if v_end_user then
        insert into public.virtual_credit_lines (user_id) values (new.user_id) on conflict (user_id) do nothing;
      end if;
      select l.id into new.credit_line_id from public.virtual_credit_lines l where l.user_id = new.user_id;
    end if;
    if v_end_user then
      new.status := 'active';
      new.price_cents := public.config_int('membership_fee_cents');
      new.free_months_remaining := 0;
      new.current_period_start := null;
      new.current_period_end := null;
      new.canceled_at := null;
    end if;
    return new;
  end if;

  if v_end_user and not public.is_admin() then
    if new.user_id is distinct from old.user_id or new.credit_line_id is distinct from old.credit_line_id
       or new.price_cents is distinct from old.price_cents
       or new.free_months_remaining is distinct from old.free_months_remaining
       or new.current_period_start is distinct from old.current_period_start
       or new.current_period_end is distinct from old.current_period_end then
      raise exception 'FORBIDDEN_COLUMN' using detail = 'Members can cancel or resubscribe only.', errcode = '42501';
    end if;
    if new.status is distinct from old.status and not (
         new.status = 'canceled' or (old.status = 'canceled' and new.status = 'active')) then
      raise exception 'INVALID_STATUS_TRANSITION' using errcode = '22023';
    end if;
    if new.status = 'active' and old.status = 'canceled' then
      new.price_cents := public.config_int('membership_fee_cents');
      if new.credit_line_id is null then
        insert into public.virtual_credit_lines (user_id) values (new.user_id) on conflict (user_id) do nothing;
        select l.id into new.credit_line_id from public.virtual_credit_lines l where l.user_id = new.user_id;
      end if;
    end if;
  end if;
  if new.status = 'canceled' and old.status <> 'canceled' then
    new.canceled_at := now();
  elsif new.status <> 'canceled' then
    new.canceled_at := null;
    new.cancel_reason := null;
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update on public.membership_subscriptions
  for each row execute function private.membership_guard();
create trigger t90_touch before update on public.membership_subscriptions
  for each row execute function private.set_updated_at();

create function private.addon_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  v_end_user boolean := current_user in ('anon', 'authenticated');
begin
  if tg_op = 'INSERT' then
    if v_end_user or new.price_cents is null then
      new.price_cents := case new.addon_key
        when 'rent_reporting' then public.config_int('addon_rent_reporting_cents')
        when 'ai_coach' then public.config_int('addon_ai_coach_cents')
      end;
    end if;
    if v_end_user then
      new.status := 'active';
      new.started_at := now();
      new.canceled_at := null;
    end if;
    return new;
  end if;

  if v_end_user and not public.is_admin() then
    if new.user_id is distinct from old.user_id or new.addon_key is distinct from old.addon_key
       or new.price_cents is distinct from old.price_cents or new.started_at is distinct from old.started_at then
      raise exception 'FORBIDDEN_COLUMN' using detail = 'Add-ons can only be canceled here.', errcode = '42501';
    end if;
    if new.status is distinct from old.status and new.status <> 'canceled' then
      raise exception 'INVALID_STATUS_TRANSITION' using detail = 'Start a new add-on instead of reactivating.', errcode = '22023';
    end if;
  end if;
  if new.status = 'canceled' and old.status <> 'canceled' then
    new.canceled_at := now();
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update on public.addon_subscriptions
  for each row execute function private.addon_guard();
create trigger t90_touch before update on public.addon_subscriptions
  for each row execute function private.set_updated_at();

create trigger t10_append_only before update or delete on public.treasury_allocations
  for each row execute function private.forbid_mutation();
create trigger t11_append_only_truncate before truncate on public.treasury_allocations
  for each statement execute function private.forbid_mutation();

create function private.metro2_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    new.status := 'prepared';
    new.prepared_by := coalesce(new.prepared_by, auth.uid());
    new.delivered_at := null;
    return new;
  end if;
  if new.status is distinct from old.status and not (
       (old.status = 'prepared' and new.status in ('delivered', 'rejected'))
    or (old.status = 'delivered' and new.status in ('acknowledged', 'rejected'))) then
    raise exception 'INVALID_STATUS_TRANSITION' using errcode = '22023';
  end if;
  if new.status = 'delivered' and old.status = 'prepared' then
    new.delivered_at := now();
  end if;
  if new.file_sha256 is distinct from old.file_sha256 and old.status <> 'prepared' then
    raise exception 'FORBIDDEN_COLUMN' using detail = 'A delivered file cannot be swapped.', errcode = '42501';
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update on public.metro2_exports
  for each row execute function private.metro2_guard();
create trigger t90_touch before update on public.metro2_exports
  for each row execute function private.set_updated_at();

create function private.score_snapshot_guard() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_consent uuid;
begin
  select c.id into v_consent from public.consents c
   where c.user_id = new.user_id and c.kind = 'soft_pull' and c.revoked_at is null
     and c.accepted_at <= coalesce(new.pulled_at, now())
   order by c.accepted_at desc limit 1;
  if v_consent is null then
    raise exception 'SOFT_PULL_CONSENT_REQUIRED'
      using detail = 'Scores may only be pulled after the member consents to a soft inquiry.', errcode = '42501';
  end if;
  new.consent_id := v_consent;
  return new;
end $$;

create function private.score_snapshot_unlock() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_unlock uuid;
begin
  if new.score >= public.config_int('affiliate_score_threshold') then
    insert into public.affiliate_unlocks (user_id, score_snapshot_id, score)
    values (new.user_id, new.id, new.score)
    on conflict (user_id) do nothing
    returning id into v_unlock;
    if v_unlock is not null then
      perform private.notify(
        new.user_id, 'credit.offers_unlocked', 'Card matches unlocked',
        'Your score reached ' || new.score || '. You can now compare card offers ranked by fit, not by what EzWerkz earns. EzWerkz may earn a commission. Results vary.',
        '/credit', jsonb_build_object('score', new.score));
    end if;
  end if;
  return null;
end $$;

create trigger t10_guard before insert on public.credit_score_snapshots
  for each row execute function private.score_snapshot_guard();
create trigger t50_unlock after insert on public.credit_score_snapshots
  for each row execute function private.score_snapshot_unlock();

create function private.disputes_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if current_user in ('anon', 'authenticated') then
      new.status := 'received';
      new.received_at := now();
      new.due_at := now() + interval '30 days';
      new.resolved_at := null;
      new.resolution_notes := null;
    end if;
    if new.credit_line_id is null then
      select l.id into new.credit_line_id from public.virtual_credit_lines l where l.user_id = new.user_id;
    end if;
    return new;
  end if;
  if new.user_id is distinct from old.user_id or new.received_at is distinct from old.received_at
     or new.due_at is distinct from old.due_at or new.description is distinct from old.description then
    raise exception 'FORBIDDEN_COLUMN' using errcode = '42501';
  end if;
  if new.status like 'resolved_%' or new.status = 'rejected_frivolous' then
    new.resolved_at := coalesce(new.resolved_at, now());
  else
    new.resolved_at := null;
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update on public.credit_reporting_disputes
  for each row execute function private.disputes_guard();
create trigger t90_touch before update on public.credit_reporting_disputes
  for each row execute function private.set_updated_at();

create function private.bill_analyses_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.storage_path := regexp_replace(btrim(new.storage_path), '^bill-uploads/', '');
  if current_user in ('anon', 'authenticated') and not public.is_admin() then
    if tg_op = 'UPDATE' and new.user_id is distinct from old.user_id then
      raise exception 'FORBIDDEN_COLUMN' using errcode = '42501';
    end if;
    if split_part(new.storage_path, '/', 1) <> new.user_id::text then
      raise exception 'INVALID_STORAGE_PATH'
        using detail = 'Bill uploads live under "<your user id>/" in the bill-uploads bucket.', errcode = '22023';
    end if;
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update on public.bill_analyses
  for each row execute function private.bill_analyses_guard();
create trigger t90_touch before update on public.bill_analyses
  for each row execute function private.set_updated_at();

create function private.referrals_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' and current_user in ('anon', 'authenticated') then
    new.referrer_id := auth.uid();
    new.referred_user_id := null;
    new.status := 'invited';
    new.signed_up_at := null;
    new.rewarded_at := null;
    new.reward_months := public.config_int('referral_reward_months');
    select u.referral_code into new.referral_code from public.users u where u.id = auth.uid();
  end if;
  return new;
end $$;

create trigger t10_guard before insert on public.referrals
  for each row execute function private.referrals_guard();
create trigger t90_touch before update on public.referrals
  for each row execute function private.set_updated_at();
create trigger t90_touch before update on public.credit_store_products
  for each row execute function private.set_updated_at();
create trigger t90_touch before update on public.credit_statements
  for each row execute function private.set_updated_at();
create trigger t90_touch before update on public.affiliate_offers
  for each row execute function private.set_updated_at();

-- -----------------------------------------------------------------------------
-- Level-up, referral reward, payment settlement
-- -----------------------------------------------------------------------------

create function private.apply_level_up(p_credit_line_id uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
declare
  v_line public.virtual_credit_lines%rowtype;
  v_needed integer := public.config_int('credit_level_up_after_on_time_months');
  v_target bigint := public.config_int('credit_level_up_limit_cents');
  v_ok boolean;
  v_prev text;
begin
  select * into v_line from public.virtual_credit_lines where id = p_credit_line_id for update;
  if not found then
    raise exception 'CREDIT_LINE_NOT_FOUND' using errcode = 'P0002';
  end if;
  if v_line.level_up_applied_at is not null or v_line.status <> 'open' then
    return false;
  end if;

  select count(*) = v_needed and coalesce(bool_and(recent.paid_on_time), false)
    into v_ok
    from (select s.paid_on_time from public.credit_statements s
           where s.credit_line_id = p_credit_line_id and s.paid_on_time is not null
           order by s.period_end desc
           limit v_needed) recent;
  if not v_ok then
    return false;
  end if;

  v_prev := private.enter_internal();
  update public.virtual_credit_lines
     set limit_cents = greatest(limit_cents, v_target), level_up_applied_at = now()
   where id = p_credit_line_id;
  perform private.exit_internal(v_prev);

  perform private.award_badge(v_line.user_id, 'limit_level_up', jsonb_build_object('limit_cents', greatest(v_line.limit_cents, v_target)));
  perform private.notify(
    v_line.user_id, 'credit.level_up', 'Level up: your limit is now ' || private.fmt_cents(greatest(v_line.limit_cents, v_target)),
    v_needed || ' on-time payments in a row raised your spendable EzWerkz limit. Results vary.',
    '/credit/rewards', jsonb_build_object('limit_cents', greatest(v_line.limit_cents, v_target)));
  insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
  values (auth.uid(), 'credit.level_up', 'virtual_credit_lines', p_credit_line_id,
          jsonb_build_object('old_limit_cents', v_line.limit_cents, 'new_limit_cents', greatest(v_line.limit_cents, v_target)));
  return true;
end $$;

create function private.reward_referral(p_referred_user_id uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare
  v_ref public.referrals%rowtype;
begin
  select * into v_ref from public.referrals
   where referred_user_id = p_referred_user_id and status = 'signed_up'
   for update;
  if not found then
    return;
  end if;

  update public.referrals set status = 'rewarded', rewarded_at = now() where id = v_ref.id;

  update public.membership_subscriptions
     set free_months_remaining = free_months_remaining + v_ref.reward_months
   where user_id = v_ref.referrer_id;
  if not found then
    -- Bank the reward; it applies once the referrer subscribes.
    insert into public.membership_subscriptions (user_id, status, price_cents, free_months_remaining)
    values (v_ref.referrer_id, 'canceled', public.config_int('membership_fee_cents'), v_ref.reward_months)
    on conflict (user_id) do update
      set free_months_remaining = public.membership_subscriptions.free_months_remaining + excluded.free_months_remaining;
  end if;

  perform private.award_badge(v_ref.referrer_id, 'referral_reward');
  perform private.notify(
    v_ref.referrer_id, 'credit.referral_reward', 'You earned a free month',
    'A friend you referred made their first on-time payment. Your next membership month is on us.',
    '/credit/rewards', jsonb_build_object('referral_id', v_ref.id, 'months', v_ref.reward_months));
end $$;

create function private.credit_payment_settled() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_sign integer;
  v_prev text;
  v_stmt public.credit_statements%rowtype;
  v_became_paid boolean := false;
  v_on_time boolean;
  v_vendor bigint;
  v_impact bigint;
  v_platform bigint;
  v_partner text;
  v_streak integer;
  v_streak_badge integer := public.config_int('streak_badge_months');
begin
  if new.status = 'succeeded' and (tg_op = 'INSERT' or old.status is distinct from 'succeeded') then
    v_sign := 1;
  elsif tg_op = 'UPDATE' and old.status = 'succeeded' and new.status = 'reversed' then
    v_sign := -1;
  else
    return null;
  end if;

  v_prev := private.enter_internal();
  update public.virtual_credit_lines
     set balance_cents = greatest(balance_cents - v_sign * new.amount_cents, 0)
   where id = new.credit_line_id;
  perform private.exit_internal(v_prev);

  if new.statement_id is not null then
    update public.credit_statements
       set amount_paid_cents = greatest(amount_paid_cents + v_sign * new.amount_cents, 0)
     where id = new.statement_id
    returning * into v_stmt;

    if v_sign = 1 and v_stmt.paid_at is null and v_stmt.minimum_due_cents > 0
       and v_stmt.amount_paid_cents >= v_stmt.minimum_due_cents then
      v_on_time := private.due_local_date(new.paid_at) <= v_stmt.due_date;
      update public.credit_statements
         set paid_at = new.paid_at,
             paid_on_time = v_on_time,
             days_past_due = greatest(private.due_local_date(new.paid_at) - due_date, 0)
       where id = v_stmt.id;
      v_became_paid := true;
    elsif v_sign = -1 and v_stmt.paid_at is not null and v_stmt.amount_paid_cents < v_stmt.minimum_due_cents then
      update public.credit_statements set paid_at = null, paid_on_time = null, days_past_due = 0 where id = v_stmt.id;
    end if;
  end if;

  if v_sign = 1 then
    v_vendor := least(public.config_int('membership_reporting_vendor_cents'), new.amount_cents);
    v_impact := least(public.config_int('membership_impact_cents'), new.amount_cents - v_vendor);
    v_partner := public.config_text('impact_partner_name');
    if v_impact > 0 and v_partner is null then
      v_impact := 0; -- never allocate (or advertise) impact without a named, real partner
    end if;
    v_platform := new.amount_cents - v_vendor - v_impact;

    insert into public.treasury_allocations (source_type, source_id, credit_payment_id, user_id, bucket, amount_cents, partner_name, note)
    select 'credit_payment', new.id, new.id, new.user_id, b.bucket, b.amount, b.partner, 'membership payment split'
      from (values ('reporting_vendor', v_vendor, null::text),
                   ('impact', v_impact, v_partner),
                   ('platform', v_platform, null::text)) as b (bucket, amount, partner)
     where b.amount > 0;
  else
    insert into public.treasury_allocations (source_type, source_id, credit_payment_id, user_id, bucket, amount_cents, partner_name, note)
    select 'credit_payment', new.id, new.id, new.user_id, t.bucket, -sum(t.amount_cents), t.partner_name, 'reversal'
      from public.treasury_allocations t
     where t.credit_payment_id = new.id
     group by t.bucket, t.partner_name
    having sum(t.amount_cents) <> 0;
  end if;

  if v_became_paid then
    if v_on_time then
      perform private.award_badge(new.user_id, 'first_on_time_payment');
      v_streak := public.credit_on_time_streak(new.credit_line_id);
      if v_streak >= 3 then
        perform private.award_badge(new.user_id, 'on_time_streak_3');
      end if;
      if v_streak >= v_streak_badge then
        perform private.award_badge(new.user_id, 'on_time_streak_' || v_streak_badge);
      end if;
      perform private.notify(new.user_id, 'credit.payment_on_time', 'Paid on time',
        private.fmt_cents(new.amount_cents) || ' received. That''s ' || v_streak || ' on-time in a row. Nice work!',
        '/credit/rewards', jsonb_build_object('payment_id', new.id, 'streak', v_streak));
      perform private.apply_level_up(new.credit_line_id);
      perform private.reward_referral(new.user_id);
    else
      perform private.notify(new.user_id, 'credit.payment_received', 'Payment received',
        private.fmt_cents(new.amount_cents) || ' received. Thanks for getting caught up.',
        '/credit', jsonb_build_object('payment_id', new.id));
    end if;
  end if;
  return null;
end $$;

create trigger t50_settled after insert or update of status on public.credit_payments
  for each row execute function private.credit_payment_settled();

-- -----------------------------------------------------------------------------
-- RPCs
-- -----------------------------------------------------------------------------

create function private.apply_membership_payment(
  p_statement_id uuid, p_amount_cents bigint, p_method text, p_provider_payment_id text
) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_stmt public.credit_statements%rowtype;
  v_line public.virtual_credit_lines%rowtype;
  v_wallet uuid;
  v_id uuid := gen_random_uuid();
  v_existing uuid;
begin
  if p_amount_cents is null or p_amount_cents <= 0 then
    raise exception 'INVALID_AMOUNT' using errcode = '22023';
  end if;
  if p_method is null or p_method not in ('card', 'ach', 'wallet') then
    raise exception 'INVALID_METHOD' using errcode = '22023';
  end if;
  if p_provider_payment_id is not null then
    select id into v_existing from public.credit_payments where provider_payment_id = p_provider_payment_id;
    if found then
      return v_existing; -- processor webhook retry
    end if;
  end if;

  select * into v_stmt from public.credit_statements where id = p_statement_id;
  if not found then
    raise exception 'STATEMENT_NOT_FOUND' using errcode = 'P0002';
  end if;
  select * into v_line from public.virtual_credit_lines where id = v_stmt.credit_line_id for update;
  if p_amount_cents > v_line.balance_cents then
    raise exception 'OVERPAYMENT'
      using detail = format('The current balance is %s.', private.fmt_cents(v_line.balance_cents)), errcode = '22023';
  end if;

  if p_method = 'wallet' then
    select w.id into v_wallet from public.wallets w where w.user_id = v_stmt.user_id;
    if v_wallet is null then
      raise exception 'WALLET_NOT_FOUND' using errcode = 'P0002';
    end if;
    perform private.post_ledger_entry(v_wallet, 'debit', p_amount_cents, 'membership_fee',
                                      'EzWerkz credit line payment', 'credit_payment', v_id);
  end if;

  insert into public.credit_payments (id, credit_line_id, user_id, statement_id, amount_cents, method, status, provider_payment_id, paid_at)
  values (v_id, v_line.id, v_stmt.user_id, v_stmt.id, p_amount_cents, p_method, 'succeeded', p_provider_payment_id, now());
  return v_id;
end $$;

-- Card/ACH payments are recorded by the server (service role) after the
-- processor confirms them. A member may record a 'wallet' payment for their own
-- statement — the wallet is debited in the same transaction.
create function public.record_membership_payment(
  p_statement_id uuid,
  p_amount_cents bigint,
  p_method text,
  p_provider_payment_id text default null
) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_owner uuid;
  v_id uuid;
begin
  select s.user_id into v_owner from public.credit_statements s where s.id = p_statement_id;
  if v_owner is null then
    raise exception 'STATEMENT_NOT_FOUND' using errcode = 'P0002';
  end if;
  if not (public.is_trusted_caller() or public.is_admin()) then
    if auth.uid() is distinct from v_owner then
      raise exception 'FORBIDDEN' using errcode = '42501';
    end if;
    if p_method is distinct from 'wallet' then
      raise exception 'PROCESSOR_CONFIRMATION_REQUIRED'
        using detail = 'Card and ACH payments are recorded by the server after the processor confirms them.',
              errcode = '42501';
    end if;
  end if;

  v_id := private.apply_membership_payment(p_statement_id, p_amount_cents, p_method, p_provider_payment_id);
  insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
  values (auth.uid(), 'credit.payment_recorded', 'credit_payments', v_id,
          jsonb_build_object('statement_id', p_statement_id, 'amount_cents', p_amount_cents, 'method', p_method));
  return v_id;
end $$;

create function public.sweep_membership_from_wallet(p_user_id uuid) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_auth public.autopay_authorizations%rowtype;
  v_stmt public.credit_statements%rowtype;
  v_balance bigint;
  v_amount bigint;
  v_wallet public.wallets%rowtype;
  v_payment uuid;
begin
  if not (public.is_trusted_caller() or public.is_admin() or auth.uid() = p_user_id) then
    raise exception 'FORBIDDEN' using errcode = '42501';
  end if;

  select * into v_auth from public.autopay_authorizations
   where user_id = p_user_id and purpose = 'membership_fee' and revoked_at is null
   order by authorized_at desc limit 1
   for update;
  if not found then
    return null;
  end if;

  select s.* into v_stmt
    from public.credit_statements s
    join public.virtual_credit_lines l on l.id = s.credit_line_id
   where s.user_id = p_user_id and s.paid_at is null
     and s.statement_balance_cents > s.amount_paid_cents and l.status = 'open'
   order by s.due_date asc
   limit 1
   for update of s;
  if not found then
    return null;
  end if;

  select l.balance_cents into v_balance from public.virtual_credit_lines l where l.id = v_stmt.credit_line_id;
  v_amount := least(v_stmt.statement_balance_cents - v_stmt.amount_paid_cents, v_balance, v_auth.max_amount_cents);
  if v_amount is null or v_amount <= 0 then
    return null;
  end if;

  select * into v_wallet from public.wallets where id = v_auth.wallet_id;
  if v_wallet.status <> 'active' or v_wallet.available_cents < v_amount then
    perform private.notify(p_user_id, 'autopay.skipped', 'Autopay didn''t run this time',
      'Your Wallet had less than ' || private.fmt_cents(v_amount) || ', so no payment was taken. You can pay by card or Wallet any time before '
        || to_char(v_stmt.due_date, 'FMMon FMDD') || '.',
      '/credit', jsonb_build_object('statement_id', v_stmt.id, 'amount_cents', v_amount));
    return null;
  end if;

  v_payment := private.apply_membership_payment(v_stmt.id, v_amount, 'wallet', null);
  update public.autopay_authorizations set last_swept_at = now() where id = v_auth.id;

  -- Reg E style receipt after each sweep.
  perform private.notify(p_user_id, 'autopay.receipt', 'Autopay receipt',
    private.fmt_cents(v_amount) || ' was paid from your EzWerkz Wallet toward your statement due '
      || to_char(v_stmt.due_date, 'FMMon FMDD, YYYY') || ', under the autopay authorization you gave on '
      || to_char(v_auth.authorized_at, 'FMMon FMDD, YYYY') || ' (terms ' || v_auth.authorization_text_version
      || '). You can turn autopay off any time in Wallet.',
    '/wallet',
    jsonb_build_object('payment_id', v_payment, 'authorization_id', v_auth.id, 'statement_id', v_stmt.id, 'amount_cents', v_amount));
  insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
  values (auth.uid(), 'autopay.sweep', 'credit_payments', v_payment,
          jsonb_build_object('user_id', p_user_id, 'authorization_id', v_auth.id, 'amount_cents', v_amount));
  return v_payment;
end $$;

create function public.apply_credit_level_up(p_credit_line_id uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
declare
  v_owner uuid;
begin
  select l.user_id into v_owner from public.virtual_credit_lines l where l.id = p_credit_line_id;
  if v_owner is null then
    raise exception 'CREDIT_LINE_NOT_FOUND' using errcode = 'P0002';
  end if;
  if not (public.is_trusted_caller() or public.is_admin() or auth.uid() = v_owner) then
    raise exception 'FORBIDDEN' using errcode = '42501';
  end if;
  return private.apply_level_up(p_credit_line_id);
end $$;

-- Monthly job (service role): bill everything owed at the moment of the cut.
-- statement_balance = the line's current balance and every not-yet-statemented
-- charge is attached. This product is pay-in-full, so minimum_due = balance.
create function public.cut_credit_statement(
  p_credit_line_id uuid, p_period_start date, p_period_end date, p_due_date date default null
) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_line public.virtual_credit_lines%rowtype;
  v_id uuid;
  v_due date := coalesce(p_due_date, p_period_end + 21);
begin
  if not (public.is_trusted_caller() or public.is_admin()) then
    raise exception 'FORBIDDEN' using errcode = '42501';
  end if;
  if p_period_start is null or p_period_end is null or p_period_end < p_period_start or v_due < p_period_end then
    raise exception 'INVALID_PERIOD' using errcode = '22023';
  end if;

  select * into v_line from public.virtual_credit_lines where id = p_credit_line_id for update;
  if not found then
    raise exception 'CREDIT_LINE_NOT_FOUND' using errcode = 'P0002';
  end if;
  select id into v_id from public.credit_statements where credit_line_id = p_credit_line_id and period_start = p_period_start;
  if found then
    return v_id;
  end if;

  insert into public.credit_statements (credit_line_id, user_id, period_start, period_end,
                                        statement_balance_cents, minimum_due_cents, due_date)
  values (v_line.id, v_line.user_id, p_period_start, p_period_end, v_line.balance_cents, v_line.balance_cents, v_due)
  returning id into v_id;

  update public.credit_transactions
     set statement_id = v_id
   where credit_line_id = v_line.id and statement_id is null;

  if v_line.balance_cents > 0 then
    perform private.notify(v_line.user_id, 'credit.statement_ready', 'Your statement is ready',
      'Statement balance ' || private.fmt_cents(v_line.balance_cents) || ', due ' || to_char(v_due, 'FMMon FMDD') || '.',
      '/credit', jsonb_build_object('statement_id', v_id));
  end if;
  return v_id;
end $$;

-- Monthly job (service role): charge the membership to the line, or use a
-- free (referral) month. Idempotent per calendar month.
create function public.post_membership_charge(p_user_id uuid) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_sub public.membership_subscriptions%rowtype;
  v_line public.virtual_credit_lines%rowtype;
  v_start date := date_trunc('month', now())::date;
  v_end date := (date_trunc('month', now()) + interval '1 month - 1 day')::date;
  v_id uuid;
begin
  if not (public.is_trusted_caller() or public.is_admin()) then
    raise exception 'FORBIDDEN' using errcode = '42501';
  end if;
  select * into v_sub from public.membership_subscriptions where user_id = p_user_id for update;
  if not found or v_sub.status = 'canceled' then
    return null;
  end if;
  select * into v_line from public.virtual_credit_lines where user_id = p_user_id;
  if not found or v_line.status <> 'open' then
    raise exception 'CREDIT_LINE_NOT_OPEN' using errcode = '22023';
  end if;

  if v_sub.current_period_start = v_start then
    select t.id into v_id from public.credit_transactions t
     where t.credit_line_id = v_line.id and t.kind = 'membership_fee' and t.posted_at >= v_start
     order by t.posted_at desc limit 1;
    return v_id;
  end if;

  if v_sub.free_months_remaining > 0 then
    update public.membership_subscriptions
       set free_months_remaining = free_months_remaining - 1, current_period_start = v_start, current_period_end = v_end
     where id = v_sub.id;
    perform private.notify(p_user_id, 'credit.free_month', 'Free month applied',
      'Your referral reward covered this month''s membership.', '/credit/rewards', '{}'::jsonb);
    return null;
  end if;

  update public.membership_subscriptions
     set current_period_start = v_start, current_period_end = v_end
   where id = v_sub.id;
  insert into public.credit_transactions (credit_line_id, user_id, kind, amount_cents, description)
  values (v_line.id, p_user_id, 'membership_fee', v_sub.price_cents, 'EzWerkz membership, ' || to_char(v_start, 'FMMonth YYYY'))
  returning id into v_id;
  return v_id;
end $$;

create function public.redeem_referral_code(p_code text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := auth.uid();
  v_email text;
  v_referrer uuid;
  v_code text := upper(btrim(coalesce(p_code, '')));
  v_id uuid;
begin
  if v_uid is null then
    raise exception 'AUTH_REQUIRED' using errcode = '42501';
  end if;
  select u.id into v_referrer from public.users u where u.referral_code = v_code;
  if v_referrer is null then
    raise exception 'REFERRAL_CODE_INVALID' using errcode = 'P0002';
  end if;
  if v_referrer = v_uid then
    raise exception 'SELF_REFERRAL' using errcode = '22023';
  end if;
  if exists (select 1 from public.referrals r where r.referred_user_id = v_uid) then
    raise exception 'ALREADY_REFERRED' using errcode = '22023';
  end if;
  if exists (select 1 from public.credit_payments p where p.user_id = v_uid and p.status = 'succeeded') then
    raise exception 'REFERRAL_TOO_LATE'
      using detail = 'Referral codes must be redeemed before your first payment.', errcode = '22023';
  end if;

  select u.email into v_email from public.users u where u.id = v_uid;
  update public.referrals
     set referred_user_id = v_uid, status = 'signed_up', signed_up_at = now()
   where id = (select r.id from public.referrals r
                where r.referrer_id = v_referrer and r.referred_user_id is null and r.status = 'invited'
                  and lower(r.referred_email) = lower(v_email)
                order by r.created_at limit 1)
  returning id into v_id;
  if v_id is null then
    insert into public.referrals (referrer_id, referred_user_id, referral_code, status, signed_up_at, reward_months)
    values (v_referrer, v_uid, v_code, 'signed_up', now(), public.config_int('referral_reward_months'))
    returning id into v_id;
  end if;

  perform private.notify(v_referrer, 'credit.referral_signed_up', 'A friend joined with your code',
    'You''ll get a free month after their first on-time payment.', '/credit/rewards', jsonb_build_object('referral_id', v_id));
  return v_id;
end $$;

-- Offers ranked by fit (best product the member qualifies for, then lowest
-- annual fee). Bounty is deliberately not part of the ordering.
create function public.ranked_affiliate_offers(p_score integer)
returns setof public.affiliate_offers
language sql stable set search_path = '' as $$
  select o.* from public.affiliate_offers o
   where o.active and o.min_score <= p_score
   order by o.min_score desc, o.annual_fee_cents asc, o.product_name asc;
$$;

-- Aggregate impact totals for honest UI copy (no per-member data).
create function public.treasury_impact_summary()
returns table (partner_name text, total_cents bigint, allocation_count bigint)
language sql stable security definer set search_path = '' as $$
  select t.partner_name, sum(t.amount_cents)::bigint, count(*)::bigint
    from public.treasury_allocations t
   where t.bucket = 'impact'
   group by t.partner_name
  having sum(t.amount_cents) <> 0;
$$;

revoke execute on function
  public.record_membership_payment(uuid, bigint, text, text),
  public.sweep_membership_from_wallet(uuid),
  public.apply_credit_level_up(uuid),
  public.cut_credit_statement(uuid, date, date, date),
  public.post_membership_charge(uuid),
  public.redeem_referral_code(text),
  public.credit_on_time_streak(uuid),
  public.ranked_affiliate_offers(integer),
  public.treasury_impact_summary()
from public, anon;
grant execute on function
  public.record_membership_payment(uuid, bigint, text, text),
  public.sweep_membership_from_wallet(uuid),
  public.apply_credit_level_up(uuid),
  public.cut_credit_statement(uuid, date, date, date),
  public.post_membership_charge(uuid),
  public.redeem_referral_code(text),
  public.credit_on_time_streak(uuid),
  public.ranked_affiliate_offers(integer),
  public.treasury_impact_summary()
to authenticated, service_role;

-- -----------------------------------------------------------------------------
-- RLS
-- -----------------------------------------------------------------------------

alter table public.credit_store_products enable row level security;
alter table public.virtual_credit_lines enable row level security;
alter table public.credit_statements enable row level security;
alter table public.credit_transactions enable row level security;
alter table public.credit_payments enable row level security;
alter table public.membership_subscriptions enable row level security;
alter table public.addon_subscriptions enable row level security;
alter table public.treasury_allocations enable row level security;
alter table public.metro2_exports enable row level security;
alter table public.credit_score_snapshots enable row level security;
alter table public.credit_reporting_disputes enable row level security;
alter table public.affiliate_offers enable row level security;
alter table public.affiliate_unlocks enable row level security;
alter table public.affiliate_clicks enable row level security;
alter table public.user_badges enable row level security;
alter table public.referrals enable row level security;
alter table public.bill_analyses enable row level security;

-- Store catalog: everyone signed in sees active products; admins manage.
create policy credit_store_products_select on public.credit_store_products for select to authenticated
  using (active or (select public.is_admin()));
create policy credit_store_products_write_admin on public.credit_store_products for all to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

create policy virtual_credit_lines_select_self on public.virtual_credit_lines for select to authenticated
  using (user_id = (select auth.uid()));
create policy virtual_credit_lines_insert_self on public.virtual_credit_lines for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy virtual_credit_lines_select_admin on public.virtual_credit_lines for select to authenticated
  using ((select public.is_admin()));
create policy virtual_credit_lines_update_admin on public.virtual_credit_lines for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

create policy credit_statements_select_self on public.credit_statements for select to authenticated
  using (user_id = (select auth.uid()));
create policy credit_statements_select_admin on public.credit_statements for select to authenticated
  using ((select public.is_admin()));

create policy credit_transactions_select_self on public.credit_transactions for select to authenticated
  using (user_id = (select auth.uid()));
create policy credit_transactions_insert_purchase on public.credit_transactions for insert to authenticated
  with check (kind = 'purchase' and user_id = (select auth.uid())
              and exists (select 1 from public.virtual_credit_lines l
                           where l.id = credit_line_id and l.user_id = (select auth.uid())));
create policy credit_transactions_select_admin on public.credit_transactions for select to authenticated
  using ((select public.is_admin()));

create policy credit_payments_select_self on public.credit_payments for select to authenticated
  using (user_id = (select auth.uid()));
create policy credit_payments_select_admin on public.credit_payments for select to authenticated
  using ((select public.is_admin()));

create policy membership_select_self on public.membership_subscriptions for select to authenticated
  using (user_id = (select auth.uid()));
create policy membership_insert_self on public.membership_subscriptions for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy membership_update_self on public.membership_subscriptions for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy membership_select_admin on public.membership_subscriptions for select to authenticated
  using ((select public.is_admin()));

create policy addon_select_self on public.addon_subscriptions for select to authenticated
  using (user_id = (select auth.uid()));
create policy addon_insert_self on public.addon_subscriptions for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy addon_update_self on public.addon_subscriptions for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy addon_select_admin on public.addon_subscriptions for select to authenticated
  using ((select public.is_admin()));

create policy treasury_select_self on public.treasury_allocations for select to authenticated
  using (user_id = (select auth.uid()));
create policy treasury_select_admin on public.treasury_allocations for select to authenticated
  using ((select public.is_admin()));

create policy metro2_select_admin on public.metro2_exports for select to authenticated
  using ((select public.is_admin()));
create policy metro2_insert_admin on public.metro2_exports for insert to authenticated
  with check ((select public.is_admin()));
create policy metro2_update_admin on public.metro2_exports for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

create policy score_snapshots_select_self on public.credit_score_snapshots for select to authenticated
  using (user_id = (select auth.uid()));
create policy score_snapshots_select_admin on public.credit_score_snapshots for select to authenticated
  using ((select public.is_admin()));
create policy score_snapshots_insert_admin on public.credit_score_snapshots for insert to authenticated
  with check ((select public.is_admin()));

create policy disputes_select_self on public.credit_reporting_disputes for select to authenticated
  using (user_id = (select auth.uid()));
create policy disputes_insert_self on public.credit_reporting_disputes for insert to authenticated
  with check (user_id = (select auth.uid())
              and (credit_line_id is null or exists (select 1 from public.virtual_credit_lines l
                                                      where l.id = credit_line_id and l.user_id = (select auth.uid()))));
create policy disputes_select_admin on public.credit_reporting_disputes for select to authenticated
  using ((select public.is_admin()));
create policy disputes_update_admin on public.credit_reporting_disputes for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

create policy affiliate_offers_select on public.affiliate_offers for select to authenticated
  using (active or (select public.is_admin()));
create policy affiliate_offers_write_admin on public.affiliate_offers for all to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

create policy affiliate_unlocks_select_self on public.affiliate_unlocks for select to authenticated
  using (user_id = (select auth.uid()));
create policy affiliate_unlocks_select_admin on public.affiliate_unlocks for select to authenticated
  using ((select public.is_admin()));

create policy affiliate_clicks_select_self on public.affiliate_clicks for select to authenticated
  using (user_id = (select auth.uid()));
create policy affiliate_clicks_insert_self on public.affiliate_clicks for insert to authenticated
  with check (user_id = (select auth.uid())
              and exists (select 1 from public.affiliate_offers o where o.id = offer_id and o.active));
create policy affiliate_clicks_select_admin on public.affiliate_clicks for select to authenticated
  using ((select public.is_admin()));

create policy user_badges_select_self on public.user_badges for select to authenticated
  using (user_id = (select auth.uid()));
create policy user_badges_select_admin on public.user_badges for select to authenticated
  using ((select public.is_admin()));

create policy referrals_select_party on public.referrals for select to authenticated
  using (referrer_id = (select auth.uid()) or referred_user_id = (select auth.uid()));
create policy referrals_insert_self on public.referrals for insert to authenticated
  with check (referrer_id = (select auth.uid()));
create policy referrals_select_admin on public.referrals for select to authenticated
  using ((select public.is_admin()));
create policy referrals_update_admin on public.referrals for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

create policy bill_analyses_select_self on public.bill_analyses for select to authenticated
  using (user_id = (select auth.uid()));
create policy bill_analyses_insert_self on public.bill_analyses for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy bill_analyses_update_self on public.bill_analyses for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy bill_analyses_delete_self on public.bill_analyses for delete to authenticated
  using (user_id = (select auth.uid()));
create policy bill_analyses_select_admin on public.bill_analyses for select to authenticated
  using ((select public.is_admin()));
