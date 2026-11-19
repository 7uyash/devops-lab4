#!/usr/bin/env bash
# Database failover: detect that the primary is down (3 failed health checks, 1 s apart),
# then promote the hot standby. The apps find the new primary by themselves (target_session_attrs).
set -euo pipefail
cd "$(dirname "$0")"
fails=0
while [ $fails -lt 3 ]; do
  if docker compose exec -T db-replica pg_isready -h db-primary -t 1 >/dev/null 2>&1; then
    fails=0
  else
    fails=$((fails + 1)); echo "$(date +%T.%3N) health check failed ($fails/3)"
  fi
  sleep 1
done
echo "$(date +%T.%3N) primary declared DOWN -> promoting db-replica"
docker compose exec -T db-replica psql -U shop -d shop -Atc "SELECT pg_promote(wait => true)"
echo "$(date +%T.%3N) db-replica promoted, in recovery: $(docker compose exec -T db-replica psql -U shop -d shop -Atc 'SELECT pg_is_in_recovery()')"
