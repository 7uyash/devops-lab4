#!/bin/sh
# runs once when the primary is initialised: replication user + slot-friendly pg_hba entry
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD '$REPLICATION_PASSWORD'"
echo "host replication replicator all scram-sha-256" >> "$PGDATA/pg_hba.conf"
