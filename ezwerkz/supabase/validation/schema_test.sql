-- Functional tests for the EzWerkz schema: RLS, guards, compliance rules and every RPC.
-- Run via supabase/validation/run.sh (validation only).
\set ON_ERROR_STOP 1
\pset pager off

-- ============================================================ fixtures
select t.as_db();
insert into auth.users (id, email, raw_user_meta_data) values
  ('aaaaaaaa-0000-4000-8000-000000000001', 'ops@ezwerkz.example', '{"full_name":"Ops One","role":"admin"}'),
  ('aaaaaaaa-0000-4000-8000-000000000002', 'ops2@ezwerkz.example', '{"full_name":"Ops Two"}'),
  ('bbbbbbbb-0000-4000-8000-000000000001', 'store1142@example.com', '{"full_name":"Priya Patel"}'),
  ('bbbbbbbb-0000-4000-8000-000000000002', 'other@example.com', '{"full_name":"Other Manager"}'),
  ('cccccccc-0000-4000-8000-000000000001', 'devon@example.com', '{"full_name":"Devon Carter"}'),
  ('cccccccc-0000-4000-8000-000000000002', 'jo@example.com', '{"full_name":"Jo Rivera"}'),
  ('cccccccc-0000-4000-8000-000000000003', 'far@example.com', '{"full_name":"Far Away"}'),
  ('cccccccc-0000-4000-8000-000000000004', 'quiet@example.com', '{"full_name":"No Texts"}'),
  ('dddddddd-0000-4000-8000-000000000001', 'maya@example.com', '{"full_name":"Maya Johnson"}'),
  ('dddddddd-0000-4000-8000-000000000002', 'friend@example.com', '{"full_name":"Friend Fan"}'),
  ('dddddddd-0000-4000-8000-000000000003', 'late@example.com', '{"full_name":"Late Larry"}');

select t.ok((select count(*) = 11 from public.users), 'auth trigger created public.users rows');
select t.ok((select bool_and(role = 'member') from public.users), 'metadata cannot grant a role: everyone starts as member');
select t.ok((select count(*) = 22 from public.user_modules), 'default modules credit+wallet');
select t.ok((select count(*) = 11 from public.wallets), 'every user has a wallet');
select t.ok((select full_name = 'Maya Johnson' from public.users where id = 'dddddddd-0000-4000-8000-000000000001'), 'full_name from metadata');
select t.ok((select referral_code ~ '^[A-Z0-9]{8}$' from public.users where id = 'dddddddd-0000-4000-8000-000000000001'), 'referral code generated');

-- trusted (SQL editor) role assignment
insert into public.organizations (id, name) values ('00000000-0000-4000-8000-0000000000c2', 'Other Co');
update public.users set role = 'admin' where id in ('aaaaaaaa-0000-4000-8000-000000000001', 'aaaaaaaa-0000-4000-8000-000000000002');
update public.users set role = 'client_manager', organization_id = '00000000-0000-4000-8000-0000000000c1' where id = 'bbbbbbbb-0000-4000-8000-000000000001';
update public.users set role = 'client_manager', organization_id = '00000000-0000-4000-8000-0000000000c2' where id = 'bbbbbbbb-0000-4000-8000-000000000002';
select t.ok((select count(*) = 2 from public.audit_log where action = 'users.role_changed' and entity_id::text like 'bbbbbbbb%'), 'role changes audited');

-- ============================================================ core: users, consents, audit, config
select t.as_user('dddddddd-0000-4000-8000-000000000001');
select t.throws($$update public.users set role = 'admin' where id = 'dddddddd-0000-4000-8000-000000000001'$$, 'FORBIDDEN_COLUMN', 'member cannot self-promote');
select t.throws($$update public.users set organization_id = '00000000-0000-4000-8000-0000000000c1' where id = auth.uid()$$, 'FORBIDDEN_COLUMN', 'member cannot join an org');
update public.users set full_name = 'Maya J.', phone_e164 = '+14045550101', sms_opt_in = true, sms_opt_in_at = '2001-01-01' where id = auth.uid();
select t.ok((select sms_opt_in_at > now() - interval '1 minute' from public.users where id = auth.uid()), 'sms_opt_in_at is server time, not client-supplied');
select t.ok((select count(*) = 1 from public.users), 'member sees only own user row');
select t.ok((select count(*) = 0 from public.users where id = 'cccccccc-0000-4000-8000-000000000001'), 'member cannot read another profile');
select t.ok((select count(*) = 1 from public.platform_config where key = 'membership_fee_cents'), 'config readable');
update public.platform_config set value = '1' where key = 'membership_fee_cents';
select t.ok((select value = '500'::jsonb from public.platform_config where key = 'membership_fee_cents'), 'member cannot change config (RLS)');
insert into public.consents (kind, text_version, accepted_at) values ('soft_pull', 'v1', '2000-01-01') returning id as maya_soft_pull \gset
select t.ok((select accepted_at > now() - interval '1 minute' from public.consents where id = :'maya_soft_pull'), 'consent accepted_at is server time');
select t.throws(format($$update public.consents set text_version = 'v2' where id = %L$$, :'maya_soft_pull'), 'CONSENT_IMMUTABLE');
delete from public.consents where id = :'maya_soft_pull';
select t.ok((select count(*) = 1 from public.consents where id = :'maya_soft_pull'), 'member cannot delete consents (RLS)');
insert into public.audit_log (actor_id, action, entity_type) values ('aaaaaaaa-0000-4000-8000-000000000001', 'member.note', 'test');
select t.as_db();
select t.ok((select actor_id = 'dddddddd-0000-4000-8000-000000000001' from public.audit_log where action = 'member.note'), 'audit actor cannot be forged');
select t.throws(format($$delete from public.consents where id = %L$$, :'maya_soft_pull'), 'APPEND_ONLY', 'consents cannot be deleted even by trusted code');
select t.as_user('dddddddd-0000-4000-8000-000000000001');

select t.as_user('bbbbbbbb-0000-4000-8000-000000000001');
select t.ok((select count(*) = 1 from public.users), 'manager sees self (no colleagues yet)');
select t.ok((select count(*) = 1 from public.organizations), 'manager sees own org only');

select t.as_user('aaaaaaaa-0000-4000-8000-000000000001');
select t.ok((select count(*) = 11 from public.users), 'admin sees all users');
update public.platform_config set value = '500' where key = 'membership_fee_cents';
update public.platform_config set value = '15' where key = 'dispatch_radius_miles';
select t.as_db();
select t.throws($$update public.audit_log set action = 'x'$$, 'APPEND_ONLY', 'audit_log is append-only (even for the owner)');
select t.throws($$delete from public.audit_log$$, 'APPEND_ONLY', 'audit_log delete blocked');

select t.as_anon();
select t.ok((select count(*) = 0 from public.users), 'anon sees nothing');
select t.ok((select count(*) = 0 from public.platform_config), 'anon cannot read config');
select t.throws($$select public.is_admin()$$, 'permission denied%', 'anon cannot call identity helpers');

-- ============================================================ wallet
select t.as_db();
select id as maya_wallet from public.wallets where user_id = 'dddddddd-0000-4000-8000-000000000001' \gset
select id as devon_wallet from public.wallets where user_id = 'cccccccc-0000-4000-8000-000000000001' \gset

select t.as_user('dddddddd-0000-4000-8000-000000000001');
select t.throws(format($$insert into public.ledger_entries (wallet_id, direction, amount_cents, category, description) values (%L, 'credit', 100000, 'deposit', 'free money')$$, :'maya_wallet'),
  'new row violates row-level security%', 'member cannot insert ledger rows');
select t.throws(format($$select public.wallet_post_entry(%L, 'credit', 100000, 'deposit', 'free money')$$, :'maya_wallet'), 'FORBIDDEN', 'member cannot credit own wallet');
select t.throws(format($$select public.wallet_post_entry(%L, 'debit', 100, 'withdrawal', 'not mine')$$, :'devon_wallet'), 'FORBIDDEN', 'member cannot touch another wallet');
update public.wallets set available_cents = 999999 where id = :'maya_wallet';
select t.ok((select available_cents = 0 from public.wallets where id = :'maya_wallet'), 'member cannot write own balance (RLS)');

select t.as_service();
select public.wallet_post_entry(:'maya_wallet', 'credit', 10000, 'deposit', 'Card top-up', 'stripe_payment_intent', 'ffffffff-0000-4000-8000-000000000001') as dep1 \gset
select public.wallet_post_entry(:'maya_wallet', 'credit', 10000, 'deposit', 'Card top-up (retry)', 'stripe_payment_intent', 'ffffffff-0000-4000-8000-000000000001') as dep2 \gset
select t.ok(:'dep1' = :'dep2', 'webhook retry is idempotent');
select t.ok((select available_cents = 10000 from public.wallets where id = :'maya_wallet'), 'deposit applied once');
select t.throws(format($$update public.wallets set available_cents = 1 where id = %L$$, :'maya_wallet'), 'FORBIDDEN_COLUMN', 'service role cannot write balances directly');

select t.as_user('dddddddd-0000-4000-8000-000000000001');
select public.wallet_post_entry(:'maya_wallet', 'debit', 3000, 'withdrawal', 'To bank');
select t.ok((select available_cents = 7000 from public.wallets where id = :'maya_wallet'), 'member debit applied');
select t.ok((select balance_after_cents = 7000 from public.ledger_entries where wallet_id = :'maya_wallet' order by created_at desc limit 1), 'balance_after recorded');
select t.throws(format($$select public.wallet_post_entry(%L, 'debit', 999999, 'withdrawal', 'too much')$$, :'maya_wallet'), 'INSUFFICIENT_FUNDS', 'no overdraft');

select t.as_db();
select t.throws(format($$update public.ledger_entries set amount_cents = 1 where wallet_id = %L$$, :'maya_wallet'), 'APPEND_ONLY', 'ledger update blocked');
select t.throws(format($$delete from public.ledger_entries where wallet_id = %L$$, :'maya_wallet'), 'APPEND_ONLY', 'ledger delete blocked');
select t.throws($$truncate public.ledger_entries cascade$$, 'APPEND_ONLY', 'ledger truncate blocked');
select t.throws($$delete from auth.users where id = 'dddddddd-0000-4000-8000-000000000001'$$, '%', 'cannot hard-delete a user with financial history');

select t.as_user('dddddddd-0000-4000-8000-000000000001');
insert into public.virtual_cards (wallet_id, provider_card_id, last4, brand, kind, nickname, status)
values (:'maya_wallet', 'ic_test_1', '4242', 'visa', 'permanent', 'Groceries', 'frozen') returning id as card1 \gset
select t.ok((select status = 'active' and user_id = auth.uid() from public.virtual_cards where id = :'card1'), 'card created active with owner');
select t.throws(format($$update public.virtual_cards set last4 = '0000' where id = %L$$, :'card1'), 'FORBIDDEN_COLUMN');
update public.virtual_cards set status = 'canceled' where id = :'card1';
select t.ok((select canceled_at is not null from public.virtual_cards where id = :'card1'), 'cancel stamped');
select t.throws(format($$update public.virtual_cards set status = 'active' where id = %L$$, :'card1'), 'CARD_CANCELED');
select t.throws(format($$insert into public.virtual_cards (wallet_id, provider_card_id, last4, brand, kind) values (%L, 'ic_x', '1111', 'visa', 'permanent')$$, :'devon_wallet'),
  'WALLET_NOT_FOUND', 'cannot attach a card to another wallet');
select t.ok((select count(*) = 0 from information_schema.columns where table_name = 'virtual_cards' and column_name ~ '(pan|cvv|cvc|card_number)'), 'no PAN/CVV columns');

insert into public.income_streams (label, source_type) values ('EzWerkz shifts', 'ezwerkz_payouts');
select t.ok((select wallet_id = :'maya_wallet' from public.income_streams limit 1), 'income stream targets own wallet');

insert into public.autopay_authorizations (purpose, max_amount_cents, authorization_text_version, authorized_at)
values ('membership_fee', 5000, 'autopay-2026-10-16', '2000-01-01') returning id as maya_autopay \gset
select t.ok((select authorized_at > now() - interval '1 minute' and wallet_id = :'maya_wallet' from public.autopay_authorizations where id = :'maya_autopay'), 'autopay: who/when/amount/version stored');
select t.throws(format($$update public.autopay_authorizations set max_amount_cents = 99999 where id = %L$$, :'maya_autopay'), 'AUTHORIZATION_IMMUTABLE');
delete from public.autopay_authorizations where id = :'maya_autopay';
select t.ok((select count(*) = 1 from public.autopay_authorizations where id = :'maya_autopay'), 'autopay authorization kept (revocable, not deletable)');

-- ============================================================ credit
select t.as_user('dddddddd-0000-4000-8000-000000000003');
insert into public.virtual_credit_lines (limit_cents, balance_cents) values (999999, 77);
select t.ok((select limit_cents = 50000 and balance_cents = 0 and account_number ~ '^SS[0-9]{12}$' from public.virtual_credit_lines), 'member-opened line forced to default limit/zero balance');

select t.as_user('dddddddd-0000-4000-8000-000000000001');
insert into public.membership_subscriptions (price_cents, free_months_remaining) values (1, 12);
select t.ok((select price_cents = 500 and free_months_remaining = 0 and credit_line_id is not null from public.membership_subscriptions), 'subscription price/free months forced; line opened');
select id as maya_line from public.virtual_credit_lines \gset
select id as course from public.credit_store_products where sku = 'course-budgeting-basics' \gset
select id as membership_product from public.credit_store_products where sku = 'membership-monthly' \gset
insert into public.credit_transactions (credit_line_id, kind, product_id, amount_cents) values (:'maya_line', 'purchase', :'course', 1);
select t.ok((select balance_cents = 2500 from public.virtual_credit_lines), 'purchase charged at server price');
select t.throws(format($$insert into public.credit_transactions (credit_line_id, kind, product_id, amount_cents) values (%L, 'purchase', %L, 500)$$, :'maya_line', :'membership_product'), 'USE_MEMBERSHIP_SUBSCRIPTION');
select t.throws(format($$insert into public.credit_transactions (credit_line_id, kind, amount_cents) values (%L, 'refund', 2500)$$, :'maya_line'), 'FORBIDDEN', 'member cannot self-refund');
select t.throws(format($$select public.record_membership_payment(%L, 100, 'card', 'pi_fake')$$, :'maya_line'), 'STATEMENT_NOT_FOUND');

select t.as_service();
select t.throws(format($$update public.virtual_credit_lines set balance_cents = 0 where id = %L$$, :'maya_line'), 'FORBIDDEN_COLUMN', 'service role cannot zero a balance');
select t.throws(format($$update public.virtual_credit_lines set limit_cents = 900000 where id = %L$$, :'maya_line'), 'FORBIDDEN_COLUMN', 'limit only via level-up');
select public.post_membership_charge('dddddddd-0000-4000-8000-000000000001') as charge1 \gset
select public.post_membership_charge('dddddddd-0000-4000-8000-000000000001') as charge2 \gset
select t.ok(:'charge1' = :'charge2', 'membership charge idempotent per month');
select t.ok((select balance_cents = 3000 from public.virtual_credit_lines where id = :'maya_line'), 'fee charged to line');
select public.cut_credit_statement(:'maya_line', date '2026-09-01', date '2026-09-30', date '2026-10-21') as stmt1 \gset
select t.ok((select statement_balance_cents = 3000 and minimum_due_cents = 3000 from public.credit_statements where id = :'stmt1'), 'statement cut at line balance');
select t.ok((select count(*) = 2 from public.credit_transactions where statement_id = :'stmt1'), 'transactions assigned to statement');

select t.as_user('dddddddd-0000-4000-8000-000000000001');
select t.throws(format($$select public.record_membership_payment(%L, 3000, 'card', 'pi_fake')$$, :'stmt1'), 'PROCESSOR_CONFIRMATION_REQUIRED', 'member cannot self-record a card payment');
select t.throws(format($$select public.sweep_membership_from_wallet(%L)$$, 'dddddddd-0000-4000-8000-000000000002'), 'FORBIDDEN', 'cannot sweep someone else');
select public.sweep_membership_from_wallet('dddddddd-0000-4000-8000-000000000001') as sweep1 \gset
select t.ok(:'sweep1' <> '', 'autopay sweep paid the statement');
select t.ok((select available_cents = 4000 from public.wallets where id = :'maya_wallet'), 'wallet debited 3000');
select t.ok((select balance_cents = 0 from public.virtual_credit_lines), 'line paid down');
select t.ok((select paid_on_time and paid_at is not null and amount_paid_cents = 3000 from public.credit_statements where id = :'stmt1'), 'statement paid on time');
select t.ok((select count(*) = 1 from public.notifications where kind = 'autopay.receipt'), 'sweep receipt sent');
select t.ok((select count(*) = 1 from public.user_badges where badge_key = 'first_on_time_payment'), 'first on-time badge');
select t.ok((select count(*) = 2 and sum(amount_cents) = 3000 from public.treasury_allocations where credit_payment_id = :'sweep1'), 'member can see own treasury split');

select t.as_db();
select t.ok((select amount_cents = 150 from public.treasury_allocations where credit_payment_id = :'sweep1' and bucket = 'reporting_vendor'), 'vendor gets 150');
select t.ok((select amount_cents = 2850 from public.treasury_allocations where credit_payment_id = :'sweep1' and bucket = 'platform'), 'platform gets remainder');
select t.ok((select count(*) = 0 from public.treasury_allocations where bucket = 'impact'), 'impact is off by default');
select t.throws($$update public.treasury_allocations set amount_cents = 1$$, 'APPEND_ONLY', 'treasury append-only');
-- impact on but without a named partner -> still not allocated
update public.platform_config set value = '50' where key = 'membership_impact_cents';

-- Two more on-time statements -> level-up.
select t.as_service();
insert into public.credit_transactions (credit_line_id, kind, amount_cents, description) values (:'maya_line', 'membership_fee', 500, 'Oct');
select public.cut_credit_statement(:'maya_line', date '2026-10-01', date '2026-10-31', date '2026-11-21') as stmt2 \gset
select public.record_membership_payment(:'stmt2', 500, 'card', 'pi_test_2') as pay2 \gset
select public.record_membership_payment(:'stmt2', 500, 'card', 'pi_test_2') as pay2b \gset
select t.ok(:'pay2' = :'pay2b', 'card payment idempotent on provider id');
select t.ok((select count(*) = 0 from public.treasury_allocations where credit_payment_id = :'pay2' and bucket = 'impact'), 'impact needs a real partner name');
select t.ok((select limit_cents = 50000 from public.virtual_credit_lines where id = :'maya_line'), 'no level-up after 2');
insert into public.credit_transactions (credit_line_id, kind, amount_cents, description) values (:'maya_line', 'membership_fee', 500, 'Nov');
select public.cut_credit_statement(:'maya_line', date '2026-11-01', date '2026-11-30', date '2026-12-21') as stmt3 \gset
select public.record_membership_payment(:'stmt3', 500, 'ach', 'pi_test_3') as pay3 \gset
select t.ok((select limit_cents = 100000 and level_up_applied_at is not null from public.virtual_credit_lines where id = :'maya_line'), 'level-up to 100000 after 3 on-time');
select t.ok((select count(*) = 1 from public.user_badges where badge_key = 'limit_level_up'), 'level-up badge');
select t.ok((select count(*) = 1 from public.user_badges where badge_key = 'on_time_streak_3'), 'streak badge');
select t.ok(public.apply_credit_level_up(:'maya_line') = false, 'level-up only once');
select t.ok(public.credit_on_time_streak(:'maya_line') = 3, 'streak = 3');

-- impact with a real partner
select t.as_db();
update public.platform_config set value = '"Atlanta Community Food Bank (example)"' where key = 'impact_partner_name';
select t.as_service();
insert into public.credit_transactions (credit_line_id, kind, amount_cents, description) values (:'maya_line', 'membership_fee', 500, 'Dec');
select public.cut_credit_statement(:'maya_line', date '2026-12-01', date '2026-12-31', date '2027-01-21') as stmt4 \gset
select public.record_membership_payment(:'stmt4', 500, 'card', 'pi_test_4') as pay4 \gset
select t.ok((select amount_cents = 50 from public.treasury_allocations where credit_payment_id = :'pay4' and bucket = 'impact'), 'impact allocated only with partner');
select t.ok((select amount_cents = 300 from public.treasury_allocations where credit_payment_id = :'pay4' and bucket = 'platform'), 'platform remainder after impact');
select t.ok((select total_cents = 50 from public.treasury_impact_summary()), 'impact summary from actual allocations');
-- reversal
update public.credit_payments set status = 'reversed' where id = :'pay4';
select t.ok((select sum(amount_cents) = 0 from public.treasury_allocations where credit_payment_id = :'pay4'), 'reversal writes compensating rows');
select t.ok((select balance_cents = 500 from public.virtual_credit_lines where id = :'maya_line'), 'reversal restores balance');
select t.ok((select paid_at is null and paid_on_time is null from public.credit_statements where id = :'stmt4'), 'reversal reopens statement');
select t.throws(format($$update public.credit_payments set status = 'succeeded' where id = %L$$, :'pay4'), 'INVALID_STATUS_TRANSITION');
select t.as_db();
update public.platform_config set value = '0' where key = 'membership_impact_cents';
update public.platform_config set value = 'null' where key = 'impact_partner_name';

-- Late payment
select t.as_service();
select id as larry_line from public.virtual_credit_lines where user_id = 'dddddddd-0000-4000-8000-000000000003' \gset
insert into public.credit_transactions (credit_line_id, kind, amount_cents, description) values (:'larry_line', 'membership_fee', 500, 'Aug');
select public.cut_credit_statement(:'larry_line', date '2026-08-01', date '2026-08-31', date '2026-09-21') as late_stmt \gset
select public.record_membership_payment(:'late_stmt', 500, 'card', 'pi_late');
select t.ok((select paid_on_time = false and days_past_due > 20 from public.credit_statements where id = :'late_stmt'), 'late payment recorded honestly');
select t.ok((select count(*) = 0 from public.user_badges where user_id = 'dddddddd-0000-4000-8000-000000000003'), 'no badge for late payment');
-- limit enforcement
select t.as_user('dddddddd-0000-4000-8000-000000000003');
select id as course15 from public.credit_store_products where sku = 'course-credit-101' \gset
insert into public.credit_transactions (credit_line_id, kind, product_id, amount_cents)
select :'larry_line', 'purchase', :'course15', 0 from generate_series(1, 33);
select t.ok((select balance_cents = 49500 from public.virtual_credit_lines), '33 x 1500 purchases');
select t.throws(format($$insert into public.credit_transactions (credit_line_id, kind, product_id, amount_cents) values (%L, 'purchase', %L, 0)$$, :'larry_line', :'course15'), 'CREDIT_LIMIT_EXCEEDED');

-- Scores + affiliate unlock
select t.as_service();
select t.throws($$insert into public.credit_score_snapshots (user_id, score, provider) values ('dddddddd-0000-4000-8000-000000000003', 700, 'softpull-partner')$$, 'SOFT_PULL_CONSENT_REQUIRED');
insert into public.credit_score_snapshots (user_id, score, provider) values ('dddddddd-0000-4000-8000-000000000001', 640, 'softpull-partner');
select t.ok((select count(*) = 0 from public.affiliate_unlocks), 'no unlock below 660');
insert into public.credit_score_snapshots (user_id, score, provider) values ('dddddddd-0000-4000-8000-000000000001', 665, 'softpull-partner');
insert into public.credit_score_snapshots (user_id, score, provider) values ('dddddddd-0000-4000-8000-000000000001', 700, 'softpull-partner');
select t.ok((select count(*) = 1 and min(score) = 665 from public.affiliate_unlocks), 'first >= 660 unlocks once');
select t.ok((select count(*) = 1 from public.notifications where kind = 'credit.offers_unlocked' and body like '%may earn a commission%'), 'unlock notification with commission disclosure');
select t.ok((select array_agg(issuer order by ord) = array['Woodgrove Bank', 'Fabrikam Credit Union', 'Northwind Bank']
             from (select issuer, row_number() over () as ord from public.ranked_affiliate_offers(665)) r), 'offers ranked by fit, not bounty');

-- Referrals
select t.as_db();
select referral_code as maya_code from public.users where id = 'dddddddd-0000-4000-8000-000000000001' \gset
select t.as_user('dddddddd-0000-4000-8000-000000000001');
select t.throws(format($$select public.redeem_referral_code(%L)$$, :'maya_code'), 'SELF_REFERRAL');
select t.as_user('dddddddd-0000-4000-8000-000000000002');
select public.redeem_referral_code(lower(:'maya_code'));
select t.throws(format($$select public.redeem_referral_code(%L)$$, :'maya_code'), 'ALREADY_REFERRED');
insert into public.membership_subscriptions default values;
select t.as_service();
select public.wallet_post_entry(w.id, 'credit', 2000, 'deposit', 'top-up') from public.wallets w where w.user_id = 'dddddddd-0000-4000-8000-000000000002';
select public.post_membership_charge('dddddddd-0000-4000-8000-000000000002');
select public.cut_credit_statement(l.id, date '2026-09-01', date '2026-09-30', date '2026-10-31') as friend_stmt
  from public.virtual_credit_lines l where l.user_id = 'dddddddd-0000-4000-8000-000000000002' \gset
select t.as_user('dddddddd-0000-4000-8000-000000000002');
select public.record_membership_payment(:'friend_stmt', 500, 'wallet');
select t.as_db();
select t.ok((select status = 'rewarded' from public.referrals where referred_user_id = 'dddddddd-0000-4000-8000-000000000002'), 'referral rewarded after first on-time payment');
select t.ok((select free_months_remaining = 1 from public.membership_subscriptions where user_id = 'dddddddd-0000-4000-8000-000000000001'), 'referrer got a free month');
select t.as_service();
-- next month the free month is used instead of a charge (simulate a new month by clearing the period marker as trusted code)
update public.membership_subscriptions set current_period_start = date '2026-09-01' where user_id = 'dddddddd-0000-4000-8000-000000000001';
select t.ok(public.post_membership_charge('dddddddd-0000-4000-8000-000000000001') is null, 'free month consumed instead of charge');
select t.ok((select free_months_remaining = 0 from public.membership_subscriptions where user_id = 'dddddddd-0000-4000-8000-000000000001'), 'free month decremented');

-- Cancellation (<= 2 taps = one update) and add-ons
select t.as_user('dddddddd-0000-4000-8000-000000000001');
select t.throws($$update public.membership_subscriptions set free_months_remaining = 9$$, 'FORBIDDEN_COLUMN');
update public.membership_subscriptions set status = 'canceled', cancel_reason = 'testing';
select t.ok((select canceled_at is not null from public.membership_subscriptions), 'member can cancel directly');
insert into public.addon_subscriptions (addon_key, price_cents) values ('ai_coach', 1) returning id as coach \gset
select t.ok((select price_cents = 1000 from public.addon_subscriptions where id = :'coach'), 'add-on price from config');
update public.addon_subscriptions set status = 'canceled' where id = :'coach';
select t.throws(format($$update public.addon_subscriptions set status = 'active' where id = %L$$, :'coach'), 'INVALID_STATUS_TRANSITION');
insert into public.addon_subscriptions (addon_key) values ('ai_coach');
select t.throws($$insert into public.addon_subscriptions (addon_key) values ('ai_coach')$$, 'duplicate key%', 'one active add-on per key');

-- Disputes, bills
insert into public.credit_reporting_disputes (dispute_type, description, status) values ('balance', 'Balance looks wrong', 'resolved_verified') returning id as dispute \gset
select t.ok((select status = 'received' and due_at > now() + interval '29 days' and credit_line_id is not null from public.credit_reporting_disputes where id = :'dispute'), 'FCRA dispute intake');
select t.throws($$insert into public.bill_analyses (storage_path) values ('cccccccc-0000-4000-8000-000000000001/bill.pdf')$$, 'INVALID_STORAGE_PATH');
insert into public.bill_analyses (storage_path) values ('bill-uploads/dddddddd-0000-4000-8000-000000000001/bill.pdf') returning storage_path as bill_path \gset
select t.ok(:'bill_path' = 'dddddddd-0000-4000-8000-000000000001/bill.pdf', 'bucket prefix normalized');
insert into storage.objects (bucket_id, name) values ('bill-uploads', 'dddddddd-0000-4000-8000-000000000001/bill.pdf');
select t.throws($$insert into storage.objects (bucket_id, name) values ('bill-uploads', 'cccccccc-0000-4000-8000-000000000001/x.pdf')$$, 'new row violates row-level security%', 'bill uploads owner-only');
select t.throws($$insert into storage.objects (bucket_id, name) values ('drug-screen-evidence', 'x.jpg')$$, 'new row violates row-level security%', 'evidence bucket admin-only');

-- ============================================================ shifts: MSA
select t.as_user('bbbbbbbb-0000-4000-8000-000000000001');
select t.throws($$insert into public.shifts (location, lat, lng, position_title, tier_required, scheduled_start, scheduled_end)
                  values ('x', 33.77, -84.35, 'Stocking', 1, now() + interval '1 hour', now() + interval '5 hours')$$, 'MSA_REQUIRED', 'cannot post before signing MSA');
select t.throws($$insert into public.contract_signatures (company_id, msa_version, msa_signed, section8_acknowledged, section8_initials, document_sha256)
                  values ('00000000-0000-4000-8000-0000000000c1', '2026-10-16', true, false, 'PP', repeat('a', 64))$$, '%contract_signatures_both_acknowledged%', 'Section 8 acknowledgment required');
select t.throws($$insert into public.contract_signatures (company_id, msa_version, msa_signed, section8_acknowledged, section8_initials, document_sha256)
                  values ('00000000-0000-4000-8000-0000000000c2', '2026-10-16', true, true, 'PP', repeat('a', 64))$$, '%', 'cannot sign for another company');
insert into public.contract_signatures (company_id, msa_version, msa_signed, section8_acknowledged, section8_initials, document_sha256, ip_address)
values ('00000000-0000-4000-8000-0000000000c1', '2026-10-16', true, true, 'pp', repeat('a', 64), '203.0.113.7') returning id as sig \gset
select t.ok((select section8_initials = 'PP' and signer_id = auth.uid() from public.contract_signatures where id = :'sig'), 'signature recorded');
select t.as_db();
select t.throws(format($$update public.contract_signatures set section8_initials = 'XX' where id = %L$$, :'sig'), 'APPEND_ONLY', 'signatures immutable');
select t.as_user('bbbbbbbb-0000-4000-8000-000000000001');
select t.ok(public.has_signed_msa('00000000-0000-4000-8000-0000000000c1'), 'has_signed_msa true for own org');
select t.as_user('bbbbbbbb-0000-4000-8000-000000000002');
select t.ok(not public.has_signed_msa('00000000-0000-4000-8000-0000000000c1'), 'has_signed_msa hides other orgs');

-- ============================================================ shifts: workers
select t.as_user('cccccccc-0000-4000-8000-000000000001');
select t.ok(public.enroll_module('shifts') = 'worker', 'member becomes worker via shifts door');
update public.users set phone_e164 = '+14045550001', home_lat = 33.80, home_lng = -84.38 where id = auth.uid();
insert into public.consents (kind, text_version) values ('sms', 'sms-2026-10-16');
select t.ok((select sms_opt_in and sms_opt_in_at is not null and home_geo is not null from public.users where id = auth.uid()), 'sms consent -> opt-in; home geo derived');
select t.ok((select compliance_tier = 1 and background_check_status = 'not_started' from public.worker_compliance), 'worker compliance row created');
select t.throws($$update public.worker_compliance set compliance_tier = 2$$, 'FORBIDDEN_COLUMN', 'worker cannot self-upgrade');
select t.throws($$update public.worker_compliance set engagement_type = 'w2_eor'$$, 'FORBIDDEN_COLUMN');
update public.worker_compliance set payout_destination = 'ezwerkz_wallet';

select t.as_user('cccccccc-0000-4000-8000-000000000002');
select public.enroll_module('shifts');
update public.users set phone_e164 = '+14045550002', home_lat = 33.75, home_lng = -84.30, sms_opt_in = true where id = auth.uid();
select t.as_user('cccccccc-0000-4000-8000-000000000003');
select public.enroll_module('shifts');
update public.users set phone_e164 = '+14045550003', home_lat = 34.50, home_lng = -84.35, sms_opt_in = true where id = auth.uid();
select t.as_user('cccccccc-0000-4000-8000-000000000004');
select public.enroll_module('shifts');
update public.users set phone_e164 = '+14045550004', home_lat = 33.78, home_lng = -84.36 where id = auth.uid();

-- ============================================================ shifts: posting + visibility
select t.as_user('bbbbbbbb-0000-4000-8000-000000000001');
insert into public.shifts (id, location_id, location, lat, lng, position_title, tier_required, scheduled_start, scheduled_end, is_emergency, hourly_billing_rate_cents, hourly_pay_rate_cents)
values ('eeeeeeee-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000d1', '1142 Ponce de Leon Ave NE', 33.7738, -84.3530,
        'Stocking', 1, now() - interval '2 hours', now() - interval '2 hours' + interval '8 hours 8 minutes', true, 1, 1);
select t.ok((select hourly_billing_rate_cents = 2200 and hourly_pay_rate_cents = 1500 and geo is not null and client_id = auth.uid()
             from public.shifts where id = 'eeeeeeee-0000-4000-8000-00000000000a'), 'rates from config, geo derived, client forced');
insert into public.shifts (id, location, lat, lng, position_title, tier_required, scheduled_start, scheduled_end)
values ('eeeeeeee-0000-4000-8000-000000000002', 'Store 1142', 33.7738, -84.3530, 'Cashier', 2, now() + interval '2 days', now() + interval '2 days 6 hours');
select t.ok((select hourly_billing_rate_cents = 3500 and hourly_pay_rate_cents = 1800 from public.shifts where id = 'eeeeeeee-0000-4000-8000-000000000002'), 'tier 2 rates');
select t.throws($$insert into public.shifts (location, lat, lng, position_title, tier_required, scheduled_start, scheduled_end, location_id)
                  values ('x', 33.77, -84.35, 'Stocking', 1, now(), now() + interval '4 hours', '00000000-0000-4000-8000-0000000000d9')$$, 'INVALID_LOCATION');
select t.throws($$select * from public.workers_within_radius('eeeeeeee-0000-4000-8000-00000000000a')$$, 'FORBIDDEN', 'managers never get worker phone numbers');

select t.as_user('cccccccc-0000-4000-8000-000000000001');
select t.ok((select count(*) = 1 from public.shifts), 'tier-1 worker sees only the open tier-1 shift');
select t.ok((select count(*) = 1 from public.organizations), 'worker sees the shift''s company');
select t.as_user('bbbbbbbb-0000-4000-8000-000000000002');
select t.ok((select count(*) = 0 from public.shifts), 'other company sees none');
select t.as_user('dddddddd-0000-4000-8000-000000000001');
select t.ok((select count(*) = 0 from public.shifts), 'member sees no shifts');

select t.as_service();
select t.ok((select array_agg(full_name order by distance_miles) = array['Devon Carter', 'Jo Rivera']
             from public.workers_within_radius('eeeeeeee-0000-4000-8000-00000000000a')), 'radius: opted-in, eligible, within 15 mi');
select t.ok((select bool_and(distance_miles between 0.1 and 15) from public.workers_within_radius('eeeeeeee-0000-4000-8000-00000000000a')), 'distances in miles');
select t.ok((select count(*) = 3 from public.workers_within_radius('eeeeeeee-0000-4000-8000-00000000000a', 60)), 'wider radius adds the far worker, never the non-opted-in one');
select t.ok((select count(*) = 0 from public.workers_within_radius('eeeeeeee-0000-4000-8000-000000000002')), 'tier-2 shift: no tier-2 workers yet');

-- ============================================================ claim + approve (shift A)
select t.as_user('cccccccc-0000-4000-8000-000000000001');
select t.throws($$select public.claim_shift('eeeeeeee-0000-4000-8000-000000000002', auth.uid())$$, 'TIER_REQUIRED');
select t.throws($$select public.claim_shift('eeeeeeee-0000-4000-8000-00000000000a', 'cccccccc-0000-4000-8000-000000000002')$$, 'FORBIDDEN', 'cannot claim for someone else');
select t.ok(public.claim_shift('eeeeeeee-0000-4000-8000-00000000000a', auth.uid()), 'claim succeeds');
select t.as_user('cccccccc-0000-4000-8000-000000000002');
select t.ok(public.claim_shift('eeeeeeee-0000-4000-8000-00000000000a', auth.uid()) = false, 'second claim loses (false)');
select t.as_user('cccccccc-0000-4000-8000-000000000001');
select t.ok((select status = 'claimed' and claimed_by_name = 'Devon Carter' from public.shifts where id = 'eeeeeeee-0000-4000-8000-00000000000a'), 'claimed with display name');
select t.throws($$update public.shifts set hourly_pay_rate_cents = 9999 where id = 'eeeeeeee-0000-4000-8000-00000000000a'$$, 'FORBIDDEN_COLUMN');
select t.throws($$update public.shifts set status = 'approved' where id = 'eeeeeeee-0000-4000-8000-00000000000a'$$, 'USE_APPROVE_SHIFT');
select t.throws($$update public.shifts set status = 'open', claimed_by = null where id = 'eeeeeeee-0000-4000-8000-00000000000a'$$, 'TOO_LATE_TO_RELEASE');
update public.shifts set status = 'in_progress' where id = 'eeeeeeee-0000-4000-8000-00000000000a';
select t.ok((select started_at is not null from public.shifts where id = 'eeeeeeee-0000-4000-8000-00000000000a'), 'check-in stamped');
select id as thread_a from public.chat_threads where shift_id = 'eeeeeeee-0000-4000-8000-00000000000a' \gset
insert into public.chat_messages (thread_id, body, sender_role, flagged) values (:'thread_a', 'On my way! text me at (404) 555-0199 or devon@mail.com', 'admin', false) returning id as msg1, body as msg1_body, sender_role as msg1_role \gset
select t.ok(:'msg1_body' = 'On my way! text me at [contact info hidden] or [contact info hidden]', 'DB backstop redacts contact info');
select t.ok(:'msg1_role' = 'worker', 'sender_role forced from profile');
select t.as_user('bbbbbbbb-0000-4000-8000-000000000001');
select t.ok((select count(*) = 1 from public.chat_messages where thread_id = :'thread_a'), 'manager reads the thread');
insert into public.chat_messages (thread_id, body) values (:'thread_a', 'Thanks Devon, see you soon');
select t.ok((select count(*) = 1 from public.users where id = 'cccccccc-0000-4000-8000-000000000001') = false, 'manager cannot read worker profile (phone)');
select t.as_user('bbbbbbbb-0000-4000-8000-000000000002');
select t.ok((select count(*) = 0 from public.chat_messages), 'other company cannot read chat');
select t.throws(format($$insert into public.chat_messages (thread_id, body) values (%L, 'hi')$$, :'thread_a'), 'new row violates row-level security%', 'outsiders cannot post');
select t.as_user('aaaaaaaa-0000-4000-8000-000000000001');
select t.ok((select count(*) = 1 and bool_and(severity = 'high' and status = 'open') from public.poach_flags), 'backstop created an admin flag');
update public.poach_flags set status = 'reviewed', resolution_notes = 'Reminded both parties of Section 8';
select t.ok((select reviewed_by = auth.uid() and reviewed_at is not null from public.poach_flags), 'review stamped');

select t.as_user('cccccccc-0000-4000-8000-000000000001');
select t.throws($$select public.approve_shift('eeeeeeee-0000-4000-8000-00000000000a', 5, true)$$, 'FORBIDDEN', 'worker cannot approve');
select t.as_user('bbbbbbbb-0000-4000-8000-000000000002');
select t.throws($$select public.approve_shift('eeeeeeee-0000-4000-8000-00000000000a', 5, true)$$, 'FORBIDDEN', 'other company cannot approve');
select t.as_user('aaaaaaaa-0000-4000-8000-000000000001');
select t.throws($$select public.approve_shift('eeeeeeee-0000-4000-8000-00000000000a', 5, true)$$, 'FORBIDDEN', 'admins cannot approve on the client''s behalf');
select t.as_user('bbbbbbbb-0000-4000-8000-000000000001');
select t.throws($$select public.approve_shift('eeeeeeee-0000-4000-8000-00000000000a', 6, true)$$, 'INVALID_RATING');
select public.approve_shift('eeeeeeee-0000-4000-8000-00000000000a', 5, true) as payout_a \gset
select t.throws($$select public.approve_shift('eeeeeeee-0000-4000-8000-00000000000a', 5, true)$$, 'ALREADY_APPROVED');
select t.ok((select count(*) = 1 from public.shift_ratings), 'manager sees rating');
select t.ok((select count(*) = 0 from public.payouts), 'manager cannot read payouts');
select t.as_user('cccccccc-0000-4000-8000-000000000001');
-- 8h08m -> 8.25h (quarter-hour rounding, same as quoteShift)
select t.ok((select total_billed_cents = 18150 and total_paid_to_worker_cents = 12375 and agency_margin_cents = 5775
                    and status = 'pending' and destination = 'ezwerkz_wallet' from public.payouts where id = :'payout_a'), 'payout = rate x quarter-rounded hours');
select t.ok((select completed_shifts = 1 and on_time_shifts = 1 and rating_average = 5 and tier2_invited_at is null from public.worker_compliance), 'worker stats updated');

select t.as_service();
update public.payouts set status = 'paid', stripe_payment_intent_id = 'pi_shift_a' where id = :'payout_a';
select t.ok((select available_cents = 12375 from public.wallets where user_id = 'cccccccc-0000-4000-8000-000000000001'), 'shift pay landed in wallet');
select t.ok((select count(*) = 1 from public.ledger_entries where reference_type = 'payout' and reference_id = :'payout_a'), 'one shift_earnings entry');
select public.wallet_post_entry(w.id, 'credit', 12375, 'shift_earnings', 'dup', 'payout', :'payout_a') from public.wallets w where w.user_id = 'cccccccc-0000-4000-8000-000000000001';
select t.ok((select available_cents = 12375 from public.wallets where user_id = 'cccccccc-0000-4000-8000-000000000001'), 'duplicate payout posting is a no-op');
select t.ok((select amount_cents = 5775 from public.treasury_allocations where source_type = 'payout' and source_id = :'payout_a'), 'margin to platform');
select t.throws(format($$update public.payouts set status = 'pending' where id = %L$$, :'payout_a'), 'INVALID_STATUS_TRANSITION');
select t.throws(format($$update public.payouts set total_paid_to_worker_cents = 1 where id = %L$$, :'payout_a'), 'FORBIDDEN_COLUMN');

-- ============================================================ shift B -> tier-2 invite
select t.as_user('bbbbbbbb-0000-4000-8000-000000000001');
insert into public.shifts (id, location, lat, lng, position_title, tier_required, scheduled_start, scheduled_end)
values ('eeeeeeee-0000-4000-8000-00000000000b', 'Store 1142', 33.7738, -84.3530, 'Lot maintenance', 1, now() - interval '1 hour', now() + interval '3 hours');
select t.as_user('cccccccc-0000-4000-8000-000000000001');
select t.ok(public.claim_shift('eeeeeeee-0000-4000-8000-00000000000b', auth.uid()), 'claim B');
select t.as_user('bbbbbbbb-0000-4000-8000-000000000001');
select public.approve_shift('eeeeeeee-0000-4000-8000-00000000000b', 4, true);
select t.as_user('cccccccc-0000-4000-8000-000000000001');
select t.ok((select rating_average = 4.5 and tier2_invited_at is not null from public.worker_compliance), 'tier-2 invite after 2 on-time shifts at 4.5');
select t.ok((select count(*) = 1 from public.notifications where kind = 'shifts.tier2_invite' and body like '%never taken out of your pay%'), 'invite says platform pays the check');
select t.ok(public.evaluate_tier2_eligibility(auth.uid()), 'eligibility true');

-- ============================================================ background check (FCRA)
select t.as_user('aaaaaaaa-0000-4000-8000-000000000001');
select t.throws($$select public.order_background_check('cccccccc-0000-4000-8000-000000000001')$$, 'FCRA_CONSENT_REQUIRED', 'no check without standalone FCRA consent');
select t.as_user('cccccccc-0000-4000-8000-000000000001');
insert into public.consents (kind, text_version) values ('fcra_disclosure', 'fcra-2026-10-16');
select t.ok((select fcra_disclosure_accepted_at is not null from public.worker_compliance), 'FCRA consent timestamp on compliance');
select t.as_user('aaaaaaaa-0000-4000-8000-000000000001');
insert into public.background_checks (worker_id, provider_report_id, status, cost_cents, paid_by)
values ('cccccccc-0000-4000-8000-000000000001', 'rpt_devon', 'pending', 0, 'platform') returning id as bg1, cost_cents as bg1_cost \gset
select t.ok(:bg1_cost = 2500, 'platform pays the configured check cost');
select t.ok((select background_check_status = 'pending' from public.worker_compliance where user_id = 'cccccccc-0000-4000-8000-000000000001'), 'compliance pending');
select t.ok((select count(*) = 1 from public.treasury_allocations where source_type = 'background_check' and amount_cents = 2500), 'check cost recorded against platform margin');
select t.throws($$update public.worker_compliance set background_check_status = 'passed' where user_id = 'cccccccc-0000-4000-8000-000000000001'$$, 'FORBIDDEN_COLUMN', 'admin cannot set status directly');
select t.as_service();
select t.throws($$update public.worker_compliance set background_check_status = 'failed' where user_id = 'cccccccc-0000-4000-8000-000000000001'$$, 'FORBIDDEN_COLUMN', 'webhook cannot reject directly');
select public.record_background_check_result('rpt_devon', 'consider');
select t.ok((select background_check_status = 'consider' from public.worker_compliance where user_id = 'cccccccc-0000-4000-8000-000000000001'), 'consider goes to review');
select t.throws(format($$update public.background_checks set adjudication = 'final_adverse_sent' where id = %L$$, :'bg1'), 'INVALID_ADJUDICATION', 'no skipping the pre-adverse notice');
select t.throws(format($$update public.background_checks set adjudication = 'pre_adverse_sent' where id = %L$$, :'bg1'), 'HUMAN_REVIEW_REQUIRED', 'webhook cannot start adverse action');
select t.as_user('aaaaaaaa-0000-4000-8000-000000000001');
select public.review_background_check('cccccccc-0000-4000-8000-000000000001', 'pre_adverse');
select t.ok((select pre_adverse_sent_at is not null and final_adverse_eligible_at >= now() + interval '5 days' and reviewed_by = auth.uid()
             from public.background_checks where id = :'bg1'), 'pre-adverse notice + 5 business day wait');
select t.throws($$select public.review_background_check('cccccccc-0000-4000-8000-000000000001', 'final_adverse')$$, 'ADVERSE_ACTION_WAITING_PERIOD');
select t.ok(public.review_background_check('cccccccc-0000-4000-8000-000000000001', 'clear') = 'passed', 'admin clears after dispute');

-- Final adverse path for Jo: simulate the waiting period having elapsed.
select t.as_user('cccccccc-0000-4000-8000-000000000002');
insert into public.consents (kind, text_version) values ('fcra_disclosure', 'fcra-2026-10-16');
select t.as_service();
select public.order_background_check('cccccccc-0000-4000-8000-000000000002', 'cand_jo', 'rpt_jo') as bg_jo \gset
select public.record_background_check_result('rpt_jo', 'consider');
select t.as_user('aaaaaaaa-0000-4000-8000-000000000001');
select public.review_background_check('cccccccc-0000-4000-8000-000000000002', 'pre_adverse');
select t.as_db();
set session_replication_role = replica;
update public.background_checks set pre_adverse_sent_at = now() - interval '9 days', final_adverse_eligible_at = now() - interval '1 day' where id = :'bg_jo';
set session_replication_role = origin;
select t.as_user('aaaaaaaa-0000-4000-8000-000000000001');
select t.ok(public.review_background_check('cccccccc-0000-4000-8000-000000000002', 'final_adverse') = 'failed', 'final adverse after the wait');
select t.ok((select count(*) = 2 from public.audit_log where action = 'background_check.adjudicated' and entity_id = :'bg_jo'), 'each human step audited');
select t.as_user('cccccccc-0000-4000-8000-000000000002');
select t.ok((select count(*) = 2 from public.notifications where kind in ('compliance.pre_adverse', 'compliance.final_adverse')), 'worker received both notices');

-- ============================================================ drug screens
select t.as_user('aaaaaaaa-0000-4000-8000-000000000001');
select t.throws($$select public.record_drug_screen('cccccccc-0000-4000-8000-000000000001', 'LOT-1', 'negative', 'devon/1.jpg', now(), null)$$, 'DRUG_SCREEN_CONSENT_REQUIRED');
select t.throws($$select public.record_drug_screen('aaaaaaaa-0000-4000-8000-000000000001', 'LOT-1', 'negative', 'x.jpg', now(), null)$$, 'COLLECTOR_IS_WORKER');
select t.as_user('cccccccc-0000-4000-8000-000000000001');
insert into public.consents (kind, text_version) values ('drug_screen', 'drug-2026-10-16');
select t.throws($$select public.record_drug_screen('cccccccc-0000-4000-8000-000000000001', 'LOT-1', 'negative', 'devon/1.jpg', now(), null)$$, 'FORBIDDEN', 'non-admin cannot record');
select t.as_user('aaaaaaaa-0000-4000-8000-000000000001');
select t.throws($$select public.record_drug_screen('cccccccc-0000-4000-8000-000000000001', 'LOT-1', 'negative', '', now(), null)$$, 'EVIDENCE_REQUIRED');
select t.throws($$select public.record_drug_screen('cccccccc-0000-4000-8000-000000000001', 'LOT-1', 'negative', 'devon/1.jpg', now(), null)$$, 'EVIDENCE_NOT_FOUND');
insert into storage.objects (bucket_id, name) values ('drug-screen-evidence', 'devon/1.jpg'), ('drug-screen-evidence', 'devon/2.jpg'), ('drug-screen-evidence', 'devon/lab.pdf');
select public.record_drug_screen('cccccccc-0000-4000-8000-000000000001', 'LOT-1', 'non_negative', 'drug-screen-evidence/devon/1.jpg', now(), 'faint line') as dlog1 \gset
select t.ok((select drug_screen_status = 'pending' and compliance_tier = 1 from public.worker_compliance where user_id = 'cccccccc-0000-4000-8000-000000000001'), 'rapid non-negative = pending, not failed');
update public.drug_screen_logs set result = 'negative' where id = :'dlog1';
select t.ok((select result = 'non_negative' from public.drug_screen_logs where id = :'dlog1'), 'admin cannot edit a result (RLS)');
select t.as_service();
select t.throws(format($$update public.drug_screen_logs set result = 'negative' where id = %L$$, :'dlog1'), 'APPEND_ONLY', 'no override to passed, even for the service role');
select t.as_user('aaaaaaaa-0000-4000-8000-000000000001');
select public.record_drug_screen('cccccccc-0000-4000-8000-000000000001', 'LOT-2', 'negative', 'devon/2.jpg', now(), null);
select t.ok((select drug_screen_status = 'passed' and compliance_tier = 2 from public.worker_compliance where user_id = 'cccccccc-0000-4000-8000-000000000001'),
  'negative + background passed + invited -> tier 2');
select t.ok((select count(*) = 2 from public.treasury_allocations where source_type = 'drug_screen' and amount_cents = 500), 'kit costs platform-paid');

select t.as_user('cccccccc-0000-4000-8000-000000000001');
select t.ok(exists (select 1 from public.shifts where id = 'eeeeeeee-0000-4000-8000-000000000002'), 'tier-2 worker now sees tier-2 shift');
select t.ok((select count(*) = 2 from public.drug_screen_logs), 'worker sees own screen history');
select t.ok(public.claim_shift('eeeeeeee-0000-4000-8000-000000000002', auth.uid()), 'tier-2 claim works');

-- lab-confirmed failure drops back to tier 1
select t.as_user('aaaaaaaa-0000-4000-8000-000000000002');
insert into public.drug_screen_logs (worker_id, collector_id, collected_at, kit_lot_number, result, screen_type, evidence_path, worker_consent_at, consent_id)
select 'cccccccc-0000-4000-8000-000000000001', auth.uid(), now(), 'LAB-ACC-9', 'non_negative', 'lab_confirmation', 'devon/lab.pdf', now(), id
  from public.consents where kind = 'drug_screen' and user_id = 'cccccccc-0000-4000-8000-000000000001';
select t.ok((select drug_screen_status = 'failed' and compliance_tier = 1 from public.worker_compliance where user_id = 'cccccccc-0000-4000-8000-000000000001'), 'lab-confirmed failure -> tier 1');

-- ============================================================ SMS dispatch + claim by code
select t.as_user('bbbbbbbb-0000-4000-8000-000000000001');
insert into public.shifts (id, location, lat, lng, position_title, tier_required, scheduled_start, scheduled_end, is_emergency)
values ('eeeeeeee-0000-4000-8000-00000000000d', 'Store 1142', 33.7738, -84.3530, 'General labor', 1, now() + interval '3 days', now() + interval '3 days 4 hours', true);
select t.throws($$select * from public.create_dispatches('eeeeeeee-0000-4000-8000-00000000000d')$$, 'FORBIDDEN', 'manager cannot run dispatch directly');
select t.as_service();
-- Jo had a final adverse action: excluded. Add another eligible nearby worker by restoring W4 opt-in.
update public.users set sms_opt_in = true where id = 'cccccccc-0000-4000-8000-000000000004';
select count(*) as n_dispatched from public.create_dispatches('eeeeeeee-0000-4000-8000-00000000000d') \gset
select t.ok(:n_dispatched = 2, 'dispatched to Devon + No Texts (now opted in), not Jo (adverse), not far worker');
select t.ok((select count(*) = 0 from public.create_dispatches('eeeeeeee-0000-4000-8000-00000000000d')), 'no duplicate dispatches');
select t.ok((select count(distinct claim_code) = 2 and bool_and(claim_code ~ '^[0-9]{4}$' and expires_at > now() + interval '29 minutes')
             from public.shift_dispatches where shift_id = 'eeeeeeee-0000-4000-8000-00000000000d'), 'unique 4-digit codes, 30-min expiry');
select claim_code as devon_code from public.shift_dispatches where shift_id = 'eeeeeeee-0000-4000-8000-00000000000d' and user_id = 'cccccccc-0000-4000-8000-000000000001' \gset
select claim_code as quiet_code from public.shift_dispatches where shift_id = 'eeeeeeee-0000-4000-8000-00000000000d' and user_id = 'cccccccc-0000-4000-8000-000000000004' \gset
select t.ok(public.claim_shift_by_code('+14045550001', '0000') is null or :'devon_code' = '0000', 'wrong code -> null');
select t.ok(public.claim_shift_by_code('+14045550004', :'devon_code') is null or :'devon_code' = :'quiet_code', 'code bound to the phone it was sent to');
select t.ok(public.claim_shift_by_code('+1 (404) 555-0001', :'devon_code') = 'eeeeeeee-0000-4000-8000-00000000000d', 'SMS claim works');
select t.ok(public.claim_shift_by_code('+14045550004', :'quiet_code') is null, 'second SMS claim gets null');
select t.ok((select array_agg(outcome order by user_id) = array['claimed', 'shift_filled'] from public.shift_dispatches where shift_id = 'eeeeeeee-0000-4000-8000-00000000000d'), 'dispatch outcomes recorded');
select t.as_user('cccccccc-0000-4000-8000-000000000001');
select t.throws($$select public.claim_shift_by_code('+14045550001', '1234')$$, 'permission denied%', 'SMS claim is service-role only');

-- STOP keyword + phone change
select t.as_service();
update public.users set sms_opt_in = false where id = 'cccccccc-0000-4000-8000-000000000001';
select t.ok((select count(*) = 0 from public.consents where user_id = 'cccccccc-0000-4000-8000-000000000001' and kind = 'sms' and revoked_at is null), 'STOP revokes SMS consent');
select t.ok((select sms_opt_out_at is not null from public.users where id = 'cccccccc-0000-4000-8000-000000000001'), 'opt-out timestamped');
select t.as_user('cccccccc-0000-4000-8000-000000000004');
update public.users set phone_e164 = '+14045550044' where id = auth.uid();
select t.ok((select not sms_opt_in from public.users where id = auth.uid()), 'new phone number needs fresh SMS consent');

-- Release + cancel
select t.as_user('cccccccc-0000-4000-8000-000000000001');
update public.shifts set status = 'open', claimed_by = null where id = 'eeeeeeee-0000-4000-8000-00000000000d';
select t.as_db();
select t.ok((select status = 'open' and claimed_by is null and claimed_at is null and claimed_by_name is null from public.shifts where id = 'eeeeeeee-0000-4000-8000-00000000000d'), 'worker released shift before start');
select t.ok((select count(*) = 1 from public.notifications where kind = 'shift.released'), 'manager told about release');
select t.as_user('bbbbbbbb-0000-4000-8000-000000000001');
update public.shifts set status = 'canceled' where id = 'eeeeeeee-0000-4000-8000-00000000000d';
select t.ok((select canceled_at is not null from public.shifts where id = 'eeeeeeee-0000-4000-8000-00000000000d'), 'manager canceled');
select t.throws($$update public.shifts set status = 'open' where id = 'eeeeeeee-0000-4000-8000-00000000000d'$$, 'INVALID_STATUS_TRANSITION');

-- ============================================================ leads
select t.as_user('dddddddd-0000-4000-8000-000000000001');
select t.ok((select count(*) = 0 from public.lead_sources), 'members cannot see leads');
select t.as_db();
select t.throws($$update public.lead_sources set enabled = true where key = 'indeed'$$, '%lead_sources_license_required%', 'prohibited-scraping sources need a license');
select t.as_service();
insert into public.lead_targets (source, company_name, job_title, location, url, urgency_keywords, contact_email, dedupe_hash)
values ('jsonld', 'Example Market', 'Overnight stocker', 'Atlanta, GA', 'https://example.com/jobs/1', array['immediately'], 'hiring@examplemarket.com', repeat('b', 32))
returning id as lead1 \gset
select t.throws($$insert into public.lead_targets (source, company_name, job_title, url, dedupe_hash) values ('jsonld', 'X', 'Y', 'https://x.com', repeat('b', 32))$$, 'duplicate key%', 'dedupe_hash unique');
insert into public.outreach_drafts (lead_id, subject, body, status) values (:'lead1', 'Coverage for call-outs', 'Hi team...', 'sent') returning id as draft1, status as draft1_status \gset
select t.ok(:'draft1_status' = 'draft', 'drafts start as draft');
select t.throws(format($$update public.outreach_drafts set status = 'approved' where id = %L$$, :'draft1'), 'HUMAN_APPROVAL_REQUIRED', 'the job cannot approve');
select t.as_user('aaaaaaaa-0000-4000-8000-000000000001');
select t.throws(format($$update public.outreach_drafts set status = 'approved' where id = %L$$, :'draft1'), 'CAN_SPAM_FOOTER_REQUIRED');
update public.outreach_drafts set body = 'Hi team... EzWerkz, 100 Example St, Atlanta GA. Reply STOP or click unsubscribe to opt out.' where id = :'draft1';
update public.outreach_drafts set status = 'approved' where id = :'draft1';
select t.ok((select approved_by = auth.uid() and approved_at is not null from public.outreach_drafts where id = :'draft1'), 'human approval recorded');
insert into public.email_suppressions (domain, reason) values ('examplemarket.com', 'unsubscribe');
select t.as_service();
update public.outreach_drafts set status = 'sent' where id = :'draft1';
select t.ok((select status = 'suppressed' from public.outreach_drafts where id = :'draft1'), 'suppression list checked before send');

-- ============================================================ structural checks
select t.as_db();
select t.ok((select count(*) = 0 from pg_tables where schemaname = 'public' and not rowsecurity), 'RLS enabled on every public table');
select t.ok((select count(*) = 0 from pg_tables pt where schemaname = 'public'
              and not exists (select 1 from pg_policies p where p.schemaname = 'public' and p.tablename = pt.tablename)), 'every public table has explicit policies');
select t.ok((select count(*) = 0 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname in ('public', 'private') and p.prosecdef and p.proconfig is null), 'every SECURITY DEFINER function pins search_path');
select t.ok((select count(*) = 2 from pg_publication_tables where pubname = 'supabase_realtime' and tablename in ('shifts', 'chat_messages')), 'realtime publication');
select t.ok((select count(*) = 2 and bool_and(not public) from storage.buckets where id in ('bill-uploads', 'drug-screen-evidence')), 'private buckets');
select t.ok((select count(*) = 0 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'public' and has_function_privilege('anon', p.oid, 'execute')
                and p.proname in ('claim_shift', 'approve_shift', 'record_drug_screen', 'wallet_post_entry', 'create_dispatches',
                                  'workers_within_radius', 'claim_shift_by_code', 'record_membership_payment', 'sweep_membership_from_wallet',
                                  'apply_credit_level_up', 'evaluate_tier2_eligibility')), 'anon cannot execute any RPC');
select 'ALL TESTS PASSED' as result;
