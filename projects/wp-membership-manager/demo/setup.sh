#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d --wait --wait-timeout 180
# Apache copies WordPress into the shared volume on first startup.
for attempt in $(seq 1 60); do
  if docker compose run --rm cli config path >/dev/null 2>&1; then break; fi
  sleep 2
done
if ! docker compose run --rm cli core is-installed >/dev/null 2>&1; then
  docker compose run --rm cli core install --url="http://localhost:${WP_PORT:-8080}" --title='Demo Association' --admin_user=demo --admin_password=local-demo-only --admin_email=admin@example.test --skip-email
fi
docker compose run --rm cli plugin activate wp-membership-manager
docker compose run --rm cli eval-file wp-content/plugins/wp-membership-manager/demo/seed.php
printf 'WordPress: http://localhost:%s/wp-admin/admin.php?page=wpmm\nMailpit: http://localhost:%s\nLogin: demo / local-demo-only (local synthetic demo only)\n' "${WP_PORT:-8080}" "${MAILPIT_PORT:-8025}"
