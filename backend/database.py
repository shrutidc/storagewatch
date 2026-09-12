import psycopg2
from psycopg2.extras import RealDictCursor
import os
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

def insert_metrics(metrics):
    """Insert filesystem metrics into database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO filesystem_metrics (
            time, hostname, filesystem, filesystem_type,
            total_bytes, used_bytes, free_bytes, used_percent,
            read_bytes_per_sec, write_bytes_per_sec
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
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

def get_latest_metrics(filesystem="/"):
    """Get most recent metrics record for a given volume."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM filesystem_metrics
        WHERE filesystem = %s
        ORDER BY time DESC LIMIT 1
    """, (filesystem,))

    result = cursor.fetchone()
    cursor.close()
    conn.close()

    return result

def get_metrics_history(limit=100, filesystem="/"):
    """Get historical metrics records for a given volume."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM filesystem_metrics
        WHERE filesystem = %s
        ORDER BY time DESC LIMIT %s
    """, (filesystem, limit))

    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return results

def get_all_volumes_latest():
    """Get the most recent metrics record for each distinct monitored volume."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT DISTINCT ON (filesystem) *
        FROM filesystem_metrics
        ORDER BY filesystem, time DESC
    """)

    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return results

def insert_alert(hostname, alert_type, severity, message, metric_value, ai_explanation=None):
    """Insert an alert record. Returns the new alert's id."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO alerts (hostname, alert_type, severity, message, metric_value, ai_explanation)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (hostname, alert_type, severity, message, metric_value, ai_explanation))

    alert_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()

    return alert_id

def update_alert_explanation(alert_id, ai_explanation):
    """Attach an AI explanation to an existing alert (generated asynchronously)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE alerts SET ai_explanation = %s WHERE id = %s
    """, (ai_explanation, alert_id))

    conn.commit()
    cursor.close()
    conn.close()

def get_recent_alerts(limit=10):
    """Get recent unresolved alerts."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM alerts
        WHERE resolved = FALSE
        ORDER BY created_at DESC LIMIT %s
    """, (limit,))

    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return results
