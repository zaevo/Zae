-- Minimal stand-in for what a Supabase project provides before user migrations
-- run (roles, auth/storage schemas, realtime publication, default grants) plus a
-- text-backed PostGIS stub for machines without PostGIS. Validation only: never
-- apply this to a real Supabase project.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin noinherit; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin noinherit; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role nologin noinherit bypassrls; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticator') then create role authenticator login noinherit; end if;
end $$;
grant anon, authenticated, service_role to authenticator;

create schema extensions;
grant usage on schema extensions to anon, authenticated, service_role;
alter default privileges in schema extensions grant execute on functions to anon, authenticated, service_role;

-- ---------------------------------------------------------------- PostGIS stub
-- PostGIS is not installed locally. These text-backed types/functions accept the
-- same SQL surface the migrations use (geography(Point,4326), ST_MakePoint,
-- ST_SetSRID, casts, ST_X/ST_Y, ST_Distance, ST_DWithin) and compute real
-- haversine distances so radius queries can be exercised.
create type extensions.geometry;
create function extensions.geometry_in(cstring) returns extensions.geometry language internal immutable strict as 'textin';
create function extensions.geometry_out(extensions.geometry) returns cstring language internal immutable strict as 'textout';
create function extensions.geometry_typmod_in(cstring[]) returns integer language plpgsql immutable strict as $$ begin return 0; end $$;
create type extensions.geometry (input = extensions.geometry_in, output = extensions.geometry_out, typmod_in = extensions.geometry_typmod_in, internallength = variable, storage = extended);

create type extensions.geography;
create function extensions.geography_in(cstring) returns extensions.geography language internal immutable strict as 'textin';
create function extensions.geography_out(extensions.geography) returns cstring language internal immutable strict as 'textout';
create function extensions.geography_typmod_in(cstring[]) returns integer language plpgsql immutable strict as $$ begin return 4326; end $$;
create type extensions.geography (input = extensions.geography_in, output = extensions.geography_out, typmod_in = extensions.geography_typmod_in, internallength = variable, storage = extended);

create cast (extensions.geography as text) without function;
create cast (extensions.geometry as text) without function;
create cast (text as extensions.geography) without function;
create cast (text as extensions.geometry) without function;

create function extensions.st_makepoint(double precision, double precision) returns extensions.geometry
  language sql immutable strict as $$ select format('POINT(%s %s)', $1, $2)::extensions.geometry $$;
create function extensions.st_setsrid(extensions.geometry, integer) returns extensions.geometry
  language sql immutable strict as $$ select format('SRID=%s;%s', $2, regexp_replace($1::text, '^SRID=[0-9]+;', ''))::extensions.geometry $$;
create function extensions.geography(extensions.geometry) returns extensions.geography
  language sql immutable strict as $$ select (case when $1::text ~ '^SRID=' then $1::text else 'SRID=4326;' || $1::text end)::extensions.geography $$;
create function extensions.geometry(extensions.geography) returns extensions.geometry
  language sql immutable strict as $$ select $1::text::extensions.geometry $$;
create cast (extensions.geometry as extensions.geography) with function extensions.geography(extensions.geometry) as implicit;
create cast (extensions.geography as extensions.geometry) with function extensions.geometry(extensions.geography);

create function extensions._coord(text, integer) returns double precision language sql immutable strict as $$
  select (regexp_match($1, 'POINT\(\s*(-?[0-9.eE+-]+)\s+(-?[0-9.eE+-]+)\s*\)'))[$2]::double precision
$$;
create function extensions.st_x(extensions.geometry) returns double precision language sql immutable strict as $$ select extensions._coord($1::text, 1) $$;
create function extensions.st_y(extensions.geometry) returns double precision language sql immutable strict as $$ select extensions._coord($1::text, 2) $$;
create function extensions.st_distance(extensions.geography, extensions.geography) returns double precision
  language sql immutable strict as $$
  select 2 * 6371008.8 * asin(sqrt(
    power(sin(radians(extensions._coord($2::text, 2) - extensions._coord($1::text, 2)) / 2), 2)
    + cos(radians(extensions._coord($1::text, 2))) * cos(radians(extensions._coord($2::text, 2)))
    * power(sin(radians(extensions._coord($2::text, 1) - extensions._coord($1::text, 1)) / 2), 2)))
$$;
create function extensions.st_dwithin(extensions.geography, extensions.geography, double precision) returns boolean
  language sql immutable strict as $$ select extensions.st_distance($1, $2) <= $3 $$;

-- Comparison support so `IS DISTINCT FROM` works and the harness can swap GIST for btree.
create function extensions.geog_cmp(extensions.geography, extensions.geography) returns integer language sql immutable strict as $$ select bttextcmp($1::text, $2::text) $$;
create function extensions.geog_lt(extensions.geography, extensions.geography) returns boolean language sql immutable strict as $$ select $1::text < $2::text $$;
create function extensions.geog_le(extensions.geography, extensions.geography) returns boolean language sql immutable strict as $$ select $1::text <= $2::text $$;
create function extensions.geog_eq(extensions.geography, extensions.geography) returns boolean language sql immutable strict as $$ select $1::text = $2::text $$;
create function extensions.geog_ge(extensions.geography, extensions.geography) returns boolean language sql immutable strict as $$ select $1::text >= $2::text $$;
create function extensions.geog_gt(extensions.geography, extensions.geography) returns boolean language sql immutable strict as $$ select $1::text > $2::text $$;
create operator extensions.< (leftarg = extensions.geography, rightarg = extensions.geography, function = extensions.geog_lt);
create operator extensions.<= (leftarg = extensions.geography, rightarg = extensions.geography, function = extensions.geog_le);
create operator extensions.= (leftarg = extensions.geography, rightarg = extensions.geography, function = extensions.geog_eq);
create operator extensions.>= (leftarg = extensions.geography, rightarg = extensions.geography, function = extensions.geog_ge);
create operator extensions.> (leftarg = extensions.geography, rightarg = extensions.geography, function = extensions.geog_gt);
create operator class extensions.geography_btree_ops default for type extensions.geography using btree as
  operator 1 extensions.<, operator 2 extensions.<=, operator 3 extensions.=, operator 4 extensions.>=, operator 5 extensions.>,
  function 1 extensions.geog_cmp(extensions.geography, extensions.geography);

-- ---------------------------------------------------------------- auth
create schema auth;
grant usage on schema auth to anon, authenticated, service_role;
create table auth.users (
  id uuid primary key default gen_random_uuid(),
  email text,
  phone text,
  raw_user_meta_data jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);
create function auth.jwt() returns jsonb language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claim', true), ''), nullif(current_setting('request.jwt.claims', true), ''))::jsonb
$$;
create function auth.uid() returns uuid language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claim.sub', true), ''), (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'))::uuid
$$;
create function auth.role() returns text language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claim.role', true), ''), (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role'))::text
$$;
grant execute on all functions in schema auth to anon, authenticated, service_role;

-- ---------------------------------------------------------------- storage
create schema storage;
grant usage on schema storage to anon, authenticated, service_role;
create table storage.buckets (
  id text primary key,
  name text not null unique,
  owner uuid,
  public boolean default false,
  file_size_limit bigint,
  allowed_mime_types text[],
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create table storage.objects (
  id uuid primary key default gen_random_uuid(),
  bucket_id text references storage.buckets (id),
  name text,
  owner uuid,
  owner_id text,
  metadata jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique (bucket_id, name)
);
alter table storage.objects enable row level security;
create function storage.foldername(name text) returns text[] language plpgsql as $$
declare _parts text[];
begin
  select string_to_array(name, '/') into _parts;
  return _parts[1:array_length(_parts, 1) - 1];
end $$;
grant all on storage.objects to anon, authenticated, service_role;
grant select on storage.buckets to anon, authenticated, service_role;

-- ---------------------------------------------------------------- realtime
create publication supabase_realtime;

-- ---------------------------------------------------------------- public defaults (as Supabase configures them)
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
