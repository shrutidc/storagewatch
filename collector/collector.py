import psutil
import requests
import json
import platform
import subprocess
import time
from datetime import datetime, timezone

BACKEND_URL = "http://localhost:8000"

def get_filesystem_type():
    try:
        result = subprocess.run(
            ["diskutil", "info", "/"],
            capture_output=True,
            text=True
        )
        for line in result.stdout.split("\n"):
            if "File System Personality" in line:
                return line.split(":")[-1].strip()
    except Exception as e:
        print(f"Error detecting filesystem: {e}")
    return "Unknown"

previous_counters = None
previous_time = None

def collect_metrics():
    """Collect filesystem and I/O metrics."""
    global previous_counters, previous_time

    # Capacity metrics
    disk = psutil.disk_usage("/")

    # I/O counters
    counters = psutil.disk_io_counters()
    current_time = time.time()

    # Calculate throughput
    if previous_counters and previous_time:
        time_delta = current_time - previous_time
        read_bytes_per_sec = int((counters.read_bytes - previous_counters.read_bytes) / time_delta)
        write_bytes_per_sec = int((counters.write_bytes - previous_counters.write_bytes) / time_delta)
    else:
        read_bytes_per_sec = 0
        write_bytes_per_sec = 0

    previous_counters = counters
    previous_time = current_time

    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "hostname": platform.node(),
        "filesystem": "/",
        "filesystem_type": get_filesystem_type(),
        "total_bytes": disk.total,
        "used_bytes": disk.used,
        "free_bytes": disk.free,
        "used_percent": round(disk.used / disk.total * 100, 1),
        "read_bytes_per_sec": read_bytes_per_sec,
        "write_bytes_per_sec": write_bytes_per_sec,
    }

    return metrics

def send_metrics(metrics):
    """POST metrics to backend."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/metrics",
            json=metrics,
            timeout=5
        )
        if response.status_code == 200:
            print(f"✓ Metrics sent: {metrics['used_percent']:.1f}% used, R:{metrics['read_bytes_per_sec']/1e6:.0f}MB/s W:{metrics['write_bytes_per_sec']/1e6:.0f}MB/s")
            return True
    except Exception as e:
        print(f"✗ Error sending metrics: {e}")
    return False

def main():
    """Run collector loop."""
    print(f"Starting StorageWatch collector...")
    print(f"Backend: {BACKEND_URL}")
    print(f"Sampling every 5 seconds...\n")

    while True:
        try:
            metrics = collect_metrics()
            send_metrics(metrics)
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n\nCollector stopped.")
            break
        except Exception as e:
            print(f"Error in collection loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
