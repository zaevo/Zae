-- =============================================================================
-- 0002_wallet.sql — Module B: wallet, append-only ledger, virtual cards,
-- income streams, autopay authorizations (Reg E style), wallet_post_entry().
--
-- Invariants enforced here (not just in app code):
--   * wallets.available_cents changes ONLY through a ledger_entries insert.
--   * A debit can never overdraw (INSUFFICIENT_FUNDS) or leave a frozen wallet.
--   * ledger_entries is append-only.
--   * virtual_cards has no PAN/CVV columns — card details are shown only by the
--     issuer's PCI-compliant UI component.
-- =============================================================================

create table public.wallets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references public.users (id) on delete cascade,
  available_cents bigint not null default 0 check (available_cents >= 0),
  pending_cents bigint not null default 0 check (pending_cents >= 0),
  status text not null default 'active' check (status in ('active', 'frozen', 'closed')),
  currency text not null default 'usd' check (currency = 'usd'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on column public.wallets.available_cents is
  'Cached balance maintained by the ledger trigger. Never update directly; post a ledger entry.';

create table public.ledger_entries (
  id uuid primary key default gen_random_uuid(),
  wallet_id uuid not null references public.wallets (id) on delete restrict,
  direction text not null check (direction in ('credit', 'debit')),
  amount_cents bigint not null check (amount_cents > 0),
  category text not null check (category in (
    'shift_earnings', 'membership_fee', 'addon_fee', 'card_spend', 'deposit', 'withdrawal', 'refund')),
  description text not null check (length(btrim(description)) between 1 and 500),
  reference_type text check (reference_type is null or reference_type ~ '^[a-z0-9_]+$'),
  reference_id uuid,
  balance_after_cents bigint,
  created_by uuid,
  created_at timestamptz not null default now()
);
comment on table public.ledger_entries is 'Append-only wallet ledger. amount_cents is always positive; direction gives the sign.';

create index ledger_entries_wallet_created_idx on public.ledger_entries (wallet_id, created_at desc);
-- One entry per (reference, direction, category): makes webhook retries and
-- payout postings idempotent.
create unique index ledger_entries_reference_key
  on public.ledger_entries (wallet_id, reference_type, reference_id, direction, category)
  where reference_type is not null and reference_id is not null;

create table public.virtual_cards (
  id uuid primary key default gen_random_uuid(),
  wallet_id uuid not null references public.wallets (id) on delete cascade,
  user_id uuid not null references public.users (id) on delete cascade,
  provider text not null default 'stripe_issuing' check (provider in ('stripe_issuing', 'lithic', 'demo')),
  provider_card_id text not null check (length(provider_card_id) between 1 and 128),
  last4 text not null check (last4 ~ '^[0-9]{4}$'),
  brand text not null check (brand in ('visa', 'mastercard')),
  kind text not null check (kind in ('permanent', 'single_use', 'temporary')),
  status text not null default 'active' check (status in ('active', 'frozen', 'canceled')),
  nickname text not null default '' check (length(nickname) <= 40),
  spend_limit_cents bigint check (spend_limit_cents is null or spend_limit_cents > 0),
  expires_at timestamptz,
  canceled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider, provider_card_id)
);
comment on table public.virtual_cards is
  'Card metadata only. PAN and CVV are never stored; show last4 here and full details only via the issuer''s PCI-compliant component.';
create index virtual_cards_wallet_idx on public.virtual_cards (wallet_id);
create index virtual_cards_user_idx on public.virtual_cards (user_id);

create table public.income_streams (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references public.users (id) on delete cascade,
  wallet_id uuid not null references public.wallets (id) on delete cascade,
  label text not null check (length(btrim(label)) between 1 and 80),
  source_type text not null check (source_type in (
    'ezwerkz_payouts', 'employer_direct_deposit', 'gig_platform', 'benefits', 'other')),
  expected_amount_cents bigint check (expected_amount_cents is null or expected_amount_cents >= 0),
  frequency text not null default 'irregular' check (frequency in ('weekly', 'biweekly', 'semimonthly', 'monthly', 'irregular')),
  allocation_percent smallint not null default 100 check (allocation_percent between 1 and 100),
  is_active boolean not null default true,
  last_deposit_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index income_streams_user_idx on public.income_streams (user_id);
create index income_streams_wallet_idx on public.income_streams (wallet_id);

-- Reg E style: who (user_id), when (authorized_at), how much (max_amount_cents),
-- which text (authorization_text_version); revocable any time (revoked_at).
create table public.autopay_authorizations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references public.users (id) on delete restrict,
  wallet_id uuid not null references public.wallets (id) on delete restrict,
  purpose text not null default 'membership_fee' check (purpose in ('membership_fee', 'addon_fee')),
  max_amount_cents bigint not null check (max_amount_cents > 0),
  frequency text not null default 'monthly' check (frequency in ('monthly')),
  authorization_text_version text not null check (length(btrim(authorization_text_version)) between 1 and 64),
  consent_id uuid references public.consents (id) on delete restrict,
  authorized_at timestamptz not null default now(),
  ip_address text check (ip_address is null or length(ip_address) <= 64),
  user_agent text check (user_agent is null or length(user_agent) <= 512),
  revoked_at timestamptz,
  last_swept_at timestamptz,
  created_at timestamptz not null default now(),
  constraint autopay_revoked_after_authorized check (revoked_at is null or revoked_at >= authorized_at)
);
create unique index autopay_authorizations_one_active
  on public.autopay_authorizations (user_id, purpose) where revoked_at is null;
create index autopay_authorizations_wallet_idx on public.autopay_authorizations (wallet_id);
create index autopay_authorizations_consent_idx on public.autopay_authorizations (consent_id);

-- -----------------------------------------------------------------------------
-- Every user gets a wallet.
-- -----------------------------------------------------------------------------

create function private.create_wallet_for_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.wallets (user_id) values (new.id) on conflict (user_id) do nothing;
  return null;
end $$;

create trigger t60_create_wallet after insert on public.users
  for each row execute function private.create_wallet_for_user();

-- -----------------------------------------------------------------------------
-- Ledger: apply each entry to the cached balance, atomically, with row lock.
-- -----------------------------------------------------------------------------

create function private.ledger_apply_entry() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_wallet public.wallets%rowtype;
  v_new bigint;
  v_prev text;
begin
  select * into v_wallet from public.wallets where id = new.wallet_id for update;
  if not found then
    raise exception 'WALLET_NOT_FOUND' using errcode = 'P0002';
  end if;
  if v_wallet.status = 'closed' then
    raise exception 'WALLET_CLOSED' using detail = 'This wallet is closed.';
  end if;

  if new.direction = 'debit' then
    if v_wallet.status <> 'active' then
      raise exception 'WALLET_FROZEN' using detail = 'Money cannot leave a frozen wallet.';
    end if;
    if v_wallet.available_cents < new.amount_cents then
      raise exception 'INSUFFICIENT_FUNDS'
        using detail = format('Available %s, requested %s.', v_wallet.available_cents, new.amount_cents);
    end if;
    v_new := v_wallet.available_cents - new.amount_cents;
  else
    v_new := v_wallet.available_cents + new.amount_cents;
  end if;

  v_prev := private.enter_internal();
  update public.wallets set available_cents = v_new where id = new.wallet_id;
  perform private.exit_internal(v_prev);

  new.balance_after_cents := v_new;
  new.created_by := coalesce(new.created_by, auth.uid());
  new.created_at := now();
  return new;
end $$;

create trigger t20_apply before insert on public.ledger_entries
  for each row execute function private.ledger_apply_entry();
create trigger t10_append_only before update or delete on public.ledger_entries
  for each row execute function private.forbid_mutation();
create trigger t11_append_only_truncate before truncate on public.ledger_entries
  for each statement execute function private.forbid_mutation();

-- Internal poster used by definer code (payout credits, membership payments).
create function private.post_ledger_entry(
  p_wallet_id uuid, p_direction text, p_amount_cents bigint, p_category text,
  p_description text, p_reference_type text, p_reference_id uuid
) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_id uuid;
begin
  perform 1 from public.wallets where id = p_wallet_id for update;
  if p_reference_type is not null and p_reference_id is not null then
    select id into v_id from public.ledger_entries
     where wallet_id = p_wallet_id and reference_type = p_reference_type and reference_id = p_reference_id
       and direction = p_direction and category = p_category;
    if found then
      return v_id;
    end if;
  end if;
  insert into public.ledger_entries (wallet_id, direction, amount_cents, category, description, reference_type, reference_id)
  values (p_wallet_id, p_direction, p_amount_cents, p_category, p_description, p_reference_type, p_reference_id)
  returning id into v_id;
  return v_id;
end $$;

-- -----------------------------------------------------------------------------
-- wallet_post_entry RPC
--   * service role / admin: any direction and category.
--   * the wallet owner: debits only (withdrawal, card_spend, membership_fee,
--     addon_fee). Credits (deposits, shift pay, refunds) come from trusted code.
--   * idempotent when (p_reference_type, p_reference_id) is given.
-- -----------------------------------------------------------------------------

create function public.wallet_post_entry(
  p_wallet_id uuid,
  p_direction text,
  p_amount_cents bigint,
  p_category text,
  p_description text,
  p_reference_type text default null,
  p_reference_id uuid default null
) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_owner uuid;
begin
  if p_direction is null or p_direction not in ('credit', 'debit') then
    raise exception 'INVALID_DIRECTION' using errcode = '22023';
  end if;
  if p_amount_cents is null or p_amount_cents <= 0 then
    raise exception 'INVALID_AMOUNT' using errcode = '22023';
  end if;
  if p_description is null or length(btrim(p_description)) = 0 then
    raise exception 'DESCRIPTION_REQUIRED' using errcode = '22023';
  end if;

  select user_id into v_owner from public.wallets where id = p_wallet_id;
  if not found then
    raise exception 'WALLET_NOT_FOUND' using errcode = 'P0002';
  end if;

  if not (public.is_trusted_caller() or public.is_admin()) then
    if auth.uid() is null or v_owner <> auth.uid() then
      raise exception 'FORBIDDEN' using errcode = '42501';
    end if;
    if p_direction <> 'debit' or p_category not in ('withdrawal', 'card_spend', 'membership_fee', 'addon_fee') then
      raise exception 'FORBIDDEN'
        using detail = 'Members can only move money out of their own wallet. Deposits are posted by the payment processor.',
              errcode = '42501';
    end if;
  end if;

  return private.post_ledger_entry(p_wallet_id, p_direction, p_amount_cents, p_category,
                                   btrim(p_description), p_reference_type, p_reference_id);
end $$;

revoke execute on function public.wallet_post_entry(uuid, text, bigint, text, text, text, uuid) from public, anon;
grant execute on function public.wallet_post_entry(uuid, text, bigint, text, text, text, uuid) to authenticated, service_role;

-- -----------------------------------------------------------------------------
-- Guards
-- -----------------------------------------------------------------------------

create function private.wallets_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  v_internal boolean := coalesce(current_setting('ezwerkz.internal', true), '') = 'on';
begin
  if new.available_cents is distinct from old.available_cents and not v_internal then
    raise exception 'FORBIDDEN_COLUMN'
      using detail = 'available_cents changes only through ledger_entries.', errcode = '42501';
  end if;
  if new.user_id is distinct from old.user_id or new.currency is distinct from old.currency then
    raise exception 'FORBIDDEN_COLUMN' using detail = 'user_id and currency are immutable.', errcode = '42501';
  end if;
  if new.pending_cents is distinct from old.pending_cents and current_user in ('anon', 'authenticated') and not v_internal then
    raise exception 'FORBIDDEN_COLUMN' using detail = 'pending_cents is maintained by the card issuer webhook.', errcode = '42501';
  end if;
  return new;
end $$;

create trigger t10_guard before update on public.wallets
  for each row execute function private.wallets_guard();
create trigger t90_touch before update on public.wallets
  for each row execute function private.set_updated_at();

create function private.virtual_cards_guard() returns trigger
language plpgsql set search_path = public as $$
declare
  v_end_user boolean := current_user in ('anon', 'authenticated');
begin
  if tg_op = 'INSERT' then
    select w.user_id into new.user_id from public.wallets w where w.id = new.wallet_id;
    if new.user_id is null then
      raise exception 'WALLET_NOT_FOUND' using errcode = 'P0002';
    end if;
    if v_end_user then
      new.status := 'active';
      new.canceled_at := null;
    end if;
    return new;
  end if;

  if old.status = 'canceled' and new.status <> 'canceled' then
    raise exception 'CARD_CANCELED' using detail = 'A canceled card cannot be reactivated; create a new card.';
  end if;
  if new.status = 'canceled' and old.status <> 'canceled' then
    new.canceled_at := now();
  end if;
  if v_end_user and not public.is_admin() then
    if new.wallet_id is distinct from old.wallet_id or new.user_id is distinct from old.user_id
       or new.provider is distinct from old.provider or new.provider_card_id is distinct from old.provider_card_id
       or new.last4 is distinct from old.last4 or new.brand is distinct from old.brand
       or new.kind is distinct from old.kind or new.expires_at is distinct from old.expires_at then
      raise exception 'FORBIDDEN_COLUMN'
        using detail = 'Only status, nickname and spend_limit_cents can be changed.', errcode = '42501';
    end if;
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update on public.virtual_cards
  for each row execute function private.virtual_cards_guard();
create trigger t90_touch before update on public.virtual_cards
  for each row execute function private.set_updated_at();

create function private.income_streams_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.wallet_id is null or (tg_op = 'UPDATE' and new.user_id is distinct from old.user_id) then
    select w.id into new.wallet_id from public.wallets w where w.user_id = new.user_id;
  end if;
  if not exists (select 1 from public.wallets w where w.id = new.wallet_id and w.user_id = new.user_id) then
    raise exception 'WALLET_MISMATCH' using detail = 'An income stream must target the owner''s wallet.';
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update on public.income_streams
  for each row execute function private.income_streams_guard();
create trigger t90_touch before update on public.income_streams
  for each row execute function private.set_updated_at();

create function private.autopay_guard() returns trigger
language plpgsql set search_path = public as $$
declare
  v_end_user boolean := current_user in ('anon', 'authenticated');
begin
  if tg_op = 'DELETE' then
    raise exception 'APPEND_ONLY' using detail = 'Autopay authorizations are retained; revoke instead.', errcode = '55000';
  end if;

  if tg_op = 'INSERT' then
    if new.wallet_id is null then
      select w.id into new.wallet_id from public.wallets w where w.user_id = new.user_id;
    end if;
    if not exists (select 1 from public.wallets w where w.id = new.wallet_id and w.user_id = new.user_id) then
      raise exception 'WALLET_MISMATCH' using detail = 'Autopay must draw from the owner''s wallet.';
    end if;
    if new.max_amount_cents is null then
      new.max_amount_cents := case new.purpose
        when 'membership_fee' then public.config_int('membership_fee_cents')
        else greatest(public.config_int('addon_rent_reporting_cents'), public.config_int('addon_ai_coach_cents'))
      end;
    end if;
    if v_end_user then
      new.authorized_at := now();
      new.revoked_at := null;
      new.last_swept_at := null;
    end if;
    return new;
  end if;

  if new.user_id is distinct from old.user_id or new.wallet_id is distinct from old.wallet_id
     or new.purpose is distinct from old.purpose or new.max_amount_cents is distinct from old.max_amount_cents
     or new.frequency is distinct from old.frequency
     or new.authorization_text_version is distinct from old.authorization_text_version
     or new.consent_id is distinct from old.consent_id or new.authorized_at is distinct from old.authorized_at
     or new.ip_address is distinct from old.ip_address or new.user_agent is distinct from old.user_agent then
    raise exception 'AUTHORIZATION_IMMUTABLE'
      using detail = 'Revoke this authorization and create a new one to change its terms.', errcode = '55000';
  end if;
  if old.revoked_at is not null and new.revoked_at is distinct from old.revoked_at then
    raise exception 'AUTHORIZATION_ALREADY_REVOKED' using errcode = '55000';
  end if;
  if old.revoked_at is null and new.revoked_at is not null and v_end_user then
    new.revoked_at := now();
  end if;
  if new.last_swept_at is distinct from old.last_swept_at and v_end_user then
    raise exception 'FORBIDDEN_COLUMN' using errcode = '42501';
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update or delete on public.autopay_authorizations
  for each row execute function private.autopay_guard();

-- -----------------------------------------------------------------------------
-- RLS
-- -----------------------------------------------------------------------------

alter table public.wallets enable row level security;
alter table public.ledger_entries enable row level security;
alter table public.virtual_cards enable row level security;
alter table public.income_streams enable row level security;
alter table public.autopay_authorizations enable row level security;

create policy wallets_select_self on public.wallets for select to authenticated
  using (user_id = (select auth.uid()));
create policy wallets_select_admin on public.wallets for select to authenticated
  using ((select public.is_admin()));
create policy wallets_update_admin on public.wallets for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

-- No insert/update/delete policies: entries are written by wallet_post_entry()
-- and trusted server code only.
create policy ledger_entries_select_self on public.ledger_entries for select to authenticated
  using (exists (select 1 from public.wallets w where w.id = wallet_id and w.user_id = (select auth.uid())));
create policy ledger_entries_select_admin on public.ledger_entries for select to authenticated
  using ((select public.is_admin()));

create policy virtual_cards_select_self on public.virtual_cards for select to authenticated
  using (user_id = (select auth.uid()));
create policy virtual_cards_insert_self on public.virtual_cards for insert to authenticated
  with check (user_id = (select auth.uid())
              and exists (select 1 from public.wallets w where w.id = wallet_id and w.user_id = (select auth.uid())));
create policy virtual_cards_update_self on public.virtual_cards for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy virtual_cards_select_admin on public.virtual_cards for select to authenticated
  using ((select public.is_admin()));
create policy virtual_cards_update_admin on public.virtual_cards for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

create policy income_streams_select_self on public.income_streams for select to authenticated
  using (user_id = (select auth.uid()));
create policy income_streams_insert_self on public.income_streams for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy income_streams_update_self on public.income_streams for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy income_streams_delete_self on public.income_streams for delete to authenticated
  using (user_id = (select auth.uid()));
create policy income_streams_select_admin on public.income_streams for select to authenticated
  using ((select public.is_admin()));

create policy autopay_select_self on public.autopay_authorizations for select to authenticated
  using (user_id = (select auth.uid()));
create policy autopay_insert_self on public.autopay_authorizations for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy autopay_update_self on public.autopay_authorizations for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy autopay_select_admin on public.autopay_authorizations for select to authenticated
  using ((select public.is_admin()));
