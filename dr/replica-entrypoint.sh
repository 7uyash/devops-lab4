#!/bin/sh
# Hot standby: clone the primary with pg_basebackup (-R writes standby.signal + primary_conninfo),
# using a physical replication slot so the primary keeps WAL until the replica has received it.
set -e
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  until pg_basebackup -h db-primary -U replicator -D "$PGDATA" -R -X stream -C -S replica1 -v; do
    echo "waiting for primary..."; sleep 2; rm -rf "$PGDATA"
  done
  chmod 700 "$PGDATA"
fi
exec postgres -c hot_standby=on
