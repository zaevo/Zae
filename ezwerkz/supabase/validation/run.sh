#!/usr/bin/env bash
# Validates the migrations against a plain local Postgres (15+), no Supabase CLI
# needed. Creates a throwaway database, applies a Supabase stand-in, every
# migration in order, the seed (twice, to prove idempotency), the functional
# test suite and a two-session claim_shift race test.
#
# Usage:  PGHOST=... PGPORT=... PGUSER=<superuser> supabase/validation/run.sh [dbname]
#
# PostGIS: if the server has PostGIS, it is used as-is. Otherwise the stub in
# supabase_stub.sql provides the geography surface the migrations use, and the
# CREATE EXTENSION postgis line / GIST indexes are swapped for the run only.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DB="${1:-ezwerkz_validation}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PSQL=(psql -X -q -v ON_ERROR_STOP=1)

"${PSQL[@]}" -d postgres -c "drop database if exists $DB" -c "create database $DB" >/dev/null

HAS_POSTGIS=$("${PSQL[@]}" -d "$DB" -tAc "select count(*) from pg_available_extensions where name = 'postgis'")
if [[ "$HAS_POSTGIS" == "1" ]]; then
  # Real PostGIS: drop the stub section, keep everything else.
  sed '/^-- -* PostGIS stub/,/^-- -* auth$/{/^-- -* auth$/!d}' "$HERE/supabase_stub.sql" > "$WORK/stub.sql"
else
  cp "$HERE/supabase_stub.sql" "$WORK/stub.sql"
fi
"${PSQL[@]}" -d "$DB" -1 -f "$WORK/stub.sql" 2>&1 | grep -v -E 'is only a shell|wal_level|HINT:  Set wal' || true

for f in "$ROOT"/migrations/*.sql; do
  b="$(basename "$f")"
  if [[ "$HAS_POSTGIS" == "1" ]]; then
    cp "$f" "$WORK/$b"
  else
    sed -e 's/^create extension if not exists postgis with schema extensions;$/-- postgis stubbed for validation/' \
        -e 's/using gist (/using btree (/' "$f" > "$WORK/$b"
  fi
  echo "apply  $b"
  "${PSQL[@]}" -d "$DB" -1 -f "$WORK/$b"
done
echo "apply  seed.sql (x2)"
"${PSQL[@]}" -d "$DB" -1 -f "$ROOT/seed.sql"
"${PSQL[@]}" -d "$DB" -1 -f "$ROOT/seed.sql"

"${PSQL[@]}" -d "$DB" -f "$HERE/test_helpers.sql"
if ! "${PSQL[@]}" -d "$DB" -f "$HERE/schema_test.sql" > "$WORK/out.txt" 2> "$WORK/err.txt"; then
  grep -E 'ERROR|FAIL' "$WORK/err.txt" | head -5
  exit 1
fi
echo "tests  $(grep -c 'NOTICE:  ok' "$WORK/err.txt") assertions passed"

# Race: session A claims and holds its transaction; session B must get false.
"${PSQL[@]}" -d "$DB" >/dev/null <<'SQL'
select t.as_user('bbbbbbbb-0000-4000-8000-000000000001');
insert into public.shifts (id, location, lat, lng, position_title, tier_required, scheduled_start, scheduled_end)
values ('eeeeeeee-0000-4000-8000-0000000000ff', 'Store 1142', 33.7738, -84.3530, 'Stocking', 1,
        now() + interval '5 days', now() + interval '5 days 4 hours');
SQL
"${PSQL[@]}" -d "$DB" -tA > "$WORK/race_a.txt" <<'SQL' &
begin;
select t.as_user('cccccccc-0000-4000-8000-000000000001');
select 'A:' || public.claim_shift('eeeeeeee-0000-4000-8000-0000000000ff', 'cccccccc-0000-4000-8000-000000000001');
select pg_sleep(2);
commit;
SQL
sleep 1
"${PSQL[@]}" -d "$DB" -tA > "$WORK/race_b.txt" <<'SQL'
select t.as_user('cccccccc-0000-4000-8000-000000000003');
select 'B:' || public.claim_shift('eeeeeeee-0000-4000-8000-0000000000ff', 'cccccccc-0000-4000-8000-000000000003');
SQL
wait
RACE="$(grep -h -E '^(A|B):' "$WORK/race_a.txt" "$WORK/race_b.txt" | tr '\n' ' ')"
if [[ "$RACE" != "A:true B:false " ]]; then
  echo "race   FAILED: $RACE"
  exit 1
fi
echo "race   ok (A:true, B:false)"
echo "OK"
