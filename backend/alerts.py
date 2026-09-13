from collections import defaultdict, deque

# One trailing window per machine. A single shared window let one machine's
# writes set another's baseline once several agents report to one backend.
# ponytail: in-process, so baselines reset on restart; persist them if that matters.
write_history = defaultdict(lambda: deque(maxlen=20))

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

def check_io_anomaly(write_bytes_per_sec, key=None):
    history = write_history[key]

    # Baseline from the previous samples only. Averaging in the current one
    # dampens the very spike being measured: a 7x burst read as 3.2x on a
    # five-sample window and never fired.
    baseline = sum(history) / len(history) if len(history) >= 5 else 0
    history.append(write_bytes_per_sec)

    if not baseline:
        return None

    ratio = write_bytes_per_sec / baseline

    if ratio > 4:
        return {
            "type": "HIGH_WRITE_ACTIVITY",
            "severity": "warning",
            "message": (f"Write activity {ratio:.1f}x baseline "
                        f"({write_bytes_per_sec / 1e6:.0f} MB/s vs {baseline / 1e6:.0f} MB/s)"),
            "ratio": ratio
        }
    return None

def detect_anomalies(metrics, owner_sub=None):
    alerts = []

    cap_alert = check_capacity_alert(metrics.used_percent)
    if cap_alert:
        alerts.append(cap_alert)

    # Write throughput is a system-wide reading (macOS has no true per-volume
    # I/O), attached to every volume's payload. Only check it once per cycle,
    # on the primary volume, to avoid double-counting the same sample into
    # the baseline and firing duplicate alerts across volumes.
    if metrics.filesystem == "/":
        io_alert = check_io_anomaly(metrics.write_bytes_per_sec,
                                    (owner_sub, metrics.hostname))
        if io_alert:
            alerts.append(io_alert)

    return alerts
