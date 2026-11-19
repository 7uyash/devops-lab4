#!/usr/bin/env bash
# usage: restore.sh [--verify-only] [backup-file]
# Verifies the checksum (falls back to the offsite copy if the local one is damaged/missing) and restores.
# --verify-only restores into a scratch database (restore drill) and leaves production untouched.
set -euo pipefail
cd "$(dirname "$0")"
target=shop
if [ "${1:-}" = "--verify-only" ]; then target=restore_drill; shift; fi
f=${1:-backups/shop-$(cat backups/LATEST).dump}
if ! sha256sum -c "$f.sha256" >/dev/null 2>&1; then
  echo "local backup missing or corrupt -> using offsite copy"
  f="offsite/$(basename "$f")"
  (cd offsite && sha256sum -c "$(basename "$f").sha256")
else
  echo "checksum OK: $f"
fi
start=$(date +%s.%N)
psql() { docker compose exec -T db-primary psql -U shop -v ON_ERROR_STOP=1 "$@"; }
if [ "$target" != shop ]; then
  psql -d postgres -qc "DROP DATABASE IF EXISTS $target" -c "CREATE DATABASE $target"
fi
docker compose exec -T db-primary pg_restore -U shop -d "$target" --clean --if-exists --no-owner < "$f"
end=$(date +%s.%N)
rows=$(psql -d "$target" -Atc "SELECT count(*) FROM orders")
printf 'restored %s into database "%s": %s orders in %.2fs\n' "$f" "$target" "$rows" "$(awk "BEGIN{print $end-$start}")"
if [ "$target" != shop ]; then psql -d postgres -qc "DROP DATABASE $target"; fi
