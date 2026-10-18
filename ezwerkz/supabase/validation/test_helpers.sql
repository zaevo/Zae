-- Test helpers for schema_test.sql (validation only).
create schema t;
grant usage on schema t to anon, authenticated, service_role;

create function t.ok(p_cond boolean, p_label text) returns void language plpgsql as $$
begin
  if p_cond is distinct from true then
    raise exception 'FAIL: %', p_label;
  end if;
  raise notice 'ok   %', p_label;
end $$;

create function t.throws(p_sql text, p_expected text, p_label text default null) returns void language plpgsql as $$
begin
  begin
    execute p_sql;
  exception when others then
    if sqlerrm like p_expected then
      raise notice 'ok   % (raised: %)', coalesce(p_label, p_expected), sqlerrm;
      return;
    end if;
    raise exception 'FAIL: % expected "%" got "%" :: %', coalesce(p_label, ''), p_expected, sqlerrm, p_sql;
  end;
  raise exception 'FAIL: % expected "%" but it succeeded :: %', coalesce(p_label, ''), p_expected, p_sql;
end $$;

-- Switch identity like PostgREST does: JWT claims + SET ROLE.
create function t.as_user(p_uid uuid) returns void language plpgsql as $$
begin
  execute 'reset role';
  perform set_config('request.jwt.claims', json_build_object('sub', p_uid, 'role', 'authenticated')::text, false);
  execute 'set role authenticated';
end $$;

create function t.as_service() returns void language plpgsql as $$
begin
  execute 'reset role';
  perform set_config('request.jwt.claims', '{"role":"service_role"}', false);
  execute 'set role service_role';
end $$;

create function t.as_anon() returns void language plpgsql as $$
begin
  execute 'reset role';
  perform set_config('request.jwt.claims', '{"role":"anon"}', false);
  execute 'set role anon';
end $$;

create function t.as_db() returns void language plpgsql as $$
begin
  execute 'reset role';
  perform set_config('request.jwt.claims', '', false);
end $$;

grant execute on all functions in schema t to anon, authenticated, service_role;
