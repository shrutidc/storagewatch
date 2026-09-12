from collections import deque

write_history = deque(maxlen=20)

def check_capacity_alert(used_percent):
    if used_percent >= 90:
        return {
            "type": "HIGH_CAPACITY",
            "severity": "critical",
            "message": f"Storage at {used_percent}% capacity"
        }
    elif used_percent >= 80:
        return {
            "type": "HIGH_CAPACITY",
            "severity": "warning",
            "message": f"Storage at {used_percent}% capacity"
        }
    return None

def check_io_anomaly(write_bytes_per_sec):
    write_history.append(write_bytes_per_sec)

    if len(write_history) < 5:
        return None

    avg = sum(write_history) / len(write_history)
    if avg == 0:
        return None

    ratio = write_bytes_per_sec / avg

    if ratio > 4:
        return {
            "type": "HIGH_WRITE_ACTIVITY",
            "severity": "warning",
            "message": f"Write activity {ratio:.1f}x baseline",
            "ratio": ratio
        }
    return None

def detect_anomalies(metrics):
    alerts = []

    cap_alert = check_capacity_alert(metrics.used_percent)
    if cap_alert:
        alerts.append(cap_alert)

    io_alert = check_io_anomaly(metrics.write_bytes_per_sec)
    if io_alert:
        alerts.append(io_alert)

    return alerts
