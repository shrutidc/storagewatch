"""Data access.

Every query is scoped to an owner — the Auth0 subject of the administrator
whose agent produced the data. `owner_sub` is the first positional argument on
every read and write rather than an optional filter, so an unscoped query that
would leak one user's machines to another can't be written by accident.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib
import json
import os
import secrets
from datetime import datetime

def get_connection():
    """Get a connection to Tiger Data."""
    return psycopg2.connect(os.getenv("TIGER_DATABASE_URL"))

def init_db():
    """Initialize database schema. Run once on startup."""
    conn = get_connection()
    cursor = conn.cursor()

    # Read and execute schema.sql
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r") as f:
        cursor.execute(f.read())

    conn.commit()
    cursor.close()
    conn.close()


# --- agent credentials -----------------------------------------------------

def _hash_token(token):
    """Agent tokens are 256 bits of randomness, so a fast digest is enough —
    there is no low-entropy password here for an attacker to grind against."""
    return hashlib.sha256(token.encode()).hexdigest()

def create_agent_token(owner_sub, label=None):
    """Mint an agent token for a user. Returns the plaintext, which is the only
    time it exists outside the agent's config — only the hash is stored."""
    token = secrets.token_urlsafe(32)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO agent_tokens (token_hash, owner_sub, label)
        VALUES (%s, %s, %s)
    """, (_hash_token(token), owner_sub, label))
    conn.commit()
    cursor.close()
    conn.close()

    return token

def resolve_agent_token(token):
    """Return the owner of an agent token, or None if it isn't a valid one."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE agent_tokens SET last_used_at = NOW()
        WHERE token_hash = %s
        RETURNING owner_sub
    """, (_hash_token(token),))
    row = cursor.fetchone()
    conn.commit()
    cursor.close()
    conn.close()

    return row[0] if row else None

def list_agent_tokens(owner_sub):
    """Metadata for a user's tokens. Never returns the tokens themselves."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT label, created_at, last_used_at FROM agent_tokens
        WHERE owner_sub = %s ORDER BY created_at DESC
    """, (owner_sub,))
    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return results


# --- machines --------------------------------------------------------------

def get_hosts(owner_sub):
    """The machines this user has reporting, most recently seen first."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT hostname, MAX(time) AS last_seen
        FROM filesystem_metrics
        WHERE owner_sub = %s
        GROUP BY hostname
        ORDER BY last_seen DESC
    """, (owner_sub,))
    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return results

def get_default_hostname(owner_sub):
    """The user's most recently reporting machine, used when no host is named."""
    hosts = get_hosts(owner_sub)
    return hosts[0]["hostname"] if hosts else None


# --- metrics ---------------------------------------------------------------

def insert_metrics(owner_sub, metrics):
    """Insert filesystem metrics into database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO filesystem_metrics (
            owner_sub, time, hostname, filesystem, filesystem_type,
            total_bytes, used_bytes, free_bytes, used_percent,
            read_bytes_per_sec, write_bytes_per_sec
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        owner_sub,
        metrics.timestamp,
        metrics.hostname,
        metrics.filesystem,
        metrics.filesystem_type,
        metrics.total_bytes,
        metrics.used_bytes,
        metrics.free_bytes,
        metrics.used_percent,
        metrics.read_bytes_per_sec,
        metrics.write_bytes_per_sec
    ))

    conn.commit()
    cursor.close()
    conn.close()

def get_latest_metrics(owner_sub, filesystem="/", hostname=None):
    """Most recent sample for one volume on one of the user's machines."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM filesystem_metrics
        WHERE owner_sub = %s AND filesystem = %s
          AND (%s::text IS NULL OR hostname = %s)
        ORDER BY time DESC LIMIT 1
    """, (owner_sub, filesystem, hostname, hostname))

    result = cursor.fetchone()
    cursor.close()
    conn.close()

    return result

def get_metrics_history(owner_sub, limit=100, filesystem="/", hostname=None):
    """Historical samples for one volume on one of the user's machines."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM filesystem_metrics
        WHERE owner_sub = %s AND filesystem = %s
          AND (%s::text IS NULL OR hostname = %s)
        ORDER BY time DESC LIMIT %s
    """, (owner_sub, filesystem, hostname, hostname, limit))

    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return results

def get_all_volumes_latest(owner_sub, hostname=None):
    """Latest sample per volume, for one of the user's machines."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT DISTINCT ON (filesystem) *
        FROM filesystem_metrics
        WHERE owner_sub = %s
          AND (%s::text IS NULL OR hostname = %s)
        ORDER BY filesystem, time DESC
    """, (owner_sub, hostname, hostname))

    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return results


# --- alerts ----------------------------------------------------------------

def insert_alert(owner_sub, hostname, alert_type, severity, message,
                 metric_value, ai_explanation=None):
    """Insert an alert record. Returns the new alert's id."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO alerts (owner_sub, hostname, alert_type, severity, message,
                            metric_value, ai_explanation)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (owner_sub, hostname, alert_type, severity, message, metric_value,
          ai_explanation))

    alert_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()

    return alert_id

def update_alert_explanation(alert_id, ai_explanation):
    """Attach an AI explanation to an existing alert (generated asynchronously).

    Not owner-scoped because the id comes from insert_alert on the same
    request, never from client input.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE alerts SET ai_explanation = %s WHERE id = %s
    """, (ai_explanation, alert_id))

    conn.commit()
    cursor.close()
    conn.close()

def get_recent_alerts(owner_sub, limit=10, hostname=None):
    """Unresolved alerts for the user's machines, newest first."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM alerts
        WHERE owner_sub = %s AND resolved = FALSE
          AND (%s::text IS NULL OR hostname = %s)
        ORDER BY created_at DESC LIMIT %s
    """, (owner_sub, hostname, hostname, limit))

    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return results


# --- disk / APFS inventory -------------------------------------------------

def save_system_info(owner_sub, hostname, data):
    """Upsert one machine's disk/APFS snapshot."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO system_info (owner_sub, hostname, updated_at, data)
        VALUES (%s, %s, NOW(), %s)
        ON CONFLICT (owner_sub, hostname)
        DO UPDATE SET updated_at = NOW(), data = EXCLUDED.data
    """, (owner_sub, hostname, json.dumps(data)))

    conn.commit()
    cursor.close()
    conn.close()

def get_system_info(owner_sub, hostname=None):
    """One machine's disk/APFS snapshot, or None if it hasn't reported."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT data FROM system_info
        WHERE owner_sub = %s AND (%s::text IS NULL OR hostname = %s)
        ORDER BY updated_at DESC LIMIT 1
    """, (owner_sub, hostname, hostname))
    row = cursor.fetchone()

    cursor.close()
    conn.close()

    return row[0] if row else None
