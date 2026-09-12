import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime

DATABASE_URL = os.getenv("TIGER_DATABASE_URL")

def get_connection():
    pass

def init_db():
    pass

def insert_metrics(metrics):
    pass

def get_latest_metrics():
    pass

def get_metrics_history(limit=100):
    pass

def insert_alert(hostname, alert_type, severity, message, metric_value):
    pass

def get_recent_alerts(limit=10):
    pass
