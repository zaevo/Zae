-- =============================================================================
-- seed.sql — reference + demo data for a fresh database (`supabase db reset`).
-- Idempotent: safe to run more than once. Contains no auth users; see
-- supabase/README.md for creating demo accounts and assigning roles.
-- =============================================================================

-- Demo client company. The id matches DEMO_USERS.client_manager.organizationId
-- in src/lib/auth.ts so demo and live data line up.
insert into public.organizations (id, name, kind, billing_email, phone_e164, address_line1, city, region, postal_code)
values ('00000000-0000-4000-8000-0000000000c1', 'Peach State Fuel & Go #1142', 'client_company',
        'store1142@example.com', '+14045550142', '1142 Ponce de Leon Ave NE', 'Atlanta', 'GA', '30306')
on conflict (id) do nothing;

insert into public.client_locations (id, organization_id, name, address_line1, city, region, postal_code, location, lat, lng, timezone)
values ('00000000-0000-4000-8000-0000000000d1', '00000000-0000-4000-8000-0000000000c1',
        'Store #1142 — Ponce', '1142 Ponce de Leon Ave NE', 'Atlanta', 'GA', '30306',
        '1142 Ponce de Leon Ave NE, Atlanta, GA 30306', 33.7738, -84.3530, 'America/New_York')
on conflict (id) do nothing;

-- MSA template version (also inserted by 0004 because signatures reference it).
insert into public.msa_versions (version, title, summary, effective_at, is_current)
values ('2026-10-16', 'EzWerkz Master Services Agreement (template)',
        'Template — have a licensed attorney review before use. Section 8 (Non-Circumvention / Conversion Fee) binds the client only.',
        date '2026-10-16', true)
on conflict (version) do nothing;

-- Closed-loop store. Prices mirror src/lib/pricing.ts (membership = CREDIT.membershipFeeCents).
insert into public.credit_store_products (sku, name, description, kind, price_cents, billing_interval, sort_order)
values
  ('membership-monthly', 'EzWerkz Credit Builder membership',
   'Monthly membership charged to your EzWerkz credit line. Cancel any time.', 'membership', 500, 'monthly', 0),
  ('course-budgeting-basics', 'Budgeting Basics (video course)',
   'Six short lessons on building a budget around variable shift income.', 'course', 2500, 'one_time', 10),
  ('course-credit-101', 'How Credit Works (video course)',
   'What goes into a credit report and how payment history is reported. Educational only; results vary.', 'course', 1500, 'one_time', 20),
  ('ebook-first-paycheck', 'Your First Paycheck Plan (e-book)',
   'A practical guide to taxes, saving and bills for hourly workers.', 'ebook', 1000, 'one_time', 30)
on conflict (sku) do nothing;

-- Card offers for the 660+ matching widget. Fictional issuers only. Ranked by
-- fit (min score, annual fee) in the app, never by bounty.
insert into public.affiliate_offers (id, issuer, product_name, min_score, annual_fee_cents, apr_text, highlights, bounty_cents, url)
values
  ('00000000-0000-4000-8000-0000000000a1', 'Northwind Bank', 'Northwind Bank Secured Visa', 300, 0,
   '27.99% variable APR', array['Refundable $200 security deposit', 'Reports to all three bureaus', 'No annual fee'], 2500,
   'https://example.com/offers/northwind-secured-visa'),
  ('00000000-0000-4000-8000-0000000000a2', 'Fabrikam Credit Union', 'Fabrikam Starter Mastercard', 600, 0,
   '24.49% variable APR', array['No deposit required', 'Credit line reviews after 6 months', 'Membership open to all US residents'], 4000,
   'https://example.com/offers/fabrikam-starter'),
  ('00000000-0000-4000-8000-0000000000a3', 'Woodgrove Bank', 'Woodgrove Everyday Cash Visa', 660, 0,
   '22.99%–29.99% variable APR', array['1.5% cash back on everything', 'No annual fee', 'No foreign transaction fees'], 9000,
   'https://example.com/offers/woodgrove-everyday-cash'),
  ('00000000-0000-4000-8000-0000000000a4', 'Contoso Federal', 'Contoso Federal Platinum Mastercard', 670, 3900,
   '19.99% variable APR', array['Lower ongoing APR', '$39 annual fee', 'Cell phone protection'], 12000,
   'https://example.com/offers/contoso-platinum'),
  ('00000000-0000-4000-8000-0000000000a5', 'Tailspin Bank', 'Tailspin Rewards Visa Signature', 700, 9500,
   '21.24%–28.24% variable APR', array['3x points on groceries and gas', '$95 annual fee', 'Travel insurance'], 20000,
   'https://example.com/offers/tailspin-rewards')
on conflict (id) do nothing;

-- Lead sources. Only official APIs, RSS, or robots.txt-permitted JSON-LD pages
-- may run. Sources whose terms prohibit scraping ship disabled and can only be
-- enabled with a licensed feed/API (enforced by lead_sources_license_required).
insert into public.lead_sources (key, name, kind, enabled, requires_license, base_url, rate_limit_per_minute, respects_robots_txt, config, notes)
values
  ('adzuna', 'Adzuna Jobs API', 'official_api', false, false,
   'https://api.adzuna.com/v1/api/jobs/us/search', 20, true,
   '{"country": "us", "what_or": "cashier stocker warehouse overnight", "where": "Atlanta, GA"}'::jsonb,
   'Official API. Stays disabled until ADZUNA_APP_ID / ADZUNA_APP_KEY are configured.'),
  ('jsonld', 'Employer career pages (schema.org JobPosting JSON-LD)', 'jsonld_page', true, false,
   null, 10, true, '{"seed_urls": []}'::jsonb,
   'Fetches only URLs whose robots.txt allows the path, with an identifying User-Agent and rate limits. No login walls, no CAPTCHA or anti-bot evasion.'),
  ('indeed', 'Indeed', 'licensed_feed', false, true,
   null, 10, true, '{}'::jsonb,
   'Indeed''s terms prohibit scraping. Disabled adapter: enable only with a licensed feed/API agreement (set license_reference).'),
  ('ziprecruiter', 'ZipRecruiter', 'licensed_feed', false, true,
   null, 10, true, '{}'::jsonb,
   'ZipRecruiter''s terms prohibit scraping. Disabled adapter: enable only with a licensed feed/API agreement (set license_reference).'),
  ('craigslist', 'Craigslist', 'licensed_feed', false, true,
   null, 10, true, '{}'::jsonb,
   'Craigslist''s terms prohibit scraping. Disabled adapter: enable only with a licensed data agreement (set license_reference).')
on conflict (key) do nothing;
