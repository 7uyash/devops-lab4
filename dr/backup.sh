#!/usr/bin/env bash
# Logical backup of the shop database: pg_dump (custom format) -> local + offsite copy, SHA-256 checksum,
# retention of the last $KEEP backups. In production the offsite copy would go to object storage in another region.
set -euo pipefail
cd "$(dirname "$0")"
KEEP=${KEEP:-5}
mkdir -p backups offsite
ts=$(date -u +%Y%m%dT%H%M%SZ)
f="backups/shop-$ts.dump"
start=$(date +%s.%N)
docker compose exec -T db-primary pg_dump -U shop -d shop -Fc > "$f"
sha256sum "$f" > "$f.sha256"
cp "$f" "$f.sha256" offsite/
end=$(date +%s.%N)
rows=$(docker compose exec -T db-primary psql -U shop -d shop -Atc "SELECT count(*) FROM orders")
echo "$ts" > backups/LATEST
printf 'backup %s  size=%s  rows=%s  took=%.2fs\n' "$f" "$(du -h "$f" | cut -f1)" "$rows" "$(awk "BEGIN{print $end-$start}")"
# retention
ls -1t backups/shop-*.dump | tail -n +$((KEEP + 1)) | while read -r old; do rm -f "$old" "$old.sha256"; echo "pruned $old"; done
echo "{\"file\": \"$f\", \"rows\": $rows, \"time\": $end}" > backups/last.json
