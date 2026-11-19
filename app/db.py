"""Tiny Postgres layer. A new connection per request keeps failover simple: after the database host
changes (replica promoted), the next request simply connects to the new primary."""
import json
import os

try:
    import psycopg
    Error = psycopg.Error
except ImportError:  # unit tests run without the driver
    psycopg = None

    class Error(Exception):
        pass

SCHEMA = """CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    customer TEXT NOT NULL,
    items JSONB NOT NULL,
    total INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now())"""


def url():
    return os.getenv("DATABASE_URL", "")


def enabled():
    return bool(url()) and psycopg is not None


def connect():
    return psycopg.connect(url(), connect_timeout=2, autocommit=True)


def ensure_schema(c):
    # least-privilege users (e.g. Vault dynamic credentials) may not create tables, so only create if missing
    if c.execute("SELECT to_regclass('orders')").fetchone()[0] is None:
        c.execute(SCHEMA)


def insert_order(customer, items, total):
    with connect() as c:
        ensure_schema(c)
        return c.execute("INSERT INTO orders (customer, items, total) VALUES (%s, %s, %s) RETURNING id",
                         (customer, json.dumps(items), total)).fetchone()[0]


def order_stats():
    with connect() as c:
        ensure_schema(c)
        n, last, revenue = c.execute("SELECT count(*), coalesce(max(id), 0), coalesce(sum(total), 0) "
                                     "FROM orders").fetchone()
        return {"orders": n, "last_id": last, "revenue": revenue}


def status():
    if not enabled():
        return "not configured"
    try:
        with connect() as c:
            c.execute("SELECT 1")
        return "ok"
    except Error:
        return "unavailable"


def current_user():
    if not enabled():
        return None
    try:
        with connect() as c:
            return c.execute("SELECT current_user").fetchone()[0]
    except Error:
        return None
