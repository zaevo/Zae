-- =============================================================================
-- 0005_leads.sql — Module D: lead engine (admin-only).
--   lead_sources, scrape_runs, lead_targets (dedupe_hash unique),
--   outreach_drafts, email_suppressions.
--
-- Compliance enforced here:
--   * Sources whose terms prohibit scraping (Indeed, ZipRecruiter, Craigslist)
--     can only be enabled with a licensed feed/API reference.
--   * Only business contact info published in the posting is stored.
--   * A draft can be approved/sent only by a human approver, must carry an
--     opt-out line (CAN-SPAM), and is auto-suppressed if the recipient or their
--     domain is on the suppression list.
-- =============================================================================

create table public.lead_sources (
  id uuid primary key default gen_random_uuid(),
  key text not null unique check (key ~ '^[a-z0-9_]+$'),
  name text not null check (length(btrim(name)) between 1 and 120),
  kind text not null check (kind in ('official_api', 'rss', 'jsonld_page', 'licensed_feed')),
  enabled boolean not null default false,
  requires_license boolean not null default false,
  license_reference text,
  base_url text check (base_url is null or base_url ~ '^https://'),
  user_agent text not null default 'EzWerkzLeadBot/1.0 (+https://ezwerkz.example/bot)',
  rate_limit_per_minute integer not null default 30 check (rate_limit_per_minute between 1 and 600),
  respects_robots_txt boolean not null default true,
  robots_checked_at timestamptz,
  config jsonb not null default '{}'::jsonb,
  notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint lead_sources_license_required check (not (enabled and requires_license and license_reference is null)),
  constraint lead_sources_robots check (respects_robots_txt or kind in ('official_api', 'licensed_feed'))
);
comment on table public.lead_sources is
  'Permitted sources only: official APIs, RSS, or pages whose robots.txt allows the path. No CAPTCHA/anti-bot evasion, no login-walled pages.';

create table public.scrape_runs (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.lead_sources (id) on delete cascade,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running' check (status in ('running', 'succeeded', 'partial', 'failed', 'skipped')),
  fetched_count integer not null default 0 check (fetched_count >= 0),
  new_leads_count integer not null default 0 check (new_leads_count >= 0),
  error text,
  created_at timestamptz not null default now()
);
create index scrape_runs_source_idx on public.scrape_runs (source_id, started_at desc);

create table public.lead_targets (
  id uuid primary key default gen_random_uuid(),
  source_id uuid references public.lead_sources (id) on delete set null,
  scrape_run_id uuid references public.scrape_runs (id) on delete set null,
  source text not null check (length(source) between 1 and 60),
  external_id text,
  company_name text not null check (length(btrim(company_name)) between 1 and 200),
  job_title text not null check (length(btrim(job_title)) between 1 and 200),
  location text not null default '',
  posted_at timestamptz,
  url text not null check (url ~ '^https?://'),
  urgency_keywords text[] not null default '{}',
  contact_email text check (contact_email is null or contact_email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  contact_source_url text,
  dedupe_hash text not null unique check (length(dedupe_hash) between 16 and 128),
  status text not null default 'new' check (status in ('new', 'drafted', 'contacted', 'ignored')),
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on column public.lead_targets.contact_email is 'Business contact published in the posting itself; never personal data from elsewhere.';
create index lead_targets_source_idx on public.lead_targets (source_id);
create index lead_targets_run_idx on public.lead_targets (scrape_run_id);
create index lead_targets_status_idx on public.lead_targets (status, created_at desc);

create table public.outreach_drafts (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references public.lead_targets (id) on delete cascade,
  to_email text check (to_email is null or to_email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  subject text not null check (length(btrim(subject)) between 1 and 200),
  body text not null check (length(btrim(body)) between 1 and 20000),
  status text not null default 'draft' check (status in ('draft', 'approved', 'sent', 'suppressed')),
  model text,
  approved_by uuid references public.users (id) on delete set null,
  approved_at timestamptz,
  sent_at timestamptz,
  provider_message_id text,
  suppressed_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index outreach_drafts_lead_idx on public.outreach_drafts (lead_id);
create index outreach_drafts_status_idx on public.outreach_drafts (status, created_at desc);
create index outreach_drafts_approver_idx on public.outreach_drafts (approved_by);

create table public.email_suppressions (
  id uuid primary key default gen_random_uuid(),
  email text check (email is null or email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  domain text check (domain is null or domain ~* '^[a-z0-9.-]+\.[a-z]{2,}$'),
  reason text not null check (reason in ('unsubscribe', 'bounce', 'complaint', 'manual')),
  created_at timestamptz not null default now(),
  constraint email_suppressions_target check (email is not null or domain is not null)
);
create unique index email_suppressions_email_key on public.email_suppressions (lower(email)) where email is not null;
create unique index email_suppressions_domain_key on public.email_suppressions (lower(domain)) where domain is not null;

-- -----------------------------------------------------------------------------
-- Guards
-- -----------------------------------------------------------------------------

-- Admins and trusted code only (the list itself is private).
create function public.is_email_suppressed(p_email text) returns boolean
language sql stable security definer set search_path = '' as $$
  select (public.is_admin() or public.is_trusted_caller())
     and p_email is not null and exists (
    select 1 from public.email_suppressions s
     where lower(s.email) = lower(btrim(p_email))
        or lower(s.domain) = lower(split_part(btrim(p_email), '@', 2)));
$$;

create function private.outreach_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  v_end_user boolean := current_user in ('anon', 'authenticated');
begin
  if tg_op = 'INSERT' then
    new.status := 'draft';
    new.approved_by := null;
    new.approved_at := null;
    new.sent_at := null;
    if new.to_email is null then
      select l.contact_email into new.to_email from public.lead_targets l where l.id = new.lead_id;
    end if;
    return new;
  end if;

  if new.status is distinct from old.status then
    if not ((old.status = 'draft' and new.status in ('approved', 'suppressed'))
         or (old.status = 'approved' and new.status in ('draft', 'sent', 'suppressed'))) then
      raise exception 'INVALID_STATUS_TRANSITION'
        using detail = format('%s -> %s is not allowed.', old.status, new.status), errcode = '22023';
    end if;

    -- Inline (not is_email_suppressed()) so the check runs with whoever is
    -- writing: admins and the service role can both read the list.
    if new.status in ('approved', 'sent') and new.to_email is not null and exists (
         select 1 from public.email_suppressions es
          where lower(es.email) = lower(btrim(new.to_email))
             or lower(es.domain) = lower(split_part(btrim(new.to_email), '@', 2))) then
      new.status := 'suppressed';
      new.suppressed_reason := 'Recipient or domain is on the suppression list.';
      return new;
    end if;

    if new.status = 'approved' then
      -- A person approves; the drafting job cannot.
      if v_end_user then
        if not public.is_admin() then
          raise exception 'FORBIDDEN' using errcode = '42501';
        end if;
        new.approved_by := auth.uid();
      elsif new.approved_by is null
            or not exists (select 1 from public.users u where u.id = new.approved_by and u.role = 'admin') then
        raise exception 'HUMAN_APPROVAL_REQUIRED' using errcode = '42501';
      end if;
      new.approved_at := now();
    elsif new.status = 'draft' then
      new.approved_by := null;
      new.approved_at := null;
    elsif new.status = 'sent' then
      if old.approved_by is null or old.approved_at is null then
        raise exception 'HUMAN_APPROVAL_REQUIRED' using errcode = '42501';
      end if;
      if new.to_email is null then
        raise exception 'RECIPIENT_REQUIRED' using errcode = '22023';
      end if;
      new.sent_at := now();
    end if;

    if new.status in ('approved', 'sent') and new.body !~* '(unsubscribe|opt[ -]?out)' then
      raise exception 'CAN_SPAM_FOOTER_REQUIRED'
        using detail = 'The email must include the physical address and an opt-out line.', errcode = '22023';
    end if;
  elsif old.status in ('approved', 'sent') and (new.subject is distinct from old.subject or new.body is distinct from old.body
                                               or new.to_email is distinct from old.to_email) then
    raise exception 'DRAFT_LOCKED' using detail = 'Move the draft back to draft status to edit it.', errcode = '22023';
  end if;
  return new;
end $$;

create trigger t10_guard before insert or update on public.outreach_drafts
  for each row execute function private.outreach_guard();
create trigger t90_touch before update on public.outreach_drafts
  for each row execute function private.set_updated_at();
create trigger t90_touch before update on public.lead_sources
  for each row execute function private.set_updated_at();
create trigger t90_touch before update on public.lead_targets
  for each row execute function private.set_updated_at();

revoke execute on function public.is_email_suppressed(text) from public, anon;
grant execute on function public.is_email_suppressed(text) to authenticated, service_role;

-- -----------------------------------------------------------------------------
-- RLS: admin-only. The scraper job uses the service role.
-- -----------------------------------------------------------------------------

alter table public.lead_sources enable row level security;
alter table public.scrape_runs enable row level security;
alter table public.lead_targets enable row level security;
alter table public.outreach_drafts enable row level security;
alter table public.email_suppressions enable row level security;

create policy lead_sources_admin on public.lead_sources for all to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));
create policy scrape_runs_admin on public.scrape_runs for all to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));
create policy lead_targets_admin on public.lead_targets for all to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));
create policy outreach_drafts_admin on public.outreach_drafts for all to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));
create policy email_suppressions_admin on public.email_suppressions for all to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));
