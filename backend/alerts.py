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

# A ratio alone fires on noise: on an idle Mac the baseline is near zero, so a
# 2 MB/s cache write reads as a "4x spike". A spike must also be this fast —
# well above background activity, well below a real bulk write (a dataset
# import or model checkpoint runs at hundreds of MB/s).
MIN_SPIKE_BYTES_PER_SEC = 50_000_000

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

    if ratio > 4 and write_bytes_per_sec >= MIN_SPIKE_BYTES_PER_SEC:
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


# --- who is filling the disk ------------------------------------------------
#
# The brief asks for alerts on "nefarious users". In practice an administrator
# cannot tell intent from telemetry, and it is not this tool's job to guess:
# what it can say is which account is consuming the space, how fast, and
# whether that is unlike the account's own recent history. Each rule below
# names an account and the evidence, so a person decides what it means.

# A quota is a limit someone deliberately set, so approaching it is worth
# saying before it is hit and a write fails.
QUOTA_WARNING_FRACTION = 0.9

# Growth is judged per hour so a missed or delayed sizing pass doesn't read as
# a spike. 10 GB/h is roughly a large download; 50 GB/h is not ordinary work.
GROWTH_WARNING_BYTES_PER_HOUR = 10 * 1024 ** 3
GROWTH_CRITICAL_BYTES_PER_HOUR = 50 * 1024 ** 3

# One account holding most of a shared machine is worth flagging even when it
# is growing slowly and breaking no quota.
DOMINANT_SHARE_FRACTION = 0.6


def _gb(n):
    return f"{n / 1024 ** 3:.1f} GB"


def check_user_quota(user):
    """Over, or nearly over, a quota somebody set."""
    hard = user.get("quota_hard_bytes") or 0
    soft = user.get("quota_soft_bytes") or 0
    used = user.get("used_bytes") or 0
    if not user.get("quota_enabled") or not (hard or soft):
        return None

    if hard and used >= hard:
        return {"type": "USER_OVER_QUOTA", "severity": "critical",
                "message": (f"{user['username']} is over the hard quota: "
                            f"{_gb(used)} of {_gb(hard)} — further writes will fail")}
    if soft and used >= soft:
        return {"type": "USER_OVER_QUOTA", "severity": "warning",
                "message": (f"{user['username']} is over the soft quota: "
                            f"{_gb(used)} of {_gb(soft)}")}
    # The soft quota is the boundary they meet first, so that is what
    # "nearly out of quota" has to mean; the hard limit only matters where no
    # soft one is set.
    limit = soft or hard
    if used >= limit * QUOTA_WARNING_FRACTION:
        return {"type": "USER_NEAR_QUOTA", "severity": "warning",
                "message": (f"{user['username']} is at {used / limit * 100:.0f}% of quota "
                            f"({_gb(used)} of {_gb(limit)})")}
    return None


def check_user_growth(user):
    """An account whose data is growing far faster than it usually does."""
    growth = user.get("growth_bytes")
    hours = user.get("elapsed_hours") or 0
    if not growth or growth <= 0 or hours <= 0:
        return None

    rate = growth / hours
    if rate >= GROWTH_CRITICAL_BYTES_PER_HOUR:
        severity = "critical"
    elif rate >= GROWTH_WARNING_BYTES_PER_HOUR:
        severity = "warning"
    else:
        return None
    return {"type": "USER_GROWTH_SPIKE", "severity": severity,
            "message": (f"{user['username']} added {_gb(growth)} in "
                        f"{hours:.1f}h ({_gb(rate)}/hour)")}


def check_user_dominance(user, volume_used_bytes):
    """One account holding most of what is used on the machine."""
    used = user.get("used_bytes") or 0
    if not volume_used_bytes or not used:
        return None
    fraction = used / volume_used_bytes
    if fraction < DOMINANT_SHARE_FRACTION:
        return None
    return {"type": "USER_DOMINATES_VOLUME", "severity": "warning",
            "message": (f"{user['username']} accounts for {fraction * 100:.0f}% of the "
                        f"{_gb(volume_used_bytes)} in use ({_gb(used)})")}


def detect_user_anomalies(users, volume_used_bytes=0):
    """Every per-user rule, over one sizing pass. Returns (user, alert) pairs so
    the caller can attribute each alert to the account it names."""
    found = []
    for user in users:
        for alert in (check_user_quota(user),
                      check_user_growth(user),
                      check_user_dominance(user, volume_used_bytes)):
            if alert:
                found.append((user, alert))
    return found
