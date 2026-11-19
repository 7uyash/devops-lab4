#!/usr/bin/env bash
# Pipeline step: write the app's role_id and a single-use, response-wrapped secret_id (TTL 120 s) into the
# directory that is mounted read-only into the app container at /run/secrets. Needs VT = deployer token.
set -euo pipefail
cd "$(dirname "$0")"
d=${APP_SECRETS_DIR:?}
V(){ docker compose exec -T -e VAULT_TOKEN="$VT" vault vault "$@"; }
V read -field=role_id auth/approle/role/shoplite-app/role-id > "$d/role_id.new"
V write -wrap-ttl=120s -field=wrapping_token -f auth/approle/role/shoplite-app/secret-id > "$d/secret_id.new"
chmod 444 "$d/role_id.new" "$d/secret_id.new"
mv -f "$d/role_id.new" "$d/role_id"; mv -f "$d/secret_id.new" "$d/secret_id"
echo "delivered role_id and wrapped secret_id to $d (mounted at /run/secrets)"
