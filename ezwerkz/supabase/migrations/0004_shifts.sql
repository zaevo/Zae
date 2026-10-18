-- =============================================================================
-- 0004_shifts.sql — Module C: B2B emergency shift marketplace.
--   client_locations, shifts, shift_dispatches, worker_compliance,
--   background_checks (FCRA adverse-action states), drug_screen_logs
--   (append-only), shift_ratings, payouts, msa_versions, contract_signatures
--   (immutable), chat_threads, chat_messages, poach_flags.
--   RPCs: workers_within_radius, create_dispatches, claim_shift,
--   claim_shift_by_code, approve_shift, evaluate_tier2_eligibility,
--   record_drug_screen (+ has_signed_msa, enroll_module, register_business,
--   order_background_check, record_background_check_result,
--   review_background_check).
--
-- Compliance enforced here:
--   * SMS dispatch only to opted-in workers with a timestamped consent.
--   * Background checks need a standalone FCRA consent, are platform-paid
--     (paid_by = 'platform', never deducted from pay), and a 'consider' result
--     can only become an adverse action through a human admin, with a
--     pre-adverse notice and a 5-business-day wait. No automatic rejection.
--   * Drug screens: consent before collection, collector != worker, evidence
--     must exist in the private bucket, results are new append-only rows (no
--     override), a rapid non-negative is 'pending' (lab confirmation).
--   * Compliance statuses on worker_compliance cannot be written directly by
--     anyone, including the service role.
--   * Shift rates come from platform_config, not from the client.
--   * Section 8 signature rows are immutable; the MSA must be signed (with the
--     separate Section 8 acknowledgment) before a client posts a shift.
--   * Chat contact-info backstop redacts phone numbers/emails that bypass the
--     app's poach filter and flags them for admin review (never fines).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Tables
-- -----------------------------------------------------------------------------

create table public.msa_versions (
  id uuid primary key default gen_random_uuid(),
  version text not null unique check (version ~ '^[0-9A-Za-z._-]{1,32}$'),
  title text not null,
  summary text not null default '',
  effective_at date not null,
  document_sha256 text check (document_sha256 is null or document_sha256 ~ '^[0-9a-f]{64}$'),
  is_current boolean not null default false,
  created_at timestamptz not null default now()
);
create unique index msa_versions_one_current on public.msa_versions (is_current) where is_current;

-- Reference data the signature FK depends on (also in seed.sql, idempotent).
insert into public.msa_versions (version, title, summary, effective_at, is_current)
values ('2026-10-16', 'EzWerkz Master Services Agreement (template)',
        'Template — have a licensed attorney review before use. Section 8 (Non-Circumvention / Conversion Fee) binds the client only.',
        date '2026-10-16', true)
on conflict (version) do nothing;

create table public.client_locations (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations (id) on delete cascade,
  name text not null check (length(btrim(name)) between 1 and 120),
  address_line1 text,
  city text,
  region text,
  postal_code text,
  location text not null check (length(btrim(location)) between 1 and 300),
  geo extensions.geography(Point, 4326),
  lat double precision check (lat between -90 and 90),
  lng double precision check (lng between -180 and 180),
  timezone text not null default 'America/New_York',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index client_locations_org_idx on public.client_locations (organization_id);
create index client_locations_geo_gix on public.client_locations using gist (geo);

create table public.shifts (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null default auth.uid() references public.users (id) on delete restrict,
  organization_id uuid not null references public.organizations (id) on delete restrict,
  location_id uuid references public.client_locations (id) on delete set null,
  location text not null check (length(btrim(location)) between 1 and 300),
  geo extensions.geography(Point, 4326) not null,
  lat double precision check (lat between -90 and 90),
  lng double precision check (lng between -180 and 180),
  position_title text not null check (length(btrim(position_title)) between 1 and 120),
  tier_required smallint not null check (tier_required in (1, 2)),
  hourly_billing_rate_cents bigint not null check (hourly_billing_rate_cents > 0),
  hourly_pay_rate_cents bigint not null check (hourly_pay_rate_cents > 0),
  scheduled_start timestamptz not null,
  scheduled_end timestamptz not null,
  status text not null default 'open' check (status in ('open', 'claimed', 'in_progress', 'completed', 'approved', 'canceled')),
  is_emergency boolean not null default false,
  notes text check (notes is null or length(notes) <= 2000),
  claimed_by uuid references public.users (id) on delete restrict,
  claimed_by_name text,
  claimed_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  approved_at timestamptz,
  canceled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint shifts_time_order check (scheduled_end > scheduled_start),
  constraint shifts_max_length check (scheduled_end - scheduled_start <= interval '16 hours'),
  constraint shifts_rate_covers_pay check (hourly_billing_rate_cents >= hourly_pay_rate_cents),
  constraint shifts_claim_consistency check (
    (status = 'open' and claimed_by is null)
    or (status in ('claimed', 'in_progress', 'completed', 'approved') and claimed_by is not null)
    or status = 'canceled')
);
comment on column public.shifts.claimed_by_name is
  'Denormalized display name so managers never need read access to worker profiles (phone numbers).';
comment on column public.shifts.geo is 'Kept in sync with lat/lng: write either one.';
create index shifts_org_start_idx on public.shifts (organization_id, scheduled_start desc);
create index shifts_claimed_by_idx on public.shifts (claimed_by, scheduled_start desc) where claimed_by is not null;
create index shifts_client_idx on public.shifts (client_id);
create index shifts_location_idx on public.shifts (location_id);
create index shifts_open_idx on public.shifts (tier_required, scheduled_start) where status = 'open';
create index shifts_geo_gix on public.shifts using gist (geo);

create table public.shift_dispatches (
  id uuid primary key default gen_random_uuid(),
  shift_id uuid not null references public.shifts (id) on delete cascade,
  user_id uuid not null references public.users (id) on delete cascade,
  phone_e164 text not null check (phone_e164 ~ '^\+[1-9][0-9]{6,14}$'),
  claim_code text not null check (claim_code ~ '^[0-9]{4}$'),
  expires_at timestamptz not null,
  sent_at timestamptz,
  twilio_sid text,
  outcome text check (outcome in ('claimed', 'declined', 'expired', 'shift_filled', 'canceled', 'ineligible', 'failed')),
  responded_at timestamptz,
  created_at timestamptz not null default now(),
  unique (shift_id, user_id)
);
comment on column public.shift_dispatches.outcome is 'null = active (sent, unexpired, unanswered).';
-- Codes are unique among active dispatches; expired rows are closed out
-- (outcome = expired) before new codes are issued.
create unique index shift_dispatches_active_code_key on public.shift_dispatches (claim_code) where outcome is null;
create index shift_dispatches_user_active_idx on public.shift_dispatches (user_id) where outcome is null;
create index shift_dispatches_expiry_idx on public.shift_dispatches (expires_at) where outcome is null;
create index shift_dispatches_twilio_idx on public.shift_dispatches (twilio_sid) where twilio_sid is not null;

create table public.worker_compliance (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references public.users (id) on delete cascade,
  compliance_tier smallint not null default 1 check (compliance_tier in (1, 2)),
  background_check_status text not null default 'not_started'
    check (background_check_status in ('not_started', 'pending', 'passed', 'failed', 'consider')),
  fcra_disclosure_accepted_at timestamptz,
  drug_screen_status text not null default 'not_tested'
    check (drug_screen_status in ('not_tested', 'pending', 'passed', 'failed')),
  drug_screen_date timestamptz,
  rating_average numeric(3, 2) check (rating_average is null or rating_average between 1 and 5),
  completed_shifts integer not null default 0 check (completed_shifts >= 0),
  on_time_shifts integer not null default 0 check (on_time_shifts >= 0),
  tier2_invited_at timestamptz,
  engagement_type text not null default 'contractor_1099' check (engagement_type in ('contractor_1099', 'w2_eor')),
  payout_destination text not null default 'ezwerkz_wallet' check (payout_destination in ('stripe_connect', 'ezwerkz_wallet')),
  stripe_connect_account_id text unique,
  background_check_provider_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint worker_compliance_on_time_le_completed check (on_time_shifts <= completed_shifts)
);
comment on column public.worker_compliance.engagement_type is
  'contractor_1099 or w2_eor. Tier 2 register/keyholder roles carry misclassification risk; W-2 via an Employer of Record is recommended.';
create index worker_compliance_tier2_queue_idx on public.worker_compliance (tier2_invited_at) where compliance_tier = 1 and tier2_invited_at is not null;

create table public.background_checks (
  id uuid primary key default gen_random_uuid(),
  worker_id uuid not null references public.users (id) on delete restrict,
  provider text not null default 'checkr' check (length(btrim(provider)) between 1 and 40),
  provider_candidate_id text,
  provider_report_id text unique,
  package text,
  status text not null default 'ordered'
    check (status in ('ordered', 'pending', 'clear', 'consider', 'suspended', 'canceled', 'error')),
  adjudication text not null default 'not_required'
    check (adjudication in ('not_required', 'pending_review', 'cleared', 'pre_adverse_sent', 'final_adverse_sent')),
  fcra_consent_id uuid not null references public.consents (id) on delete restrict,
  ordered_by uuid,
  ordered_at timestamptz not null default now(),
  completed_at timestamptz,
  cost_cents bigint not null check (cost_cents >= 0),
  paid_by text not null default 'platform' check (paid_by = 'platform'),
  pre_adverse_sent_at timestamptz,
  final_adverse_eligible_at timestamptz,
  final_adverse_sent_at timestamptz,
  reviewed_by uuid references public.users (id) on delete restrict,
  reviewed_at timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint background_checks_final_after_wait check (
    final_adverse_sent_at is null
    or (pre_adverse_sent_at is not null and final_adverse_eligible_at is not null
        and final_adverse_sent_at >= final_adverse_eligible_at))
);
comment on column public.background_checks.paid_by is 'Always the platform. The fee is never deducted from worker pay.';
comment on column public.background_checks.adjudication is
  'Human review states for a consider result: pending_review -> pre_adverse_sent -> (5 business days) -> final_adverse_sent, or cleared. Never automatic.';
create unique index background_checks_one_open on public.background_checks (worker_id) where status in ('ordered', 'pending');
create index background_checks_worker_idx on public.background_checks (worker_id, ordered_at desc);
create index background_checks_consent_idx on public.background_checks (fcra_consent_id);
create index background_checks_reviewer_idx on public.background_checks (reviewed_by);
create index background_checks_review_queue_idx on public.background_checks (ordered_at) where status = 'consider';

create table public.drug_screen_logs (
  id uuid primary key default gen_random_uuid(),
  worker_id uuid not null references public.users (id) on delete restrict,
  collector_id uuid not null references public.users (id) on delete restrict,
  collected_at timestamptz not null,
  kit_lot_number text not null check (length(btrim(kit_lot_number)) between 1 and 64),
  result text not null check (result in ('negative', 'non_negative', 'invalid')),
  screen_type text not null default 'rapid_oral_fluid' check (screen_type in ('rapid_oral_fluid', 'lab_confirmation')),
  evidence_path text not null check (length(btrim(evidence_path)) > 0),
  worker_consent_at timestamptz not null,
  consent_id uuid not null references public.consents (id) on delete restrict,
  notes text check (notes is null or length(notes) <= 2000),
  created_at timestamptz not null default now(),
  constraint drug_screen_collector_not_worker check (collector_id <> worker_id),
  constraint drug_screen_consent_before_collection check (worker_consent_at <= collected_at)
);
comment on table public.drug_screen_logs is
  'Append-only. A result is only ever a new row; there is no override. Rapid non-negative = presumptive (pending lab confirmation).';
create index drug_screen_logs_worker_idx on public.drug_screen_logs (worker_id, collected_at desc);
create index drug_screen_logs_collector_idx on public.drug_screen_logs (collector_id);
create index drug_screen_logs_consent_idx on public.drug_screen_logs (consent_id);

create table public.shift_ratings (
  id uuid primary key default gen_random_uuid(),
  shift_id uuid not null unique references public.shifts (id) on delete cascade,
  worker_id uuid not null references public.users (id) on delete cascade,
  rater_id uuid not null references public.users (id) on delete restrict,
  rating smallint not null check (rating between 1 and 5),
  on_time boolean not null,
  comment text check (comment is null or length(comment) <= 1000),
  created_at timestamptz not null default now()
);
create index shift_ratings_worker_idx on public.shift_ratings (worker_id);
create index shift_ratings_rater_idx on public.shift_ratings (rater_id);

create table public.payouts (
  id uuid primary key default gen_random_uuid(),
  shift_id uuid not null unique references public.shifts (id) on delete restrict,
  worker_id uuid not null references public.users (id) on delete restrict,
  total_billed_cents bigint not null check (total_billed_cents >= 0),
  total_paid_to_worker_cents bigint not null check (total_paid_to_worker_cents >= 0),
  agency_margin_cents bigint not null,
  stripe_payment_intent_id text unique,
  stripe_transfer_id text unique,
  destination text not null check (destination in ('stripe_connect', 'ezwerkz_wallet')),
  status text not null default 'pending' check (status in ('pending', 'paid', 'failed')),
  paid_at timestamptz,
  failure_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint payouts_amounts_balance check (total_billed_cents = total_paid_to_worker_cents + agency_margin_cents)
);
create index payouts_worker_idx on public.payouts (worker_id, created_at desc);
create index payouts_pending_idx on public.payouts (created_at) where status = 'pending';

create table public.contract_signatures (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references public.organizations (id) on delete restrict,
  signer_id uuid not null default auth.uid() references public.users (id) on delete restrict,
  signer_name text check (signer_name is null or length(signer_name) <= 200),
  signer_title text check (signer_title is null or length(signer_title) <= 120),
  msa_version text not null references public.msa_versions (version) on delete restrict,
  msa_signed boolean not null,
  section8_acknowledged boolean not null,
  section8_initials text not null check (length(btrim(section8_initials)) between 1 and 8),
  signed_at timestamptz not null default now(),
  ip_address text check (ip_address is null or length(ip_address) <= 64),
  user_agent text check (user_agent is null or length(user_agent) <= 512),
  document_sha256 text not null check (document_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  -- A signature exists only with BOTH the MSA signature and the separate,
  -- conspicuous Section 8 acknowledgment (procedural-unconscionability guard).
  constraint contract_signatures_both_acknowledged check (msa_signed and section8_acknowledged)
);
comment on table public.contract_signatures is 'Immutable e-signature records for the MSA, incl. the separate Section 8 acknowledgment + initials.';
create index contract_signatures_company_idx on public.contract_signatures (company_id, signed_at desc);
create index contract_signatures_signer_idx on public.contract_signatures (signer_id);
create index contract_signatures_version_idx on public.contract_signatures (msa_version);

create table public.chat_threads (
  id uuid primary key default gen_random_uuid(),
  shift_id uuid not null references public.shifts (id) on delete cascade,
  organization_id uuid not null references public.organizations (id) on delete cascade,
  worker_id uuid not null references public.users (id) on delete cascade,
  manager_id uuid references public.users (id) on delete set null,
  monitoring_disclosed boolean not null default true,
  created_at timestamptz not null default now(),
  unique (shift_id, worker_id)
);
comment on column public.chat_threads.monitoring_disclosed is 'Chat monitoring is disclosed in the thread header and MSA/ToS.';
create index chat_threads_worker_idx on public.chat_threads (worker_id);
create index chat_threads_org_idx on public.chat_threads (organization_id);
create index chat_threads_manager_idx on public.chat_threads (manager_id);

create table public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references public.chat_threads (id) on delete cascade,
  sender_id uuid not null default auth.uid() references public.users (id) on delete cascade,
  sender_role text not null check (sender_role in ('member', 'worker', 'client_manager', 'admin')),
  body text not null check (length(btrim(body)) between 1 and 2000),
  flagged boolean not null default false,
  created_at timestamptz not null default now()
);
create index chat_messages_thread_idx on public.chat_messages (thread_id, created_at);
create index chat_messages_sender_idx on public.chat_messages (sender_id);

create table public.poach_flags (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references public.chat_messages (id) on delete cascade,
  thread_id uuid not null references public.chat_threads (id) on delete cascade,
  sender_id uuid not null references public.users (id) on delete cascade,
  matched_rules text[] not null check (cardinality(matched_rules) >= 1),
  severity text not null check (severity in ('low', 'medium', 'high')),
  excerpt text not null check (length(excerpt) <= 500),
  status text not null default 'open' check (status in ('open', 'reviewed', 'dismissed', 'escalated')),
  reviewed_by uuid references public.users (id) on delete set null,
  reviewed_at timestamptz,
  resolution_notes text check (resolution_notes is null or length(resolution_notes) <= 2000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table public.poach_flags is 'Admin review queue. Flags warn and inform; they never fine anyone automatically.';
create index poach_flags_queue_idx on public.poach_flags (status, created_at desc);
create index poach_flags_message_idx on public.poach_flags (message_id);
create index poach_flags_thread_idx on public.poach_flags (thread_id);
create index poach_flags_sender_idx on public.poach_flags (sender_id);
create index poach_flags_reviewer_idx on public.poach_flags (reviewed_by);

-- -----------------------------------------------------------------------------
-- Helpers
-- -----------------------------------------------------------------------------

-- Caller's dispatch tier (0 when the caller is not a worker).
create function public.worker_tier() returns smallint
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select case when u.role = 'worker' then coalesce(wc.compliance_tier, 1) else 0 end
      from public.users u
      left join public.worker_compliance wc on wc.user_id = u.id
     where u.id = auth.uid()), 0)::smallint;
$$;

create function public.has_signed_msa(p_organization_id uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select (public.is_trusted_caller() or public.is_admin() or p_organization_id = public.user_org_id())
     and exists (
       select 1 from public.contract_signatures cs
        where cs.company_id = p_organization_id
          and cs.msa_signed and cs.section8_acknowledged
          and (cs.msa_version in (select v.version from public.msa_versions v where v.is_current)
               or not exists (select 1 from public.msa_versions v where v.is_current)));
$$;

create function public.add_business_days(p_from timestamptz, p_days integer) returns timestamptz
language plpgsql immutable set search_path = '' as $$
declare
  v_at timestamptz := p_from;
  v_counted integer := 0;
begin
  while v_counted < p_days loop
    v_at := v_at + interval '1 day';
    if extract(isodow from (v_at at time zone 'America/New_York')) < 6 then
      v_counted := v_counted + 1;
    end if;
  end loop;
  return v_at;
end $$;

create function public.is_thread_participant(p_thread_id uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.chat_threads t
     where t.id = p_thread_id
       and (t.worker_id = auth.uid()
            or (t.organization_id = public.user_org_id() and public.current_role_is('client_manager'))));
$$;

-- lat/lng <-> geo for tables with (geo, lat, lng) columns.
create function private.sync_geo_latlng() returns trigger
language plpgsql set search_path = public, extensions as $$
begin
  if new.geo is not null and (tg_op = 'INSERT' or new.geo is distinct from old.geo) then
    new.lat := st_y(new.geo::geometry);
    new.lng := st_x(new.geo::geometry);
  elsif new.lat is not null and new.lng is not null
        and (tg_op = 'INSERT' or new.lat is distinct from old.lat or new.lng is distinct from old.lng or new.geo is null) then
    new.geo := st_setsrid(st_makepoint(new.lng, new.lat), 4326)::geography;
  end if;
  return new;
end $$;

create trigger t20_geo before insert or update on public.client_locations
  for each row execute function private.sync_geo_latlng();
create trigger t90_touch before update on public.client_locations
  for each row execute function private.set_updated_at();

-- -----------------------------------------------------------------------------
-- Worker lifecycle: compliance row, consents, tier changes
-- -----------------------------------------------------------------------------

create function private.users_role_changed() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_prev text;
begin
  if new.role = 'worker' then
    v_prev := private.enter_internal();
    insert into public.worker_compliance (user_id, fcra_disclosure_accepted_at)
    values (new.id, (select max(c.accepted_at) from public.consents c
                      where c.user_id = new.id and c.kind = 'fcra_disclosure' and c.revoked_at is null))
    on conflict (user_id) do nothing;
    perform private.exit_internal(v_prev);
  end if;
  if new.role in ('worker', 'client_manager') then
    insert into public.user_modules (user_id, module) values (new.id, 'shifts') on conflict (user_id, module) do nothing;
  end if;
  if tg_op = 'UPDATE' then
    insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
    values (auth.uid(), 'users.role_changed', 'users', new.id,
            jsonb_build_object('old_role', old.role, 'new_role', new.role,
                               'old_org', old.organization_id, 'new_org', new.organization_id));
  end if;
  return null;
end $$;

create trigger t60_role_changed after insert or update of role, organization_id on public.users
  for each row execute function private.users_role_changed();

create function private.consents_fcra_sync() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_prev text;
begin
  if new.kind = 'fcra_disclosure' then
    v_prev := private.enter_internal();
    update public.worker_compliance
       set fcra_disclosure_accepted_at = (
         select max(c.accepted_at) from public.consents c
          where c.user_id = new.user_id and c.kind = 'fcra_disclosure' and c.revoked_at is null)
     where user_id = new.user_id;
    perform private.exit_internal(v_prev);
  end if;
  return null;
end $$;

create trigger t51_fcra_sync after insert or update of revoked_at on public.consents
  for each row execute function private.consents_fcra_sync();

create function private.worker_compliance_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  v_internal boolean := coalesce(current_setting('ezwerkz.internal', true), '') = 'on';
  v_end_user boolean := current_user in ('anon', 'authenticated');
begin
  if tg_op = 'INSERT' then
    if not v_internal then
      new.compliance_tier := 1;
      new.background_check_status := 'not_started';
      new.drug_screen_status := 'not_tested';
      new.drug_screen_date := null;
      new.fcra_disclosure_accepted_at := null;
      new.rating_average := null;
      new.completed_shifts := 0;
      new.on_time_shifts := 0;
      new.tier2_invited_at := null;
    end if;
    return new;
  end if;

  if not v_internal and (
       new.compliance_tier is distinct from old.compliance_tier
    or new.background_check_status is distinct from old.background_check_status
    or new.drug_screen_status is distinct from old.drug_screen_status
    or new.drug_screen_date is distinct from old.drug_screen_date
    or new.fcra_disclosure_accepted_at is distinct from old.fcra_disclosure_accepted_at
    or new.rating_average is distinct from old.rating_average
    or new.completed_shifts is distinct from old.completed_shifts
    or new.on_time_shifts is distinct from old.on_time_shifts
    or new.tier2_invited_at is distinct from old.tier2_invited_at) then
    raise exception 'FORBIDDEN_COLUMN'
      using detail = 'Compliance statuses change only through background_checks, drug_screen_logs, consents and approve_shift().',
            errcode = '42501';
  end if;
  if new.user_id is distinct from old.user_id then
    raise exception 'FORBIDDEN_COLUMN' using errcode = '42501';
  end if;
  if v_end_user and not public.is_admin() and (
       new.engagement_type is distinct from old.engagement_type
    or new.stripe_connect_account_id is distinct from old.stripe_connect_account_id
    or new.background_check_provider_id is distinct from old.background_check_provider_id) then
    raise exception 'FORBIDDEN_COLUMN' using detail = 'Workers can change their payout destination only.', errcode = '42501';
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update on public.worker_compliance
  for each row execute function private.worker_compliance_guard();
create trigger t90_touch before update on public.worker_compliance
  for each row execute function private.set_updated_at();

-- Tier 2 = invited + background passed + drug screen passed. Tier drops back to
-- 1 only on a confirmed failure (final adverse action or lab-confirmed result).
create function private.refresh_worker_tier(p_worker_id uuid) returns smallint
language plpgsql security definer set search_path = '' as $$
declare
  v_wc public.worker_compliance%rowtype;
  v_prev text;
begin
  select * into v_wc from public.worker_compliance where user_id = p_worker_id for update;
  if not found then
    return null;
  end if;
  if v_wc.compliance_tier = 1 and v_wc.tier2_invited_at is not null
     and v_wc.drug_screen_status = 'passed' and v_wc.background_check_status = 'passed' then
    v_prev := private.enter_internal();
    update public.worker_compliance set compliance_tier = 2 where id = v_wc.id;
    perform private.exit_internal(v_prev);
    perform private.notify(p_worker_id, 'shifts.tier2_unlocked', 'You''re Corporate Certified',
      'Tier 2 shifts (register, keyholder and more) now show up in your feed at the Tier 2 pay rate.', '/shifts', '{}'::jsonb);
    insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
    values (auth.uid(), 'worker.tier_changed', 'worker_compliance', v_wc.id, jsonb_build_object('from', 1, 'to', 2));
    return 2;
  elsif v_wc.compliance_tier = 2 and (v_wc.drug_screen_status = 'failed' or v_wc.background_check_status = 'failed') then
    v_prev := private.enter_internal();
    update public.worker_compliance set compliance_tier = 1 where id = v_wc.id;
    perform private.exit_internal(v_prev);
    insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
    values (auth.uid(), 'worker.tier_changed', 'worker_compliance', v_wc.id, jsonb_build_object('from', 2, 'to', 1));
    return 1;
  end if;
  return v_wc.compliance_tier;
end $$;

create function private.evaluate_tier2(p_worker_id uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
declare
  v_wc public.worker_compliance%rowtype;
  v_qualifying integer;
  v_ok boolean;
  v_prev text;
begin
  select wc.* into v_wc
    from public.worker_compliance wc
    join public.users u on u.id = wc.user_id and u.role = 'worker'
   where wc.user_id = p_worker_id
   for update of wc;
  if not found then
    return false;
  end if;
  if v_wc.compliance_tier >= 2 then
    return true;
  end if;

  select count(*) into v_qualifying
    from public.shift_ratings r
    join public.shifts s on s.id = r.shift_id
   where r.worker_id = p_worker_id and r.on_time and s.tier_required = 1 and s.status = 'approved';

  v_ok := v_qualifying >= public.config_int('tier2_qualifying_shifts')
          and coalesce(v_wc.rating_average, 0) >= public.config_numeric('tier2_min_rating');

  if v_ok and v_wc.tier2_invited_at is null then
    v_prev := private.enter_internal();
    update public.worker_compliance set tier2_invited_at = now() where id = v_wc.id;
    perform private.exit_internal(v_prev);
    perform private.notify(p_worker_id, 'shifts.tier2_invite', 'You''re invited to Tier 2',
      'Great work on your shifts. Tier 2 pays ' || private.fmt_cents(public.config_int('tier2_pay_rate_cents'))
        || '/hr. EzWerkz covers the ' || private.fmt_cents(public.config_int('background_check_cost_cents'))
        || ' background check; it is never taken out of your pay.',
      '/shifts', jsonb_build_object('qualifying_shifts', v_qualifying));
  end if;
  return v_ok;
end $$;

-- -----------------------------------------------------------------------------
-- Shifts: guard (who may change what), derived columns, side effects
-- -----------------------------------------------------------------------------

-- search_path includes extensions so geo IS DISTINCT FROM resolves PostGIS's
-- geography = operator.
create function private.shifts_guard() returns trigger
language plpgsql set search_path = public, extensions as $$
declare
  v_end_user boolean := current_user in ('anon', 'authenticated');
  v_internal boolean := coalesce(current_setting('ezwerkz.internal', true), '') = 'on';
  v_uid uuid := auth.uid();
  v_admin boolean;
  v_manager boolean;
  v_worker boolean;
begin
  if tg_op = 'INSERT' then
    if v_end_user then
      new.client_id := v_uid;
      new.organization_id := public.user_org_id();
      new.status := 'open';
      new.claimed_by := null;
      new.claimed_at := null;
      new.started_at := null;
      new.completed_at := null;
      new.approved_at := null;
      new.canceled_at := null;
      -- Rates always come from platform pricing for client-posted shifts.
      new.hourly_billing_rate_cents := null;
      new.hourly_pay_rate_cents := null;
      if new.organization_id is null or not public.has_signed_msa(new.organization_id) then
        raise exception 'MSA_REQUIRED'
          using detail = 'Your company must sign the MSA, including the Section 8 acknowledgment, before posting shifts.',
                errcode = '42501';
      end if;
      if new.scheduled_end <= now() then
        raise exception 'SHIFT_IN_PAST' using errcode = '22023';
      end if;
      if new.location_id is not null and not exists (
        select 1 from public.client_locations cl
         where cl.id = new.location_id and cl.organization_id = new.organization_id) then
        raise exception 'INVALID_LOCATION' using errcode = '22023';
      end if;
    end if;
    new.hourly_billing_rate_cents := coalesce(new.hourly_billing_rate_cents,
      public.config_int('tier' || new.tier_required || '_bill_rate_cents'));
    new.hourly_pay_rate_cents := coalesce(new.hourly_pay_rate_cents,
      public.config_int('tier' || new.tier_required || '_pay_rate_cents'));
    return new;
  end if;

  -- claim_shift() / approve_shift() run with the internal flag.
  if v_internal then
    return new;
  end if;

  if new.client_id is distinct from old.client_id or new.organization_id is distinct from old.organization_id
     or new.created_at is distinct from old.created_at then
    raise exception 'FORBIDDEN_COLUMN' using errcode = '42501';
  end if;
  if new.status = 'approved' or new.approved_at is distinct from old.approved_at then
    raise exception 'USE_APPROVE_SHIFT' using detail = 'Approve with approve_shift().', errcode = '42501';
  end if;
  if new.claimed_by is not null and new.claimed_by is distinct from old.claimed_by then
    raise exception 'USE_CLAIM_SHIFT' using detail = 'Claim with claim_shift().', errcode = '42501';
  end if;

  if v_end_user then
    v_admin := public.is_admin();
    v_manager := public.current_role_is('client_manager') and old.organization_id = public.user_org_id();
    v_worker := old.claimed_by is not null and old.claimed_by = v_uid;

    if new.tier_required is distinct from old.tier_required then
      new.hourly_billing_rate_cents := public.config_int('tier' || new.tier_required || '_bill_rate_cents');
      new.hourly_pay_rate_cents := public.config_int('tier' || new.tier_required || '_pay_rate_cents');
    elsif new.hourly_billing_rate_cents is distinct from old.hourly_billing_rate_cents
       or new.hourly_pay_rate_cents is distinct from old.hourly_pay_rate_cents then
      raise exception 'FORBIDDEN_COLUMN' using detail = 'Rates come from platform pricing.', errcode = '42501';
    end if;

    if new.location is distinct from old.location or new.geo is distinct from old.geo
       or new.lat is distinct from old.lat or new.lng is distinct from old.lng
       or new.location_id is distinct from old.location_id or new.position_title is distinct from old.position_title
       or new.tier_required is distinct from old.tier_required or new.scheduled_start is distinct from old.scheduled_start
       or new.scheduled_end is distinct from old.scheduled_end or new.is_emergency is distinct from old.is_emergency then
      if not (v_manager or v_admin) then
        raise exception 'FORBIDDEN_COLUMN' using errcode = '42501';
      end if;
      if old.status <> 'open' then
        raise exception 'SHIFT_LOCKED' using detail = 'Details can only change while the shift is open.', errcode = '22023';
      end if;
    end if;
    if new.notes is distinct from old.notes and not (v_manager or v_admin) then
      raise exception 'FORBIDDEN_COLUMN' using errcode = '42501';
    end if;
    if (new.claimed_at is distinct from old.claimed_at and new.claimed_by is not null)
       or new.started_at is distinct from old.started_at or new.completed_at is distinct from old.completed_at
       or new.canceled_at is distinct from old.canceled_at then
      raise exception 'FORBIDDEN_COLUMN' using detail = 'Timestamps are set by EzWerkz.', errcode = '42501';
    end if;

    if new.status is distinct from old.status then
      if v_manager or v_admin then
        if not ((old.status in ('open', 'claimed', 'in_progress') and new.status = 'canceled')
             or (old.status = 'claimed' and new.status in ('in_progress', 'completed'))
             or (old.status = 'in_progress' and new.status = 'completed')
             or (v_admin and old.status = 'claimed' and new.status = 'open')) then
          raise exception 'INVALID_STATUS_TRANSITION'
            using detail = format('%s -> %s is not allowed.', old.status, new.status), errcode = '22023';
        end if;
      elsif v_worker then
        if not ((old.status = 'claimed' and new.status = 'in_progress')
             or (old.status = 'in_progress' and new.status = 'completed')
             or (old.status = 'claimed' and new.status = 'open')) then
          raise exception 'INVALID_STATUS_TRANSITION'
            using detail = format('%s -> %s is not allowed.', old.status, new.status), errcode = '22023';
        end if;
        if new.status = 'open' and now() >= old.scheduled_start then
          raise exception 'TOO_LATE_TO_RELEASE' using detail = 'Contact the store; this shift has already started.', errcode = '22023';
        end if;
      else
        raise exception 'FORBIDDEN' using errcode = '42501';
      end if;
    end if;
  end if;

  -- Releasing a claim (worker drop, or admin reassign).
  if new.claimed_by is null and old.claimed_by is not null then
    if new.status <> 'open' then
      raise exception 'INVALID_STATUS_TRANSITION' using detail = 'A released shift goes back to open.', errcode = '22023';
    end if;
    new.claimed_at := null;
    new.claimed_by_name := null;
  end if;

  if new.status = 'in_progress' and old.status <> 'in_progress' then
    new.started_at := now();
  elsif new.status = 'completed' and old.status <> 'completed' then
    new.completed_at := now();
    new.started_at := coalesce(new.started_at, old.started_at, new.scheduled_start);
  elsif new.status = 'canceled' and old.status <> 'canceled' then
    new.canceled_at := now();
  end if;
  return new;
end $$;

create function private.shifts_derive() returns trigger
language plpgsql security definer set search_path = public, extensions as $$
begin
  if new.geo is not null and (tg_op = 'INSERT' or new.geo is distinct from old.geo) then
    new.lat := st_y(new.geo::geometry);
    new.lng := st_x(new.geo::geometry);
  elsif new.lat is not null and new.lng is not null
        and (tg_op = 'INSERT' or new.lat is distinct from old.lat or new.lng is distinct from old.lng or new.geo is null) then
    new.geo := st_setsrid(st_makepoint(new.lng, new.lat), 4326)::geography;
  end if;

  if new.claimed_by is null then
    new.claimed_by_name := null;
  elsif tg_op = 'INSERT' or new.claimed_by is distinct from old.claimed_by or new.claimed_by_name is null then
    select u.full_name into new.claimed_by_name from public.users u where u.id = new.claimed_by;
  end if;
  return new;
end $$;

create function private.shifts_after_update() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.claimed_by is not null and new.claimed_by is distinct from old.claimed_by then
    insert into public.chat_threads (shift_id, organization_id, worker_id, manager_id)
    values (new.id, new.organization_id, new.claimed_by, new.client_id)
    on conflict (shift_id, worker_id) do nothing;

    update public.shift_dispatches
       set outcome = case when user_id = new.claimed_by then 'claimed' else 'shift_filled' end,
           responded_at = case when user_id = new.claimed_by then now() else responded_at end
     where shift_id = new.id and outcome is null;

    perform private.notify(new.client_id, 'shift.claimed', 'Shift claimed',
      coalesce(nullif(new.claimed_by_name, ''), 'A worker') || ' claimed your ' || new.position_title || ' shift.',
      '/business/shifts/' || new.id, jsonb_build_object('shift_id', new.id));
    perform private.notify(new.claimed_by, 'shift.booked', 'You''re booked',
      new.position_title || ' at ' || new.location || '. Open the shift for details and chat.',
      '/shifts/' || new.id, jsonb_build_object('shift_id', new.id));
  elsif old.claimed_by is not null and new.claimed_by is null then
    perform private.notify(new.client_id, 'shift.released', 'A worker released your shift',
      'Your ' || new.position_title || ' shift is open again.', '/business/shifts/' || new.id,
      jsonb_build_object('shift_id', new.id));
  end if;

  if new.status = 'canceled' and old.status <> 'canceled' then
    update public.shift_dispatches set outcome = 'canceled' where shift_id = new.id and outcome is null;
    if new.claimed_by is not null then
      perform private.notify(new.claimed_by, 'shift.canceled', 'Shift canceled',
        'The store canceled the ' || new.position_title || ' shift. Sorry for the change.', '/shifts',
        jsonb_build_object('shift_id', new.id));
    end if;
  end if;
  return null;
end $$;

create trigger t10_guard before insert or update on public.shifts
  for each row execute function private.shifts_guard();
create trigger t20_derive before insert or update on public.shifts
  for each row execute function private.shifts_derive();
create trigger t50_after_update after update on public.shifts
  for each row execute function private.shifts_after_update();
create trigger t90_touch before update on public.shifts
  for each row execute function private.set_updated_at();

-- -----------------------------------------------------------------------------
-- Background checks (FCRA)
-- -----------------------------------------------------------------------------

create function private.background_checks_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  v_end_user boolean := current_user in ('anon', 'authenticated');
  v_consent public.consents%rowtype;
  v_requested text;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.users u where u.id = new.worker_id and u.role = 'worker') then
      raise exception 'NOT_A_WORKER' using errcode = '22023';
    end if;
    select c.* into v_consent from public.consents c
     where c.user_id = new.worker_id and c.kind = 'fcra_disclosure' and c.revoked_at is null and c.accepted_at <= now()
     order by c.accepted_at desc limit 1;
    if not found then
      raise exception 'FCRA_CONSENT_REQUIRED'
        using detail = 'The worker must accept the standalone FCRA disclosure and authorization before a check is ordered.',
              errcode = '42501';
    end if;
    new.fcra_consent_id := v_consent.id;
    new.cost_cents := public.config_int('background_check_cost_cents');
    new.paid_by := 'platform';
    new.ordered_by := coalesce(new.ordered_by, auth.uid());
    new.ordered_at := now();
    new.adjudication := case when new.status = 'consider' then 'pending_review' else 'not_required' end;
    new.pre_adverse_sent_at := null;
    new.final_adverse_eligible_at := null;
    new.final_adverse_sent_at := null;
    new.reviewed_by := null;
    new.reviewed_at := null;
    if new.status in ('clear', 'consider') then
      new.completed_at := coalesce(new.completed_at, now());
    end if;
    return new;
  end if;

  if new.worker_id is distinct from old.worker_id or new.fcra_consent_id is distinct from old.fcra_consent_id
     or new.cost_cents is distinct from old.cost_cents or new.paid_by is distinct from old.paid_by
     or new.ordered_at is distinct from old.ordered_at or new.ordered_by is distinct from old.ordered_by
     or new.provider is distinct from old.provider then
    raise exception 'FORBIDDEN_COLUMN' using errcode = '42501';
  end if;

  v_requested := new.adjudication;
  if v_requested is distinct from old.adjudication then
    -- A person decides. Never a webhook, never a timer.
    if not ((old.adjudication = 'pending_review' and v_requested in ('cleared', 'pre_adverse_sent'))
         or (old.adjudication = 'pre_adverse_sent' and v_requested in ('cleared', 'final_adverse_sent'))) then
      raise exception 'INVALID_ADJUDICATION'
        using detail = format('%s -> %s is not allowed.', old.adjudication, v_requested), errcode = '22023';
    end if;
    if old.status <> 'consider' or new.status <> 'consider' then
      raise exception 'INVALID_ADJUDICATION' using detail = 'Only a consider result is adjudicated.', errcode = '22023';
    end if;
    if v_end_user then
      if not public.is_admin() then
        raise exception 'FORBIDDEN' using errcode = '42501';
      end if;
      new.reviewed_by := auth.uid();
    elsif new.reviewed_by is null
          or not exists (select 1 from public.users u where u.id = new.reviewed_by and u.role = 'admin') then
      raise exception 'HUMAN_REVIEW_REQUIRED'
        using detail = 'Adverse-action steps must name the admin who reviewed the report.', errcode = '42501';
    end if;
    new.reviewed_at := now();
    if v_requested = 'pre_adverse_sent' then
      new.pre_adverse_sent_at := now();
      new.final_adverse_eligible_at := public.add_business_days(now(), 5);
      new.final_adverse_sent_at := null;
    elsif v_requested = 'final_adverse_sent' then
      if now() < old.final_adverse_eligible_at then
        raise exception 'ADVERSE_ACTION_WAITING_PERIOD'
          using detail = format('The final notice may be sent on or after %s.', old.final_adverse_eligible_at),
                errcode = '22023';
      end if;
      new.pre_adverse_sent_at := old.pre_adverse_sent_at;
      new.final_adverse_eligible_at := old.final_adverse_eligible_at;
      new.final_adverse_sent_at := now();
    else
      new.pre_adverse_sent_at := old.pre_adverse_sent_at;
      new.final_adverse_eligible_at := old.final_adverse_eligible_at;
      new.final_adverse_sent_at := null;
    end if;
  else
    if new.pre_adverse_sent_at is distinct from old.pre_adverse_sent_at
       or new.final_adverse_eligible_at is distinct from old.final_adverse_eligible_at
       or new.final_adverse_sent_at is distinct from old.final_adverse_sent_at
       or new.reviewed_by is distinct from old.reviewed_by or new.reviewed_at is distinct from old.reviewed_at then
      raise exception 'FORBIDDEN_COLUMN' using detail = 'Adverse-action fields change only with an adjudication step.', errcode = '42501';
    end if;
    -- Provider status updates (webhook or admin).
    if new.status is distinct from old.status then
      if new.status in ('clear', 'consider') then
        new.completed_at := coalesce(new.completed_at, now());
      end if;
      if new.status = 'consider' and old.adjudication = 'not_required' then
        new.adjudication := 'pending_review';
      elsif new.status = 'clear' and old.adjudication in ('pending_review', 'pre_adverse_sent') then
        new.adjudication := 'cleared';
      end if;
    end if;
  end if;
  return new;
end $$;

create function private.background_checks_after() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_status text;
  v_prev text;
begin
  v_status := case
    when new.status in ('ordered', 'pending', 'suspended') then 'pending'
    when new.status = 'clear' then 'passed'
    when new.status = 'consider' then
      case new.adjudication when 'cleared' then 'passed' when 'final_adverse_sent' then 'failed' else 'consider' end
    else 'not_started'
  end;

  if new.id = (select b.id from public.background_checks b where b.worker_id = new.worker_id
                order by b.ordered_at desc, b.created_at desc limit 1) then
    v_prev := private.enter_internal();
    update public.worker_compliance
       set background_check_status = v_status,
           background_check_provider_id = coalesce(new.provider_candidate_id, background_check_provider_id)
     where user_id = new.worker_id;
    perform private.exit_internal(v_prev);
  end if;

  if tg_op = 'INSERT' then
    insert into public.treasury_allocations (source_type, source_id, bucket, amount_cents, note)
    values ('background_check', new.id, 'background_check', new.cost_cents, 'platform-paid background check');
  end if;

  if tg_op = 'UPDATE' and new.adjudication is distinct from old.adjudication then
    if new.adjudication = 'pre_adverse_sent' then
      perform private.notify(new.worker_id, 'compliance.pre_adverse', 'About your background check',
        'We sent you a copy of your report and a summary of your rights under the FCRA. Nothing has been decided: you have at least 5 business days to tell us or the reporting agency about anything inaccurate.',
        '/shifts', jsonb_build_object('background_check_id', new.id));
    elsif new.adjudication = 'final_adverse_sent' then
      perform private.notify(new.worker_id, 'compliance.final_adverse', 'Background check decision',
        'We sent you a final notice with the reporting agency''s contact details and your right to dispute the report and get a free copy.',
        '/shifts', jsonb_build_object('background_check_id', new.id));
    elsif new.adjudication = 'cleared' then
      perform private.notify(new.worker_id, 'compliance.background_cleared', 'Background check complete',
        'You''re all set. Thanks for your patience.', '/shifts', jsonb_build_object('background_check_id', new.id));
    end if;
    if new.reviewed_at is distinct from old.reviewed_at then
      insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
      values (coalesce(auth.uid(), new.reviewed_by), 'background_check.adjudicated', 'background_checks', new.id,
              jsonb_build_object('from', old.adjudication, 'to', new.adjudication, 'reviewed_by', new.reviewed_by));
    end if;
  elsif new.status = 'clear' and (tg_op = 'INSERT' or old.status is distinct from 'clear') then
    perform private.notify(new.worker_id, 'compliance.background_clear', 'Background check complete',
      'Your background check came back clear.', '/shifts', jsonb_build_object('background_check_id', new.id));
  end if;

  if tg_op = 'UPDATE' and new.status is distinct from old.status then
    insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
    values (auth.uid(), 'background_check.result', 'background_checks', new.id,
            jsonb_build_object('from', old.status, 'to', new.status));
  end if;

  perform private.refresh_worker_tier(new.worker_id);
  return null;
end $$;

create trigger t10_guard before insert or update on public.background_checks
  for each row execute function private.background_checks_guard();
create trigger t50_after after insert or update on public.background_checks
  for each row execute function private.background_checks_after();
create trigger t90_touch before update on public.background_checks
  for each row execute function private.set_updated_at();

-- -----------------------------------------------------------------------------
-- Drug screens (append-only)
-- -----------------------------------------------------------------------------

create function private.drug_screen_guard() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_consent public.consents%rowtype;
begin
  if not exists (select 1 from public.users u where u.id = new.collector_id and u.role = 'admin') then
    raise exception 'COLLECTOR_NOT_ADMIN' using errcode = '42501';
  end if;
  if new.collector_id = new.worker_id then
    raise exception 'COLLECTOR_IS_WORKER' using detail = 'A worker cannot record their own screen.', errcode = '42501';
  end if;
  if not exists (select 1 from public.users u where u.id = new.worker_id and u.role = 'worker') then
    raise exception 'NOT_A_WORKER' using errcode = '22023';
  end if;

  if new.collected_at is null or new.collected_at > now() + interval '5 minutes' then
    raise exception 'INVALID_COLLECTED_AT' using errcode = '22023';
  end if;
  select c.* into v_consent from public.consents c
   where c.user_id = new.worker_id and c.kind = 'drug_screen' and c.revoked_at is null
     and c.accepted_at <= new.collected_at
   order by c.accepted_at desc limit 1;
  if not found then
    raise exception 'DRUG_SCREEN_CONSENT_REQUIRED'
      using detail = 'The worker''s consent must be recorded before collection.', errcode = '42501';
  end if;
  new.consent_id := v_consent.id;
  new.worker_consent_at := v_consent.accepted_at;

  new.kit_lot_number := btrim(coalesce(new.kit_lot_number, ''));
  if new.kit_lot_number = '' then
    raise exception 'KIT_LOT_REQUIRED' using errcode = '22023';
  end if;
  new.evidence_path := regexp_replace(btrim(coalesce(new.evidence_path, '')), '^/?drug-screen-evidence/', '');
  if new.evidence_path = '' then
    raise exception 'EVIDENCE_REQUIRED' using detail = 'A photo of the test device is required.', errcode = '22023';
  end if;
  if not exists (select 1 from storage.objects o
                  where o.bucket_id = 'drug-screen-evidence' and o.name = new.evidence_path) then
    raise exception 'EVIDENCE_NOT_FOUND'
      using detail = 'Upload the photo to the drug-screen-evidence bucket first.', errcode = '22023';
  end if;

  new.created_at := now();
  return new;
end $$;

create function private.drug_screen_after() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_prev text;
begin
  v_prev := private.enter_internal();
  if new.result = 'negative' then
    update public.worker_compliance
       set drug_screen_status = 'passed', drug_screen_date = new.collected_at
     where user_id = new.worker_id;
  elsif new.result = 'non_negative' then
    -- Rapid oral fluid is presumptive: pending lab confirmation, not failed.
    update public.worker_compliance
       set drug_screen_status = case when new.screen_type = 'lab_confirmation' then 'failed' else 'pending' end,
           drug_screen_date = new.collected_at
     where user_id = new.worker_id;
  end if;
  -- 'invalid' changes nothing: the screen must be recollected.
  perform private.exit_internal(v_prev);

  if new.screen_type = 'rapid_oral_fluid' then
    insert into public.treasury_allocations (source_type, source_id, bucket, amount_cents, note)
    values ('drug_screen', new.id, 'drug_screen', public.config_int('drug_screen_kit_cost_cents'), 'platform-paid screening kit');
  end if;

  if new.result = 'non_negative' and new.screen_type = 'rapid_oral_fluid' then
    perform private.notify(new.worker_id, 'compliance.drug_screen_pending', 'Your screen is going to a lab',
      'Rapid screens sometimes need lab confirmation. This is not a final result, and your status stays pending until the lab reports.',
      '/shifts', jsonb_build_object('drug_screen_log_id', new.id));
  elsif new.result = 'invalid' then
    perform private.notify(new.worker_id, 'compliance.drug_screen_retest', 'We need to redo your screen',
      'The test device didn''t give a readable result. We''ll schedule a quick retest at no cost to you.',
      '/shifts', jsonb_build_object('drug_screen_log_id', new.id));
  end if;

  insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
  values (new.collector_id, 'drug_screen.recorded', 'drug_screen_logs', new.id,
          jsonb_build_object('worker_id', new.worker_id, 'result', new.result, 'screen_type', new.screen_type));
  perform private.refresh_worker_tier(new.worker_id);
  return null;
end $$;

create trigger t10_guard before insert on public.drug_screen_logs
  for each row execute function private.drug_screen_guard();
create trigger t10_append_only before update or delete on public.drug_screen_logs
  for each row execute function private.forbid_mutation();
create trigger t11_append_only_truncate before truncate on public.drug_screen_logs
  for each statement execute function private.forbid_mutation();
create trigger t50_after after insert on public.drug_screen_logs
  for each row execute function private.drug_screen_after();

-- -----------------------------------------------------------------------------
-- Payouts
-- -----------------------------------------------------------------------------

create function private.payouts_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'APPEND_ONLY' using detail = 'Payouts are financial records.', errcode = '55000';
  end if;
  if new.shift_id is distinct from old.shift_id or new.worker_id is distinct from old.worker_id
     or new.total_billed_cents is distinct from old.total_billed_cents
     or new.total_paid_to_worker_cents is distinct from old.total_paid_to_worker_cents
     or new.agency_margin_cents is distinct from old.agency_margin_cents
     or new.created_at is distinct from old.created_at then
    raise exception 'FORBIDDEN_COLUMN' using detail = 'Payout amounts are fixed at approval.', errcode = '42501';
  end if;
  if new.destination is distinct from old.destination and old.status <> 'pending' then
    raise exception 'FORBIDDEN_COLUMN' using detail = 'Destination can only change before payment.', errcode = '42501';
  end if;
  if new.status is distinct from old.status then
    if not ((old.status = 'pending' and new.status in ('paid', 'failed')) or (old.status = 'failed' and new.status = 'pending')) then
      raise exception 'INVALID_STATUS_TRANSITION'
        using detail = format('%s -> %s is not allowed.', old.status, new.status), errcode = '22023';
    end if;
    if new.status = 'paid' then
      new.paid_at := now();
      new.failure_reason := null;
    end if;
  end if;
  return new;
end $$;

create function private.payouts_after() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_wallet uuid;
  v_title text;
begin
  if new.status = 'paid' and (tg_op = 'INSERT' or old.status is distinct from 'paid') then
    select s.position_title into v_title from public.shifts s where s.id = new.shift_id;
    if new.destination = 'ezwerkz_wallet' then
      select w.id into v_wallet from public.wallets w where w.user_id = new.worker_id;
      if v_wallet is null then
        insert into public.wallets (user_id) values (new.worker_id) returning id into v_wallet;
      end if;
      -- Idempotent on (payout, credit, shift_earnings).
      perform private.post_ledger_entry(v_wallet, 'credit', new.total_paid_to_worker_cents, 'shift_earnings',
                                        'Shift pay: ' || coalesce(v_title, 'shift'), 'payout', new.id);
    end if;
    if new.agency_margin_cents > 0 then
      insert into public.treasury_allocations (source_type, source_id, bucket, amount_cents, note)
      values ('payout', new.id, 'platform', new.agency_margin_cents, 'shift margin');
    end if;
    perform private.notify(new.worker_id, 'payout.paid', 'You got paid',
      private.fmt_cents(new.total_paid_to_worker_cents) || ' for ' || coalesce(v_title, 'your shift')
        || case when new.destination = 'ezwerkz_wallet' then ' is in your EzWerkz Wallet.' else ' is on its way to your bank.' end,
      case when new.destination = 'ezwerkz_wallet' then '/wallet' else '/shifts' end,
      jsonb_build_object('payout_id', new.id));
  end if;
  return null;
end $$;

create trigger t10_guard before update or delete on public.payouts
  for each row execute function private.payouts_guard();
create trigger t50_after after insert or update of status on public.payouts
  for each row execute function private.payouts_after();
create trigger t90_touch before update on public.payouts
  for each row execute function private.set_updated_at();

-- -----------------------------------------------------------------------------
-- MSA signatures (immutable)
-- -----------------------------------------------------------------------------

create function private.contract_signatures_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  v_expected text;
begin
  if current_user in ('anon', 'authenticated') then
    new.signer_id := auth.uid();
    new.signed_at := now();
    if new.company_id is distinct from public.user_org_id() or not public.current_role_is('client_manager') then
      raise exception 'FORBIDDEN' using detail = 'Only a manager of the company can sign for it.', errcode = '42501';
    end if;
  end if;
  new.section8_initials := upper(btrim(new.section8_initials));
  select v.document_sha256 into v_expected from public.msa_versions v where v.version = new.msa_version;
  if v_expected is not null and v_expected <> new.document_sha256 then
    raise exception 'MSA_HASH_MISMATCH'
      using detail = 'The signed text does not match the published MSA version.', errcode = '22023';
  end if;
  new.created_at := now();
  return new;
end $$;

create function private.contract_signatures_after() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.audit_log (actor_id, action, entity_type, entity_id, details, ip_address)
  values (new.signer_id, 'msa.signed', 'contract_signatures', new.id,
          jsonb_build_object('company_id', new.company_id, 'msa_version', new.msa_version,
                             'section8_acknowledged', new.section8_acknowledged, 'document_sha256', new.document_sha256),
          new.ip_address);
  return null;
end $$;

create trigger t10_guard before insert on public.contract_signatures
  for each row execute function private.contract_signatures_guard();
create trigger t10_append_only before update or delete on public.contract_signatures
  for each row execute function private.forbid_mutation();
create trigger t11_append_only_truncate before truncate on public.contract_signatures
  for each statement execute function private.forbid_mutation();
create trigger t50_after after insert on public.contract_signatures
  for each row execute function private.contract_signatures_after();

-- -----------------------------------------------------------------------------
-- Chat + poach flags
-- -----------------------------------------------------------------------------

-- Backstop for messages that reach the database without passing the app's
-- poach filter (e.g. direct API calls): hide contact details and flag.
create function private.chat_messages_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  v_redacted text;
begin
  if current_user in ('anon', 'authenticated') then
    new.sender_id := auth.uid();
    new.created_at := now();
    select u.role into new.sender_role from public.users u where u.id = auth.uid();
  elsif new.sender_role is null then
    select u.role into new.sender_role from public.users u where u.id = new.sender_id;
  end if;

  v_redacted := regexp_replace(new.body, '(\+?1[\s.-]?)?\(?[0-9]{3}\)?[\s.-]?[0-9]{3}[\s.-]?[0-9]{4}', '[contact info hidden]', 'g');
  v_redacted := regexp_replace(v_redacted, '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', '[contact info hidden]', 'g');
  if v_redacted <> new.body then
    new.body := v_redacted;
    new.flagged := true;
    perform set_config('ezwerkz.chat_backstop', new.id::text, true);
  end if;
  return new;
end $$;

create function private.chat_messages_after() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if coalesce(current_setting('ezwerkz.chat_backstop', true), '') = new.id::text then
    perform set_config('ezwerkz.chat_backstop', '', true);
    insert into public.poach_flags (message_id, thread_id, sender_id, matched_rules, severity, excerpt)
    values (new.id, new.thread_id, new.sender_id, array['contact_info_db_backstop'], 'high', left(new.body, 500));
  end if;
  return null;
end $$;

create trigger t10_guard before insert on public.chat_messages
  for each row execute function private.chat_messages_guard();
create trigger t50_after after insert on public.chat_messages
  for each row execute function private.chat_messages_after();

create function private.poach_flags_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if current_user in ('anon', 'authenticated') and not public.is_admin() then
      new.status := 'open';
      new.reviewed_by := null;
      new.reviewed_at := null;
      new.resolution_notes := null;
    end if;
    return new;
  end if;
  if new.message_id is distinct from old.message_id or new.thread_id is distinct from old.thread_id
     or new.sender_id is distinct from old.sender_id or new.matched_rules is distinct from old.matched_rules
     or new.severity is distinct from old.severity or new.excerpt is distinct from old.excerpt then
    raise exception 'FORBIDDEN_COLUMN' using errcode = '42501';
  end if;
  if new.status is distinct from old.status then
    new.reviewed_by := coalesce(auth.uid(), new.reviewed_by);
    new.reviewed_at := now();
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update on public.poach_flags
  for each row execute function private.poach_flags_guard();
create trigger t90_touch before update on public.poach_flags
  for each row execute function private.set_updated_at();

-- -----------------------------------------------------------------------------
-- RPCs
-- -----------------------------------------------------------------------------

-- Returns phone numbers, so it is limited to the service role (dispatch code
-- running server-side) and admins. Managers never see worker phone numbers.
create function public.workers_within_radius(p_shift_id uuid, p_miles numeric default 15)
returns table (user_id uuid, full_name text, phone_e164 text, distance_miles numeric)
language plpgsql stable security definer set search_path = public, extensions as $$
#variable_conflict use_column
declare
  v_shift public.shifts%rowtype;
begin
  if not (public.is_trusted_caller() or public.is_admin()) then
    raise exception 'FORBIDDEN' using detail = 'Call from server code with the service role.', errcode = '42501';
  end if;
  if p_miles is null or p_miles <= 0 or p_miles > 100 then
    raise exception 'INVALID_RADIUS' using errcode = '22023';
  end if;
  select * into v_shift from public.shifts s where s.id = p_shift_id;
  if not found then
    raise exception 'SHIFT_NOT_FOUND' using errcode = 'P0002';
  end if;

  return query
    select u.id, u.full_name, u.phone_e164,
           round((st_distance(u.home_geo, v_shift.geo) / 1609.344)::numeric, 2)
      from public.users u
      join public.worker_compliance wc on wc.user_id = u.id
     where u.role = 'worker'
       and u.sms_opt_in and u.sms_opt_in_at is not null
       and u.phone_e164 is not null
       and u.home_geo is not null
       and wc.compliance_tier >= v_shift.tier_required
       and wc.background_check_status <> 'failed'
       and st_dwithin(u.home_geo, v_shift.geo, (p_miles * 1609.344)::double precision)
     order by st_distance(u.home_geo, v_shift.geo), u.id;
end $$;

create function public.create_dispatches(p_shift_id uuid, p_miles numeric default 15)
returns table (dispatch_id uuid, user_id uuid, phone_e164 text, claim_code text)
language plpgsql volatile security definer set search_path = public, extensions as $$
#variable_conflict use_column
declare
  v_shift public.shifts%rowtype;
  v_ttl integer := public.config_int('sms_ttl_minutes');
  v_worker record;
  v_code text;
  v_attempts integer;
  v_id uuid;
begin
  if not (public.is_trusted_caller() or public.is_admin()) then
    raise exception 'FORBIDDEN' using detail = 'Call from server code with the service role.', errcode = '42501';
  end if;
  select * into v_shift from public.shifts s where s.id = p_shift_id;
  if not found then
    raise exception 'SHIFT_NOT_FOUND' using errcode = 'P0002';
  end if;
  if v_shift.status <> 'open' then
    raise exception 'SHIFT_NOT_OPEN' using errcode = '22023';
  end if;

  -- Serialize code generation so two dispatch runs can't pick the same code.
  perform pg_advisory_xact_lock(hashtext('ezwerkz.claim_codes'));
  update public.shift_dispatches d set outcome = 'expired'
   where d.outcome is null and d.expires_at <= now();

  for v_worker in
    select w.user_id, w.phone_e164
      from public.workers_within_radius(p_shift_id, p_miles) w
     where not exists (select 1 from public.shift_dispatches d where d.shift_id = p_shift_id and d.user_id = w.user_id)
  loop
    v_attempts := 0;
    loop
      v_code := lpad((floor(random() * 10000))::integer::text, 4, '0');
      exit when not exists (select 1 from public.shift_dispatches d where d.claim_code = v_code and d.outcome is null);
      v_attempts := v_attempts + 1;
      if v_attempts > 500 then
        raise exception 'CLAIM_CODE_SPACE_EXHAUSTED' using errcode = '53000';
      end if;
    end loop;

    insert into public.shift_dispatches (shift_id, user_id, phone_e164, claim_code, expires_at)
    values (p_shift_id, v_worker.user_id, v_worker.phone_e164, v_code, now() + make_interval(mins => v_ttl))
    returning id into v_id;

    dispatch_id := v_id;
    user_id := v_worker.user_id;
    phone_e164 := v_worker.phone_e164;
    claim_code := v_code;
    return next;
  end loop;
end $$;

-- Race-safe: the single UPDATE ... WHERE status = 'open' is the arbiter.
-- Returns false when the shift is no longer open (someone else won).
-- Raises TIER_REQUIRED / NOT_A_WORKER / NOT_ELIGIBLE / SCHEDULE_CONFLICT /
-- SHIFT_NOT_FOUND / FORBIDDEN.
create function public.claim_shift(p_shift_id uuid, p_worker_id uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
declare
  v_role text;
  v_tier smallint;
  v_bg text;
  v_shift public.shifts%rowtype;
  v_claimed uuid;
  v_prev text;
begin
  if p_shift_id is null or p_worker_id is null then
    raise exception 'INVALID_ARGUMENT' using errcode = '22023';
  end if;
  if not (public.is_trusted_caller() or public.is_admin() or auth.uid() = p_worker_id) then
    raise exception 'FORBIDDEN' using errcode = '42501';
  end if;

  select u.role, coalesce(wc.compliance_tier, 0), wc.background_check_status
    into v_role, v_tier, v_bg
    from public.users u
    left join public.worker_compliance wc on wc.user_id = u.id
   where u.id = p_worker_id;
  if v_role is distinct from 'worker' then
    raise exception 'NOT_A_WORKER' using errcode = '42501';
  end if;
  if v_bg = 'failed' then
    raise exception 'NOT_ELIGIBLE' using errcode = '42501';
  end if;

  select * into v_shift from public.shifts where id = p_shift_id;
  if not found then
    raise exception 'SHIFT_NOT_FOUND' using errcode = 'P0002';
  end if;
  if v_shift.tier_required > v_tier then
    raise exception 'TIER_REQUIRED'
      using detail = format('This shift needs Tier %s.', v_shift.tier_required), errcode = '42501';
  end if;
  if v_shift.status <> 'open' or v_shift.scheduled_end <= now() then
    return false;
  end if;
  if exists (
    select 1 from public.shifts s
     where s.claimed_by = p_worker_id and s.status in ('claimed', 'in_progress') and s.id <> p_shift_id
       and tstzrange(s.scheduled_start, s.scheduled_end) && tstzrange(v_shift.scheduled_start, v_shift.scheduled_end)) then
    raise exception 'SCHEDULE_CONFLICT' using detail = 'You already have a shift at that time.', errcode = '22023';
  end if;

  v_prev := private.enter_internal();
  update public.shifts
     set status = 'claimed', claimed_by = p_worker_id, claimed_at = now()
   where id = p_shift_id and status = 'open' and claimed_by is null
     and tier_required <= v_tier and scheduled_end > now()
  returning id into v_claimed;
  perform private.exit_internal(v_prev);

  if v_claimed is null then
    return false;
  end if;
  insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
  values (coalesce(auth.uid(), p_worker_id), 'shift.claimed', 'shifts', p_shift_id, jsonb_build_object('worker_id', p_worker_id));
  return true;
end $$;

-- Twilio inbound (service role). Returns the shift id on success, else null.
create function public.claim_shift_by_code(p_phone text, p_code text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_phone text := regexp_replace(coalesce(p_phone, ''), '[^0-9+]', '', 'g');
  v_code text := regexp_replace(coalesce(p_code, ''), '[^0-9]', '', 'g');
  v_dispatch public.shift_dispatches%rowtype;
  v_ok boolean;
begin
  if not public.is_trusted_caller() then
    raise exception 'FORBIDDEN' using errcode = '42501';
  end if;
  if v_code !~ '^[0-9]{4}$' or v_phone !~ '^\+[1-9][0-9]{6,14}$' then
    return null;
  end if;

  update public.shift_dispatches set outcome = 'expired'
   where outcome is null and expires_at <= now() and claim_code = v_code;

  select d.* into v_dispatch
    from public.shift_dispatches d
    join public.users u on u.id = d.user_id
   where u.phone_e164 = v_phone and u.sms_opt_in
     and d.claim_code = v_code and d.outcome is null and d.expires_at > now()
   for update of d;
  if not found then
    return null;
  end if;

  begin
    v_ok := public.claim_shift(v_dispatch.shift_id, v_dispatch.user_id);
  exception when others then
    update public.shift_dispatches set outcome = 'ineligible', responded_at = now() where id = v_dispatch.id;
    return null;
  end;

  if v_ok then
    return v_dispatch.shift_id;
  end if;
  update public.shift_dispatches set outcome = 'shift_filled', responded_at = now()
   where id = v_dispatch.id and outcome is null;
  return null;
end $$;

-- Manager approval: totals = rate x hours, hours rounded to the nearest quarter
-- hour exactly like quoteShift() in src/lib/pricing.ts.
create function public.approve_shift(p_shift_id uuid, p_rating integer, p_on_time boolean) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := auth.uid();
  v_shift public.shifts%rowtype;
  v_wc public.worker_compliance%rowtype;
  v_hours numeric;
  v_billed bigint;
  v_paid bigint;
  v_dest text;
  v_payout uuid;
  v_prev text;
begin
  if v_uid is null then
    raise exception 'AUTH_REQUIRED' using errcode = '42501';
  end if;
  if p_rating is null or p_rating not between 1 and 5 then
    raise exception 'INVALID_RATING' using errcode = '22023';
  end if;
  if p_on_time is null then
    raise exception 'INVALID_ARGUMENT' using errcode = '22023';
  end if;

  select * into v_shift from public.shifts where id = p_shift_id for update;
  if not found then
    raise exception 'SHIFT_NOT_FOUND' using errcode = 'P0002';
  end if;
  -- Approval triggers the client charge, so only the client's own manager may approve.
  if not (public.current_role_is('client_manager') and v_shift.organization_id = public.user_org_id()) then
    raise exception 'FORBIDDEN' using detail = 'Only the shift''s client manager can approve it.', errcode = '42501';
  end if;
  if v_shift.status = 'approved' then
    raise exception 'ALREADY_APPROVED' using errcode = '22023';
  end if;
  if v_shift.status not in ('claimed', 'in_progress', 'completed') or v_shift.claimed_by is null then
    raise exception 'SHIFT_NOT_APPROVABLE' using errcode = '22023';
  end if;
  if v_shift.scheduled_start > now() then
    raise exception 'SHIFT_NOT_STARTED' using errcode = '22023';
  end if;

  v_hours := round(extract(epoch from (v_shift.scheduled_end - v_shift.scheduled_start)) / 3600 * 4) / 4;
  v_billed := round(v_shift.hourly_billing_rate_cents * v_hours)::bigint;
  v_paid := round(v_shift.hourly_pay_rate_cents * v_hours)::bigint;

  select * into v_wc from public.worker_compliance where user_id = v_shift.claimed_by for update;
  if not found then
    v_prev := private.enter_internal();
    insert into public.worker_compliance (user_id) values (v_shift.claimed_by) returning * into v_wc;
    perform private.exit_internal(v_prev);
  end if;
  v_dest := case when v_wc.payout_destination = 'stripe_connect' and v_wc.stripe_connect_account_id is not null
                 then 'stripe_connect' else 'ezwerkz_wallet' end;

  v_prev := private.enter_internal();
  update public.shifts
     set status = 'approved', approved_at = now(), completed_at = coalesce(completed_at, now()),
         started_at = coalesce(started_at, scheduled_start)
   where id = p_shift_id;

  insert into public.shift_ratings (shift_id, worker_id, rater_id, rating, on_time)
  values (p_shift_id, v_shift.claimed_by, v_uid, p_rating, p_on_time);

  insert into public.payouts (shift_id, worker_id, total_billed_cents, total_paid_to_worker_cents, agency_margin_cents, destination)
  values (p_shift_id, v_shift.claimed_by, v_billed, v_paid, v_billed - v_paid, v_dest)
  returning id into v_payout;

  update public.worker_compliance
     set completed_shifts = completed_shifts + 1,
         on_time_shifts = on_time_shifts + case when p_on_time then 1 else 0 end,
         rating_average = (select round(avg(r.rating)::numeric, 2) from public.shift_ratings r where r.worker_id = v_shift.claimed_by)
   where user_id = v_shift.claimed_by;
  perform private.exit_internal(v_prev);

  perform private.evaluate_tier2(v_shift.claimed_by);
  perform private.notify(v_shift.claimed_by, 'shift.approved', 'Shift approved',
    'Your ' || v_shift.position_title || ' shift was approved. ' || private.fmt_cents(v_paid) || ' is on the way.',
    '/shifts/' || p_shift_id, jsonb_build_object('shift_id', p_shift_id, 'payout_id', v_payout));
  insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
  values (v_uid, 'shift.approved', 'shifts', p_shift_id,
          jsonb_build_object('payout_id', v_payout, 'hours', v_hours, 'billed_cents', v_billed,
                             'paid_cents', v_paid, 'rating', p_rating, 'on_time', p_on_time));
  return v_payout;
end $$;

create function public.evaluate_tier2_eligibility(p_worker_id uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
  if not (public.is_trusted_caller() or public.is_admin() or auth.uid() = p_worker_id) then
    raise exception 'FORBIDDEN' using errcode = '42501';
  end if;
  return private.evaluate_tier2(p_worker_id);
end $$;

create function public.record_drug_screen(
  p_worker_id uuid,
  p_kit_lot text,
  p_result text,
  p_evidence_path text,
  p_collected_at timestamptz,
  p_notes text default null
) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := auth.uid();
  v_id uuid;
begin
  if v_uid is null or not public.is_admin() then
    raise exception 'FORBIDDEN' using detail = 'Only an admin collector can record a screen.', errcode = '42501';
  end if;
  if p_worker_id = v_uid then
    raise exception 'COLLECTOR_IS_WORKER' using errcode = '42501';
  end if;
  if p_result is null or p_result not in ('negative', 'non_negative', 'invalid') then
    raise exception 'INVALID_RESULT' using errcode = '22023';
  end if;
  if p_evidence_path is null or btrim(p_evidence_path) = '' then
    raise exception 'EVIDENCE_REQUIRED' using errcode = '22023';
  end if;
  if p_kit_lot is null or btrim(p_kit_lot) = '' then
    raise exception 'KIT_LOT_REQUIRED' using errcode = '22023';
  end if;

  insert into public.drug_screen_logs (worker_id, collector_id, collected_at, kit_lot_number, result, screen_type, evidence_path, notes)
  values (p_worker_id, v_uid, coalesce(p_collected_at, now()), p_kit_lot, p_result, 'rapid_oral_fluid',
          p_evidence_path, nullif(btrim(coalesce(p_notes, '')), ''))
  returning id into v_id;
  return v_id;
end $$;

-- Admin or service role (after the provider accepts the order).
create function public.order_background_check(
  p_worker_id uuid,
  p_provider_candidate_id text default null,
  p_provider_report_id text default null,
  p_package text default null
) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_id uuid;
begin
  if not (public.is_trusted_caller() or public.is_admin()) then
    raise exception 'FORBIDDEN' using errcode = '42501';
  end if;
  select b.id into v_id from public.background_checks b
   where b.worker_id = p_worker_id and b.status in ('ordered', 'pending');
  if found then
    return v_id;
  end if;
  insert into public.background_checks (worker_id, provider_candidate_id, provider_report_id, package, status, ordered_by)
  values (p_worker_id, p_provider_candidate_id, p_provider_report_id, p_package,
          case when p_provider_report_id is null then 'ordered' else 'pending' end, auth.uid())
  returning id into v_id;
  insert into public.audit_log (actor_id, action, entity_type, entity_id, details)
  values (auth.uid(), 'background_check.ordered', 'background_checks', v_id, jsonb_build_object('worker_id', p_worker_id));
  return v_id;
end $$;

-- Provider webhook (service role): status only. Adjudication stays human.
create function public.record_background_check_result(p_provider_report_id text, p_status text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_id uuid;
begin
  if not (public.is_trusted_caller() or public.is_admin()) then
    raise exception 'FORBIDDEN' using errcode = '42501';
  end if;
  if p_status is null or p_status not in ('pending', 'clear', 'consider', 'suspended', 'canceled', 'error') then
    raise exception 'INVALID_STATUS' using errcode = '22023';
  end if;
  update public.background_checks set status = p_status
   where provider_report_id = p_provider_report_id
  returning id into v_id;
  if v_id is null then
    raise exception 'BACKGROUND_CHECK_NOT_FOUND' using errcode = 'P0002';
  end if;
  return v_id;
end $$;

-- Admin decision on the worker's latest 'consider' report.
-- p_decision: 'clear' | 'pre_adverse' | 'final_adverse'. Returns the worker's
-- resulting background_check_status.
create function public.review_background_check(p_worker_id uuid, p_decision text) returns text
language plpgsql security definer set search_path = '' as $$
declare
  v_check public.background_checks%rowtype;
  v_target text;
  v_status text;
begin
  if not public.is_admin() then
    raise exception 'FORBIDDEN' using errcode = '42501';
  end if;
  v_target := case p_decision
    when 'clear' then 'cleared'
    when 'pre_adverse' then 'pre_adverse_sent'
    when 'final_adverse' then 'final_adverse_sent'
  end;
  if v_target is null then
    raise exception 'INVALID_DECISION' using errcode = '22023';
  end if;
  select * into v_check from public.background_checks
   where worker_id = p_worker_id and status = 'consider'
   order by ordered_at desc limit 1
   for update;
  if not found then
    raise exception 'NO_REPORT_TO_REVIEW' using errcode = 'P0002';
  end if;
  update public.background_checks set adjudication = v_target, reviewed_by = auth.uid() where id = v_check.id;
  select wc.background_check_status into v_status from public.worker_compliance wc where wc.user_id = p_worker_id;
  return v_status;
end $$;

-- A signed-in user enters a module door. Entering "shifts" as a member makes
-- them a worker (Tier 1) with a compliance record.
create function public.enroll_module(p_module text) returns text
language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := auth.uid();
  v_role text;
begin
  if v_uid is null then
    raise exception 'AUTH_REQUIRED' using errcode = '42501';
  end if;
  if p_module is null or p_module not in ('credit', 'wallet', 'shifts') then
    raise exception 'INVALID_MODULE' using errcode = '22023';
  end if;
  insert into public.user_modules (user_id, module) values (v_uid, p_module) on conflict (user_id, module) do nothing;
  select u.role into v_role from public.users u where u.id = v_uid;
  if p_module = 'shifts' and v_role = 'member' then
    update public.users set role = 'worker' where id = v_uid;
    v_role := 'worker';
  end if;
  return v_role;
end $$;

-- Self-serve business sign-up: creates the organization and makes the caller
-- its client manager. Posting still requires the MSA signature.
create function public.register_business(p_name text, p_billing_email text default null) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := auth.uid();
  v_user public.users%rowtype;
  v_org uuid;
begin
  if v_uid is null then
    raise exception 'AUTH_REQUIRED' using errcode = '42501';
  end if;
  select * into v_user from public.users where id = v_uid for update;
  if v_user.organization_id is not null then
    raise exception 'ALREADY_IN_ORGANIZATION' using errcode = '22023';
  end if;
  if v_user.role <> 'member' then
    raise exception 'ROLE_NOT_ELIGIBLE' using detail = 'Workers and admins cannot register a client company.', errcode = '42501';
  end if;
  insert into public.organizations (name, billing_email)
  values (btrim(p_name), coalesce(nullif(btrim(p_billing_email), ''), v_user.email))
  returning id into v_org;
  update public.users set role = 'client_manager', organization_id = v_org where id = v_uid;
  return v_org;
end $$;

revoke execute on function
  public.workers_within_radius(uuid, numeric),
  public.create_dispatches(uuid, numeric),
  public.claim_shift(uuid, uuid),
  public.claim_shift_by_code(text, text),
  public.approve_shift(uuid, integer, boolean),
  public.evaluate_tier2_eligibility(uuid),
  public.record_drug_screen(uuid, text, text, text, timestamptz, text),
  public.order_background_check(uuid, text, text, text),
  public.record_background_check_result(text, text),
  public.review_background_check(uuid, text),
  public.enroll_module(text),
  public.register_business(text, text),
  public.worker_tier(),
  public.has_signed_msa(uuid),
  public.is_thread_participant(uuid)
from public, anon;
grant execute on function
  public.workers_within_radius(uuid, numeric),
  public.create_dispatches(uuid, numeric),
  public.claim_shift(uuid, uuid),
  public.approve_shift(uuid, integer, boolean),
  public.evaluate_tier2_eligibility(uuid),
  public.record_drug_screen(uuid, text, text, text, timestamptz, text),
  public.order_background_check(uuid, text, text, text),
  public.record_background_check_result(text, text),
  public.review_background_check(uuid, text),
  public.enroll_module(text),
  public.register_business(text, text),
  public.worker_tier(),
  public.has_signed_msa(uuid),
  public.is_thread_participant(uuid)
to authenticated, service_role;
-- SMS claim is a webhook-only path (Supabase's default privileges grant
-- authenticated EXECUTE on new functions, so revoke it explicitly).
revoke execute on function public.claim_shift_by_code(text, text) from authenticated;
grant execute on function public.claim_shift_by_code(text, text) to service_role;

-- -----------------------------------------------------------------------------
-- RLS
-- -----------------------------------------------------------------------------

alter table public.msa_versions enable row level security;
alter table public.client_locations enable row level security;
alter table public.shifts enable row level security;
alter table public.shift_dispatches enable row level security;
alter table public.worker_compliance enable row level security;
alter table public.background_checks enable row level security;
alter table public.drug_screen_logs enable row level security;
alter table public.shift_ratings enable row level security;
alter table public.payouts enable row level security;
alter table public.contract_signatures enable row level security;
alter table public.chat_threads enable row level security;
alter table public.chat_messages enable row level security;
alter table public.poach_flags enable row level security;

-- Workers can see the company behind shifts they can see.
create policy organizations_select_worker on public.organizations for select to authenticated
  using (exists (
    select 1 from public.shifts s
     where s.organization_id = organizations.id
       and (s.claimed_by = (select auth.uid())
            or (s.status = 'open' and s.tier_required <= (select public.worker_tier())))));

create policy msa_versions_select_all on public.msa_versions for select to authenticated
  using (true);
create policy msa_versions_insert_admin on public.msa_versions for insert to authenticated
  with check ((select public.is_admin()));
create policy msa_versions_update_admin on public.msa_versions for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

create policy client_locations_manager on public.client_locations for all to authenticated
  using (organization_id = (select public.user_org_id()) and (select public.current_role_is('client_manager')))
  with check (organization_id = (select public.user_org_id()) and (select public.current_role_is('client_manager')));
create policy client_locations_admin on public.client_locations for all to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

-- shifts: open shifts for the worker's tier + their own; the org's shifts for managers; all for admins.
create policy shifts_select_worker on public.shifts for select to authenticated
  using (claimed_by = (select auth.uid())
         or (status = 'open' and tier_required <= (select public.worker_tier())));
create policy shifts_select_manager on public.shifts for select to authenticated
  using (organization_id = (select public.user_org_id()) and (select public.current_role_is('client_manager')));
create policy shifts_select_admin on public.shifts for select to authenticated
  using ((select public.is_admin()));
create policy shifts_insert_manager on public.shifts for insert to authenticated
  with check (organization_id = (select public.user_org_id())
              and client_id = (select auth.uid())
              and (select public.current_role_is('client_manager')));
create policy shifts_update_manager on public.shifts for update to authenticated
  using (organization_id = (select public.user_org_id()) and (select public.current_role_is('client_manager')))
  with check (organization_id = (select public.user_org_id()) and (select public.current_role_is('client_manager')));
create policy shifts_update_worker on public.shifts for update to authenticated
  using (claimed_by = (select auth.uid()))
  with check (claimed_by = (select auth.uid()) or (claimed_by is null and status = 'open'));
create policy shifts_update_admin on public.shifts for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

create policy shift_dispatches_select_self on public.shift_dispatches for select to authenticated
  using (user_id = (select auth.uid()));
create policy shift_dispatches_select_admin on public.shift_dispatches for select to authenticated
  using ((select public.is_admin()));

create policy worker_compliance_select_self on public.worker_compliance for select to authenticated
  using (user_id = (select auth.uid()));
create policy worker_compliance_update_self on public.worker_compliance for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy worker_compliance_select_admin on public.worker_compliance for select to authenticated
  using ((select public.is_admin()));
create policy worker_compliance_insert_admin on public.worker_compliance for insert to authenticated
  with check ((select public.is_admin()));
create policy worker_compliance_update_admin on public.worker_compliance for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

create policy background_checks_select_self on public.background_checks for select to authenticated
  using (worker_id = (select auth.uid()));
create policy background_checks_select_admin on public.background_checks for select to authenticated
  using ((select public.is_admin()));
create policy background_checks_insert_admin on public.background_checks for insert to authenticated
  with check ((select public.is_admin()));
create policy background_checks_update_admin on public.background_checks for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

create policy drug_screen_logs_select_self on public.drug_screen_logs for select to authenticated
  using (worker_id = (select auth.uid()));
create policy drug_screen_logs_select_admin on public.drug_screen_logs for select to authenticated
  using ((select public.is_admin()));
create policy drug_screen_logs_insert_admin on public.drug_screen_logs for insert to authenticated
  with check ((select public.is_admin()) and collector_id = (select auth.uid()));

create policy shift_ratings_select_worker on public.shift_ratings for select to authenticated
  using (worker_id = (select auth.uid()));
create policy shift_ratings_select_manager on public.shift_ratings for select to authenticated
  using ((select public.current_role_is('client_manager'))
         and exists (select 1 from public.shifts s where s.id = shift_id and s.organization_id = (select public.user_org_id())));
create policy shift_ratings_select_admin on public.shift_ratings for select to authenticated
  using ((select public.is_admin()));

create policy payouts_select_self on public.payouts for select to authenticated
  using (worker_id = (select auth.uid()));
create policy payouts_select_admin on public.payouts for select to authenticated
  using ((select public.is_admin()));
create policy payouts_update_admin on public.payouts for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

create policy contract_signatures_select_manager on public.contract_signatures for select to authenticated
  using (company_id = (select public.user_org_id()) and (select public.current_role_is('client_manager')));
create policy contract_signatures_select_admin on public.contract_signatures for select to authenticated
  using ((select public.is_admin()));
create policy contract_signatures_insert_manager on public.contract_signatures for insert to authenticated
  with check (company_id = (select public.user_org_id())
              and signer_id = (select auth.uid())
              and (select public.current_role_is('client_manager')));

create policy chat_threads_select_party on public.chat_threads for select to authenticated
  using (worker_id = (select auth.uid())
         or (organization_id = (select public.user_org_id()) and (select public.current_role_is('client_manager'))));
create policy chat_threads_select_admin on public.chat_threads for select to authenticated
  using ((select public.is_admin()));

create policy chat_messages_select_party on public.chat_messages for select to authenticated
  using ((select public.is_thread_participant(thread_id)));
create policy chat_messages_select_admin on public.chat_messages for select to authenticated
  using ((select public.is_admin()));
create policy chat_messages_insert_party on public.chat_messages for insert to authenticated
  with check (sender_id = (select auth.uid()) and (select public.is_thread_participant(thread_id)));

create policy poach_flags_select_admin on public.poach_flags for select to authenticated
  using ((select public.is_admin()));
create policy poach_flags_update_admin on public.poach_flags for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));
create policy poach_flags_insert_sender on public.poach_flags for insert to authenticated
  with check (sender_id = (select auth.uid())
              and exists (select 1 from public.chat_messages m
                           where m.id = message_id and m.sender_id = (select auth.uid()) and m.thread_id = poach_flags.thread_id));
create policy poach_flags_insert_admin on public.poach_flags for insert to authenticated
  with check ((select public.is_admin()));

-- -----------------------------------------------------------------------------
-- Realtime: live shift feed + chat (RLS still applies to subscribers).
-- -----------------------------------------------------------------------------

do $$
begin
  if not exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    create publication supabase_realtime;
  end if;
  if not exists (select 1 from pg_publication_tables
                  where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'shifts') then
    alter publication supabase_realtime add table public.shifts;
  end if;
  if not exists (select 1 from pg_publication_tables
                  where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'chat_messages') then
    alter publication supabase_realtime add table public.chat_messages;
  end if;
end $$;

-- -----------------------------------------------------------------------------
-- Storage: private buckets
--   bill-uploads          owner-only, files under "<user id>/..."
--   drug-screen-evidence  admin-only; no update/delete (evidence is immutable)
-- -----------------------------------------------------------------------------

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('bill-uploads', 'bill-uploads', false, 10485760,
   array['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'application/pdf']),
  ('drug-screen-evidence', 'drug-screen-evidence', false, 10485760,
   array['image/jpeg', 'image/png', 'image/webp', 'image/heic'])
on conflict (id) do update set public = false;

create policy ezwerkz_bill_uploads_select on storage.objects for select to authenticated
  using (bucket_id = 'bill-uploads' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy ezwerkz_bill_uploads_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'bill-uploads' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy ezwerkz_bill_uploads_update on storage.objects for update to authenticated
  using (bucket_id = 'bill-uploads' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'bill-uploads' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy ezwerkz_bill_uploads_delete on storage.objects for delete to authenticated
  using (bucket_id = 'bill-uploads' and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy ezwerkz_drug_evidence_select on storage.objects for select to authenticated
  using (bucket_id = 'drug-screen-evidence' and (select public.is_admin()));
create policy ezwerkz_drug_evidence_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'drug-screen-evidence' and (select public.is_admin()));
