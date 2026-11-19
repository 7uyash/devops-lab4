#!/usr/bin/env bash
# usage: switch.sh blue|green   - smoke-test the target environment, then move live traffic to it.
# nginx -s reload starts new workers with the new config and lets old workers finish their requests,
# so no request is dropped during the switch.
set -euo pipefail
cd "$(dirname "$0")"
target=$1
current=$(sed -E 's/.*\$live ([a-z]+);.*/\1/' active/active.conf)
echo "live: $current  ->  target: $target"
[ "$current" = "$target" ] && { echo "already live"; exit 0; }

echo "smoke test $target before the switch:"
for path in /health /api/products /; do
  code=$( (docker compose exec -T router wget -q -S -O /dev/null "http://$target:8000$path" 2>&1 || true) | awk '/HTTP\//{print $2}' | tail -1)
  echo "  GET $path -> $code"
  [ "$code" = "200" ] || { echo "SMOKE TEST FAILED - $target stays idle, traffic remains on $current"; exit 1; }
done

cp active/active.conf active/active.conf.bak
echo "set \$live $target;" > active/active.conf
if docker compose exec -T router nginx -t -q; then
  docker compose exec -T router nginx -s reload
  echo "SWITCHED: live traffic now on $target ($(date +%T.%3N))"
else
  mv active/active.conf.bak active/active.conf
  echo "nginx config invalid - switch aborted"; exit 1
fi
