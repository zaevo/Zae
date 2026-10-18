-- =============================================================================
-- 0001_core.sql — EzWerkz core schema
--   extensions, private helper schema, organizations, users, user_modules,
--   platform_config (mirror of src/lib/pricing.ts), notifications, audit_log,
--   consents, the auth.users -> public.users trigger and the RLS helpers
--   is_admin(), current_role_is(text), user_org_id().
--
-- Conventions used by every migration:
--   * uuid PKs (gen_random_uuid()), created_at timestamptz default now(),
--     money as bigint cents, RLS enabled on every table with explicit policies.
--   * Errors raised for callers use a machine-readable code as the message
--     (e.g. 'TIER_REQUIRED') and a human sentence in DETAIL.
--   * Guard triggers that must know WHO is writing are SECURITY INVOKER and read
--     current_user: 'authenticated'/'anon' means a direct Data API statement;
--     anything else is the service role, a migration, or one of our SECURITY
--     DEFINER functions (which run as the owner).
--   * Columns that only our own functions may change (balances, compliance
--     statuses, limits) are protected by the transaction-local flag
--     `ezwerkz.internal`, set via private.enter_internal()/exit_internal().
-- =============================================================================

create extension if not exists pgcrypto with schema extensions;
create extension if not exists postgis with schema extensions;

create schema if not exists private;
revoke all on schema private from public;
comment on schema private is
  'Internal helpers and trigger functions. Not exposed through the Supabase Data API.';

-- -----------------------------------------------------------------------------
-- Private helpers
-- -----------------------------------------------------------------------------

create function private.set_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- Append-only tables (ledger, drug screens, audit, treasury, signatures).
create function private.forbid_mutation() returns trigger
language plpgsql set search_path = '' as $$
begin
  raise exception 'APPEND_ONLY'
    using detail = format('%I.%I is append-only; %s is not allowed. Record a new row instead.',
                          tg_table_schema, tg_table_name, lower(tg_op)),
          errcode = '55000';
end $$;

-- Lets our SECURITY DEFINER code change protected columns. Nest-safe: callers
-- restore the previous value with exit_internal().
create function private.enter_internal() returns text
language plpgsql set search_path = '' as $$
declare
  v_prev text := coalesce(current_setting('ezwerkz.internal', true), 'off');
begin
  perform set_config('ezwerkz.internal', 'on', true);
  return v_prev;
end $$;

create function private.exit_internal(p_prev text) returns void
language sql set search_path = '' as $$
  select set_config('ezwerkz.internal', coalesce(nullif(p_prev, ''), 'off'), true);
$$;

-- -----------------------------------------------------------------------------
-- Organizations
-- -----------------------------------------------------------------------------

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(btrim(name)) between 1 and 200),
  kind text not null default 'client_company' check (kind in ('client_company')),
  billing_email text check (billing_email is null or billing_email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  phone_e164 text check (phone_e164 is null or phone_e164 ~ '^\+[1-9][0-9]{6,14}$'),
  address_line1 text,
  city text,
  region text,
  postal_code text,
  stripe_customer_id text unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table public.organizations is 'Client companies (B2B shift marketplace customers).';

-- -----------------------------------------------------------------------------
-- Users (1:1 with auth.users)
-- -----------------------------------------------------------------------------

create table public.users (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null default '',
  full_name text not null default '' check (length(full_name) <= 200),
  phone_e164 text check (phone_e164 is null or phone_e164 ~ '^\+[1-9][0-9]{6,14}$'),
  role text not null default 'member' check (role in ('member', 'worker', 'client_manager', 'admin')),
  organization_id uuid references public.organizations (id) on delete set null,
  home_geo extensions.geography(Point, 4326),
  home_lat double precision check (home_lat between -90 and 90),
  home_lng double precision check (home_lng between -180 and 180),
  sms_opt_in boolean not null default false,
  sms_opt_in_at timestamptz,
  sms_opt_out_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- TCPA: an opt-in is only valid with the moment consent was given.
  constraint users_sms_opt_in_timestamped check (not sms_opt_in or sms_opt_in_at is not null)
);
comment on table public.users is
  'App profile for each auth user. role/organization_id/email are managed by EzWerkz (admins or trusted code), never by the user.';
comment on column public.users.home_geo is 'Worker home location used for the 15-mile dispatch radius. Kept in sync with home_lat/home_lng.';

create unique index users_phone_e164_key on public.users (phone_e164) where phone_e164 is not null;
create index users_organization_id_idx on public.users (organization_id);
create index users_role_idx on public.users (role);
create index users_home_geo_gix on public.users using gist (home_geo);

create table public.user_modules (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references public.users (id) on delete cascade,
  module text not null check (module in ('credit', 'wallet', 'shifts')),
  created_at timestamptz not null default now(),
  unique (user_id, module)
);
comment on table public.user_modules is 'Which EzWerkz "doors" (modules) a user has entered.';

-- -----------------------------------------------------------------------------
-- RLS helper functions (SECURITY DEFINER so they can read users without
-- recursing into users' own policies).
-- -----------------------------------------------------------------------------

create function public.current_role_is(p_role text) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.users u where u.id = auth.uid() and u.role = p_role);
$$;

create function public.is_admin() returns boolean
language sql stable security definer set search_path = '' as $$
  select public.current_role_is('admin');
$$;

create function public.user_org_id() returns uuid
language sql stable security definer set search_path = '' as $$
  select u.organization_id from public.users u where u.id = auth.uid();
$$;

-- True for the service role (webhooks, cron) and for direct database sessions
-- (migrations, SQL editor). False for every Data API request made with a user
-- or anon JWT.
create function public.is_trusted_caller() returns boolean
language sql stable set search_path = '' as $$
  select coalesce(auth.jwt() ->> 'role', '') = 'service_role'
      or (auth.jwt() is null and session_user not in ('authenticator', 'anon', 'authenticated'));
$$;

comment on function public.is_admin() is 'RLS helper: caller has role admin.';
comment on function public.current_role_is(text) is 'RLS helper: caller has the given role.';
comment on function public.user_org_id() is 'RLS helper: caller''s organization_id (null if none).';

-- -----------------------------------------------------------------------------
-- Platform config — mirror of src/lib/pricing.ts. If you change a number in
-- pricing.ts, change it here (new migration) too.
-- -----------------------------------------------------------------------------

create table public.platform_config (
  id uuid primary key default gen_random_uuid(),
  key text not null unique check (key ~ '^[a-z0-9_]+$'),
  value jsonb not null,
  description text not null default '',
  updated_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table public.platform_config is 'Key/value mirror of src/lib/pricing.ts used by SQL functions (rates, splits, thresholds).';

insert into public.platform_config (key, value, description) values
  ('tier1_bill_rate_cents',              '2200',   'TIER_RATES[1].billRateCents — client pays per hour'),
  ('tier1_pay_rate_cents',               '1500',   'TIER_RATES[1].payRateCents — worker earns per hour'),
  ('tier2_bill_rate_cents',              '3500',   'TIER_RATES[2].billRateCents'),
  ('tier2_pay_rate_cents',               '1800',   'TIER_RATES[2].payRateCents'),
  ('tier2_qualifying_shifts',            '2',      'TIER2_UPGRADE.qualifyingShifts — completed on-time Tier 1 shifts'),
  ('tier2_min_rating',                   '4.5',    'TIER2_UPGRADE.minRating — client rating average'),
  ('background_check_cost_cents',        '2500',   'TIER2_UPGRADE.backgroundCheckCostCents — platform-paid, never deducted from worker pay'),
  ('drug_screen_kit_cost_cents',         '500',    'TIER2_UPGRADE.drugScreenKitCostCents — platform-paid'),
  ('dispatch_radius_miles',              '15',     'DISPATCH.radiusMiles'),
  ('claim_code_length',                  '4',      'DISPATCH.claimCodeLength'),
  ('sms_ttl_minutes',                    '30',     'DISPATCH.smsTtlMinutes — claim codes expire after this'),
  ('credit_default_limit_cents',         '50000',  'CREDIT.defaultLimitCents'),
  ('credit_level_up_limit_cents',        '100000', 'CREDIT.levelUpLimitCents'),
  ('credit_level_up_after_on_time_months','3',     'CREDIT.levelUpAfterOnTimeMonths'),
  ('membership_fee_cents',               '500',    'CREDIT.membershipFeeCents'),
  ('affiliate_score_threshold',          '660',    'CREDIT.affiliateScoreThreshold'),
  ('streak_badge_months',                '6',      'CREDIT.streakBadgeMonths'),
  ('membership_reporting_vendor_cents',  '150',    'MEMBERSHIP_SPLIT.reportingVendorCents'),
  ('membership_impact_cents',            '0',      'MEMBERSHIP_SPLIT.impactCents — OFF unless a real partner is named below'),
  ('impact_partner_name',                'null',   'Real donation partner name; required before impact allocations are written'),
  ('addon_rent_reporting_cents',         '400',    'ADDONS.rentReporting.priceCents'),
  ('addon_ai_coach_cents',               '1000',   'ADDONS.aiCoach.priceCents'),
  ('referral_reward_months',             '1',      'REFERRAL.rewardMonths'),
  ('conversion_fee_cents',               '450000', 'CONVERSION_FEE_CENTS — MSA Section 8'),
  ('non_circumvention_months',           '12',     'NON_CIRCUMVENTION_MONTHS — MSA Section 8'),
  ('credit_due_timezone',                '"America/Los_Angeles"', 'Statement due dates end at 23:59 in this zone (lenient for US members)');

-- Config readers. SECURITY INVOKER: platform_config is readable by every
-- signed-in user, so these work inside both guard triggers and definer code.
create function public.config_numeric(p_key text) returns numeric
language plpgsql stable set search_path = '' as $$
declare
  v jsonb;
begin
  select c.value into v from public.platform_config c where c.key = p_key;
  if not found or v is null or jsonb_typeof(v) <> 'number' then
    raise exception 'CONFIG_MISSING' using detail = format('platform_config.%s must be a number', p_key);
  end if;
  return (v #>> '{}')::numeric;
end $$;

create function public.config_int(p_key text) returns bigint
language sql stable set search_path = '' as $$
  select round(public.config_numeric(p_key))::bigint;
$$;

create function public.config_text(p_key text) returns text
language sql stable set search_path = '' as $$
  select nullif(c.value #>> '{}', '') from public.platform_config c
   where c.key = p_key and jsonb_typeof(c.value) = 'string';
$$;

-- -----------------------------------------------------------------------------
-- Notifications
-- -----------------------------------------------------------------------------

create table public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users (id) on delete cascade,
  kind text not null check (kind ~ '^[a-z0-9_.]+$'),
  title text not null check (length(title) between 1 and 200),
  body text not null default '' check (length(body) <= 2000),
  link_href text,
  data jsonb not null default '{}'::jsonb,
  read_at timestamptz,
  created_at timestamptz not null default now()
);
create index notifications_user_created_idx on public.notifications (user_id, created_at desc);
create index notifications_user_unread_idx on public.notifications (user_id) where read_at is null;

create function private.notify(
  p_user_id uuid, p_kind text, p_title text, p_body text,
  p_link text default null, p_data jsonb default '{}'::jsonb
) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_id uuid;
begin
  insert into public.notifications (user_id, kind, title, body, link_href, data)
  values (p_user_id, p_kind, p_title, coalesce(p_body, ''), p_link, coalesce(p_data, '{}'::jsonb))
  returning id into v_id;
  return v_id;
end $$;

create function private.fmt_cents(p_cents bigint) returns text
language sql immutable set search_path = '' as $$
  select to_char(p_cents / 100.0, 'FM$999,999,990.00');
$$;

-- -----------------------------------------------------------------------------
-- Audit log (append-only). actor_id has no FK on purpose: audit rows must
-- outlive the users they mention.
-- -----------------------------------------------------------------------------

create table public.audit_log (
  id uuid primary key default gen_random_uuid(),
  actor_id uuid,
  action text not null check (length(action) between 1 and 100),
  entity_type text not null check (length(entity_type) between 1 and 100),
  entity_id uuid,
  details jsonb not null default '{}'::jsonb,
  ip_address text check (ip_address is null or length(ip_address) <= 64),
  created_at timestamptz not null default now()
);
create index audit_log_entity_idx on public.audit_log (entity_type, entity_id);
create index audit_log_actor_idx on public.audit_log (actor_id, created_at desc);
create index audit_log_created_idx on public.audit_log (created_at desc);

create trigger t10_append_only before update or delete on public.audit_log
  for each row execute function private.forbid_mutation();
create trigger t11_append_only_truncate before truncate on public.audit_log
  for each statement execute function private.forbid_mutation();

create function private.audit(
  p_action text, p_entity_type text, p_entity_id uuid, p_details jsonb default '{}'::jsonb
) returns void
language sql security definer set search_path = '' as $$
  insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
  values (auth.uid(), p_action, p_entity_type, p_entity_id, coalesce(p_details, '{}'::jsonb));
$$;

-- -----------------------------------------------------------------------------
-- Consents (FCRA disclosure, drug screen, SMS, autopay, soft pull, e-sign).
-- Evidence of consent is retained: rows cannot be deleted and only revoked_at
-- may change (once, from null).
-- -----------------------------------------------------------------------------

create table public.consents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references public.users (id) on delete restrict,
  kind text not null check (kind in ('fcra_disclosure', 'drug_screen', 'sms', 'autopay', 'soft_pull', 'esign')),
  text_version text not null check (length(btrim(text_version)) between 1 and 64),
  accepted_at timestamptz not null default now(),
  ip_address text check (ip_address is null or length(ip_address) <= 64),
  user_agent text check (user_agent is null or length(user_agent) <= 512),
  metadata jsonb not null default '{}'::jsonb,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  constraint consents_revoked_after_accepted check (revoked_at is null or revoked_at >= accepted_at)
);
create index consents_user_kind_active_idx on public.consents (user_id, kind) where revoked_at is null;

create function private.consents_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'APPEND_ONLY' using detail = 'Consent records are retained as evidence; revoke instead of deleting.', errcode = '55000';
  end if;

  if tg_op = 'INSERT' then
    if current_user in ('anon', 'authenticated') then
      -- Server clock, not the client's, is the evidence timestamp.
      new.accepted_at := now();
      new.revoked_at := null;
    end if;
    return new;
  end if;

  -- UPDATE: only revoked_at, only null -> timestamp.
  if new.id is distinct from old.id or new.user_id is distinct from old.user_id
     or new.kind is distinct from old.kind or new.text_version is distinct from old.text_version
     or new.accepted_at is distinct from old.accepted_at or new.ip_address is distinct from old.ip_address
     or new.user_agent is distinct from old.user_agent or new.metadata is distinct from old.metadata
     or new.created_at is distinct from old.created_at then
    raise exception 'CONSENT_IMMUTABLE' using detail = 'Only revoked_at can change on a consent record.', errcode = '55000';
  end if;
  if old.revoked_at is not null and new.revoked_at is distinct from old.revoked_at then
    raise exception 'CONSENT_ALREADY_REVOKED' using detail = 'Record a new consent instead of un-revoking.', errcode = '55000';
  end if;
  if old.revoked_at is null and new.revoked_at is not null and current_user in ('anon', 'authenticated') then
    new.revoked_at := now();
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update or delete on public.consents
  for each row execute function private.consents_guard();

-- -----------------------------------------------------------------------------
-- users: guard + derived columns
-- -----------------------------------------------------------------------------

create function private.users_guard() returns trigger
language plpgsql set search_path = public, extensions as $$
declare
  v_end_user boolean := current_user in ('anon', 'authenticated');
begin
  if tg_op = 'UPDATE' then
    if v_end_user and not public.is_admin() then
      if new.id is distinct from old.id or new.role is distinct from old.role
         or new.organization_id is distinct from old.organization_id or new.email is distinct from old.email then
        raise exception 'FORBIDDEN_COLUMN'
          using detail = 'role, organization_id and email are managed by EzWerkz.', errcode = '42501';
      end if;
    end if;

    -- TCPA consent is per number: changing the phone drops an existing opt-in
    -- unless this same update is the opt-in.
    if new.phone_e164 is distinct from old.phone_e164 and old.sms_opt_in and new.sms_opt_in then
      new.sms_opt_in := false;
      new.sms_opt_in_at := null;
      new.sms_opt_out_at := now();
    elsif new.sms_opt_in and not old.sms_opt_in then
      if v_end_user or new.sms_opt_in_at is null or new.sms_opt_in_at is not distinct from old.sms_opt_in_at then
        new.sms_opt_in_at := now();
      end if;
      new.sms_opt_out_at := null;
    elsif not new.sms_opt_in and old.sms_opt_in then
      if v_end_user or new.sms_opt_out_at is null or new.sms_opt_out_at is not distinct from old.sms_opt_out_at then
        new.sms_opt_out_at := now();
      end if;
    elsif v_end_user then
      new.sms_opt_in_at := old.sms_opt_in_at;
      new.sms_opt_out_at := old.sms_opt_out_at;
    end if;
  else
    if new.sms_opt_in and new.sms_opt_in_at is null then
      new.sms_opt_in_at := now();
    end if;
  end if;

  -- Keep home_geo and home_lat/home_lng in sync; whichever was written wins.
  if new.home_geo is not null
     and (tg_op = 'INSERT' or new.home_geo is distinct from old.home_geo) then
    new.home_lat := st_y(new.home_geo::geometry);
    new.home_lng := st_x(new.home_geo::geometry);
  elsif new.home_lat is not null and new.home_lng is not null
     and (tg_op = 'INSERT' or new.home_lat is distinct from old.home_lat or new.home_lng is distinct from old.home_lng
          or new.home_geo is null) then
    new.home_geo := st_setsrid(st_makepoint(new.home_lng, new.home_lat), 4326)::geography;
  elsif new.home_lat is null or new.home_lng is null then
    new.home_geo := null;
    new.home_lat := null;
    new.home_lng := null;
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update on public.users
  for each row execute function private.users_guard();
create trigger t90_touch before update on public.users
  for each row execute function private.set_updated_at();

-- SMS opt-out (STOP keyword, profile toggle, phone change) revokes active SMS consents.
create function private.users_after_update() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if old.sms_opt_in and not new.sms_opt_in then
    update public.consents
       set revoked_at = coalesce(new.sms_opt_out_at, now())
     where user_id = new.id and kind = 'sms' and revoked_at is null;
  end if;
  return null;
end $$;

create trigger t50_after_update after update of sms_opt_in on public.users
  for each row execute function private.users_after_update();

-- SMS consent row <-> users.sms_opt_in
create function private.consents_after_change() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.kind = 'sms' then
    if tg_op = 'INSERT' and new.revoked_at is null then
      update public.users
         set sms_opt_in = true, sms_opt_in_at = new.accepted_at
       where id = new.user_id and not sms_opt_in;
    elsif tg_op = 'UPDATE' and old.revoked_at is null and new.revoked_at is not null
          and not exists (select 1 from public.consents c
                           where c.user_id = new.user_id and c.kind = 'sms' and c.revoked_at is null) then
      update public.users
         set sms_opt_in = false, sms_opt_out_at = new.revoked_at
       where id = new.user_id and sms_opt_in;
    end if;
  end if;
  return null;
end $$;

create trigger t50_after_change after insert or update of revoked_at on public.consents
  for each row execute function private.consents_after_change();

-- -----------------------------------------------------------------------------
-- auth.users -> public.users. Role is ALWAYS 'member' here: raw_user_meta_data
-- is user-controlled and must never grant a role.
-- -----------------------------------------------------------------------------

create function private.handle_new_auth_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.users (id, email, full_name, role)
  values (
    new.id,
    coalesce(new.email, ''),
    left(coalesce(nullif(btrim(new.raw_user_meta_data ->> 'full_name'), ''),
                  nullif(split_part(coalesce(new.email, ''), '@', 1), ''), ''), 200),
    'member'
  )
  on conflict (id) do nothing;

  insert into public.user_modules (user_id, module)
  values (new.id, 'credit'), (new.id, 'wallet')
  on conflict (user_id, module) do nothing;
  return new;
end $$;

create trigger on_auth_user_created after insert on auth.users
  for each row execute function private.handle_new_auth_user();

create function private.handle_auth_user_email_change() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  update public.users set email = coalesce(new.email, '') where id = new.id;
  return new;
end $$;

create trigger on_auth_user_email_changed after update of email on auth.users
  for each row when (old.email is distinct from new.email)
  execute function private.handle_auth_user_email_change();

-- -----------------------------------------------------------------------------
-- Generic guards for small tables
-- -----------------------------------------------------------------------------

-- notifications: the recipient may only mark read/unread.
create function private.notifications_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if current_user in ('anon', 'authenticated') and not public.is_admin() then
    if new.user_id is distinct from old.user_id or new.kind is distinct from old.kind
       or new.title is distinct from old.title or new.body is distinct from old.body
       or new.link_href is distinct from old.link_href or new.data is distinct from old.data
       or new.created_at is distinct from old.created_at then
      raise exception 'FORBIDDEN_COLUMN' using detail = 'Only read_at can be changed.', errcode = '42501';
    end if;
  end if;
  return new;
end $$;

create trigger t10_guard before update on public.notifications
  for each row execute function private.notifications_guard();

create function private.audit_log_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if current_user in ('anon', 'authenticated') then
    new.actor_id := auth.uid();
    new.created_at := now();
  end if;
  return new;
end $$;

create trigger t05_guard before insert on public.audit_log
  for each row execute function private.audit_log_guard();

create function private.platform_config_audit() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  new.updated_by := auth.uid();
  insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
  values (auth.uid(), 'platform_config.update', 'platform_config', new.id,
          jsonb_build_object('key', new.key, 'old', old.value, 'new', new.value));
  return new;
end $$;

create trigger t10_audit before update on public.platform_config
  for each row when (old.value is distinct from new.value)
  execute function private.platform_config_audit();
create trigger t90_touch before update on public.platform_config
  for each row execute function private.set_updated_at();
create trigger t90_touch before update on public.organizations
  for each row execute function private.set_updated_at();

-- -----------------------------------------------------------------------------
-- Row Level Security
-- -----------------------------------------------------------------------------

alter table public.organizations enable row level security;
alter table public.users enable row level security;
alter table public.user_modules enable row level security;
alter table public.platform_config enable row level security;
alter table public.notifications enable row level security;
alter table public.audit_log enable row level security;
alter table public.consents enable row level security;

-- organizations (worker visibility of shift orgs is added in 0004)
create policy organizations_select_member on public.organizations for select to authenticated
  using (id = (select public.user_org_id()));
create policy organizations_select_admin on public.organizations for select to authenticated
  using ((select public.is_admin()));
create policy organizations_update_manager on public.organizations for update to authenticated
  using (id = (select public.user_org_id()) and (select public.current_role_is('client_manager')))
  with check (id = (select public.user_org_id()) and (select public.current_role_is('client_manager')));
create policy organizations_insert_admin on public.organizations for insert to authenticated
  with check ((select public.is_admin()));
create policy organizations_update_admin on public.organizations for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));
create policy organizations_delete_admin on public.organizations for delete to authenticated
  using ((select public.is_admin()));

-- users
create policy users_select_self on public.users for select to authenticated
  using (id = (select auth.uid()));
create policy users_select_org_colleagues on public.users for select to authenticated
  using (organization_id is not null
         and organization_id = (select public.user_org_id())
         and (select public.current_role_is('client_manager')));
create policy users_select_admin on public.users for select to authenticated
  using ((select public.is_admin()));
create policy users_update_self on public.users for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));
create policy users_update_admin on public.users for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

-- user_modules
create policy user_modules_select_self on public.user_modules for select to authenticated
  using (user_id = (select auth.uid()));
create policy user_modules_select_admin on public.user_modules for select to authenticated
  using ((select public.is_admin()));
create policy user_modules_insert_self on public.user_modules for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy user_modules_delete_self on public.user_modules for delete to authenticated
  using (user_id = (select auth.uid()));
create policy user_modules_write_admin on public.user_modules for all to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

-- platform_config: readable by signed-in users (prices are public), admin-managed
create policy platform_config_select_all on public.platform_config for select to authenticated
  using (true);
create policy platform_config_insert_admin on public.platform_config for insert to authenticated
  with check ((select public.is_admin()));
create policy platform_config_update_admin on public.platform_config for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

-- notifications
create policy notifications_select_self on public.notifications for select to authenticated
  using (user_id = (select auth.uid()));
create policy notifications_update_self on public.notifications for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy notifications_delete_self on public.notifications for delete to authenticated
  using (user_id = (select auth.uid()));
create policy notifications_select_admin on public.notifications for select to authenticated
  using ((select public.is_admin()));
create policy notifications_insert_admin on public.notifications for insert to authenticated
  with check ((select public.is_admin()));

-- audit_log: admins read; any signed-in user may append rows attributed to themselves
create policy audit_log_select_admin on public.audit_log for select to authenticated
  using ((select public.is_admin()));
create policy audit_log_insert_self on public.audit_log for insert to authenticated
  with check (actor_id = (select auth.uid()));

-- consents
create policy consents_select_self on public.consents for select to authenticated
  using (user_id = (select auth.uid()));
create policy consents_select_admin on public.consents for select to authenticated
  using ((select public.is_admin()));
create policy consents_insert_self on public.consents for insert to authenticated
  with check (user_id = (select auth.uid()) and revoked_at is null);
create policy consents_update_self on public.consents for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- Identity helpers: signed-in users and the service role only.
revoke execute on function public.current_role_is(text), public.is_admin(), public.user_org_id() from public, anon;
grant execute on function public.current_role_is(text), public.is_admin(), public.user_org_id() to authenticated, service_role;
