import psutil
import requests
import json
import os
import platform
import subprocess
import time
import plistlib
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# The collector runs from its own directory but the .env lives at the project
# root, so point at it explicitly rather than relying on the search path.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# The agent stays on the Mac while the backend may run elsewhere, so this has
# to be configurable for any deployment that isn't all-on-one-machine.
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# The agent has no user to sign in as, so it authenticates to the backend with
# an agent token minted from the dashboard's Settings page instead of an Auth0 token.
AGENT_TOKEN = os.getenv("AGENT_TOKEN")
AUTH_HEADERS = {"Authorization": f"Bearer {AGENT_TOKEN}"}

def get_volume_info(mountpoint):
    """Everything diskutil knows about a mounted volume, in one call."""
    try:
        out = subprocess.run(
            ["diskutil", "info", "-plist", mountpoint], capture_output=True
        ).stdout
        d = plistlib.loads(out)
    except Exception as e:
        print(f"Error reading volume info for {mountpoint}: {e}")
        return {}

    return {
        "volume_name": d.get("VolumeName", mountpoint),
        "fs_type": d.get("FilesystemName") or d.get("FilesystemType", "Unknown"),
        "writable": bool(d.get("WritableVolume", False)),
        "container_ref": d.get("APFSContainerReference"),
        "container_size": d.get("APFSContainerSize"),
        "container_free": d.get("APFSContainerFree"),
        "volume_used": d.get("CapacityInUse"),
    }

def get_monitored_volumes():
    """Real, user-relevant volumes: the boot volume and anything mounted under /Volumes.

    Excludes macOS's internal /System/Volumes/* container slices (VM, Preboot,
    Update, etc.) which aren't independently meaningful to an end user.
    """
    volumes = []
    for p in psutil.disk_partitions(all=False):
        if p.mountpoint == "/" or p.mountpoint.startswith("/Volumes/"):
            volumes.append(p.mountpoint)
    return volumes

previous_counters = None
previous_time = None

def collect_metrics():
    """Collect filesystem and I/O metrics for every real, mounted volume.

    Read/write throughput is a physical-disk-level measurement (psutil has no
    per-volume equivalent on macOS), so the same system I/O reading is
    attached to each volume's payload rather than inventing per-volume numbers.
    """
    global previous_counters, previous_time

    counters = psutil.disk_io_counters()
    current_time = time.time()

    if previous_counters and previous_time:
        time_delta = current_time - previous_time
        read_bytes_per_sec = int((counters.read_bytes - previous_counters.read_bytes) / time_delta)
        write_bytes_per_sec = int((counters.write_bytes - previous_counters.write_bytes) / time_delta)
    else:
        read_bytes_per_sec = 0
        write_bytes_per_sec = 0

    previous_counters = counters
    previous_time = current_time

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    hostname = platform.node()

    all_metrics = []
    for mountpoint in get_monitored_volumes():
        info = get_volume_info(mountpoint)

        # On APFS, every volume in a container shares one free-space pool, so
        # psutil's per-volume used/free don't add up to its total (on a modern
        # Mac "/" is a read-only system snapshot holding only ~12GB while user
        # data lives on a sibling volume). Report the container's numbers —
        # that's the real capacity constraint, and what macOS itself reports.
        if info.get("container_size") and info.get("container_free") is not None:
            total = info["container_size"]
            free = info["container_free"]
            used = total - free
        else:
            try:
                disk = psutil.disk_usage(mountpoint)
            except Exception as e:
                print(f"Error reading usage for {mountpoint}: {e}")
                continue
            total, used, free = disk.total, disk.used, disk.free

        if not total:
            continue

        all_metrics.append({
            "timestamp": timestamp,
            "hostname": hostname,
            "filesystem": mountpoint,
            "filesystem_type": info.get("fs_type", "Unknown"),
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "used_percent": round(used / total * 100, 1),
            "read_bytes_per_sec": read_bytes_per_sec,
            "write_bytes_per_sec": write_bytes_per_sec,
        })

    return all_metrics

def get_physical_disks():
    """Real physical disk info via diskutil (no smartctl/sudo needed).

    diskutil's "WholeDisks" list also includes synthesized APFS container
    disks (Content: Apple_APFS_Container), which sit virtually on top of a
    real disk rather than being one. Only GUID_partition_scheme entries are
    genuine physical disks.
    """
    try:
        out = subprocess.run(["diskutil", "list", "-plist"], capture_output=True).stdout
        data = plistlib.loads(out)
        physical = [
            d for d in data.get("AllDisksAndPartitions", [])
            if d.get("Content") == "GUID_partition_scheme"
        ]
    except Exception as e:
        print(f"Error listing disks: {e}")
        return []

    disks = []
    for entry in physical:
        disk_id = entry["DeviceIdentifier"]
        try:
            out = subprocess.run(["diskutil", "info", "-plist", disk_id], capture_output=True).stdout
            info = plistlib.loads(out)
        except Exception as e:
            print(f"Error reading disk {disk_id}: {e}")
            continue

        disks.append({
            "device_identifier": disk_id,
            "device_node": info.get("DeviceNode", f"/dev/{disk_id}"),
            "model": info.get("MediaName", "Unknown"),
            "protocol": info.get("BusProtocol", "Unknown"),
            "solid_state": bool(info.get("SolidState", False)),
            "internal": bool(info.get("Internal", True)),
            "removable": bool(info.get("RemovableMedia", False)),
            "ejectable": bool(info.get("Ejectable", False)),
            "smart_status": info.get("SMARTStatus", "Not Supported"),
            "size_bytes": info.get("Size", 0),
            "block_size": info.get("DeviceBlockSize", 0),
            "partitions": [{
                "identifier": p.get("DeviceIdentifier"),
                "content": p.get("Content"),
                "size_bytes": p.get("Size", 0),
            } for p in entry.get("Partitions", [])],
        })
    return disks

def get_apfs_containers():
    """Real APFS container/volume info: capacity, roles, FileVault, encryption."""
    try:
        out = subprocess.run(["diskutil", "apfs", "list", "-plist"], capture_output=True).stdout
        data = plistlib.loads(out)
    except Exception as e:
        print(f"Error listing APFS containers: {e}")
        return []

    containers = []
    for c in data.get("Containers", []):
        # Skip macOS's tiny internal system containers (ISC, bare Recovery) —
        # not independently meaningful to an end user. 10GB threshold cleanly
        # separates these (<6GB) from any real user-facing container.
        if c.get("CapacityCeiling", 0) < 10_000_000_000:
            continue

        volumes = [{
            "name": v.get("Name", "Unknown"),
            "device_identifier": v.get("DeviceIdentifier", ""),
            "uuid": v.get("APFSVolumeUUID", ""),
            "roles": v.get("Roles", []),
            "filevault": bool(v.get("FileVault")),
            "encrypted": bool(v.get("Encryption")),
            "locked": bool(v.get("Locked")),
            "capacity_in_use": v.get("CapacityInUse", 0),
            "capacity_quota": v.get("CapacityQuota", 0),
            "capacity_reserve": v.get("CapacityReserve", 0),
        } for v in c.get("Volumes", [])]

        containers.append({
            "container_reference": c.get("ContainerReference", "Unknown"),
            "uuid": c.get("APFSContainerUUID", ""),
            "physical_store": c.get("DesignatedPhysicalStore", ""),
            "capacity_ceiling": c.get("CapacityCeiling", 0),
            "capacity_free": c.get("CapacityFree", 0),
            "volumes": volumes,
        })
    return containers

def get_filevault_status():
    try:
        out = subprocess.run(["fdesetup", "status"], capture_output=True, text=True).stdout
        return "On" in out
    except Exception:
        return False

def get_snapshot_count():
    try:
        out = subprocess.run(["tmutil", "listlocalsnapshots", "/"], capture_output=True, text=True).stdout
        return len([l for l in out.splitlines() if l.strip().startswith("com.apple")])
    except Exception:
        return 0

def get_volume_properties():
    """Static per-volume properties (device, mount flags, local vs network).

    These don't change sample-to-sample, so they ride along with system info
    rather than being written into the time-series table on every cycle.
    """
    props = []
    for p in psutil.disk_partitions(all=False):
        if p.mountpoint != "/" and not p.mountpoint.startswith("/Volumes/"):
            continue
        opts = p.opts.split(",")
        info = get_volume_info(p.mountpoint)
        props.append({
            "mountpoint": p.mountpoint,
            "device": p.device,
            "fstype": p.fstype,
            "read_only": "ro" in opts,
            "is_local": "local" in opts,
            "volume_name": info.get("volume_name", p.mountpoint),
            "container_ref": info.get("container_ref"),
            "volume_used_bytes": info.get("volume_used"),
        })
    return props

def get_io_totals():
    """Cumulative bytes read/written since boot (physical-disk level)."""
    try:
        c = psutil.disk_io_counters()
        return {
            "read_bytes_total": c.read_bytes,
            "write_bytes_total": c.write_bytes,
            "read_count": c.read_count,
            "write_count": c.write_count,
        }
    except Exception:
        return {}

def send_system_info():
    """Gather and POST slow-changing disk/APFS info (not every 5-sec cycle)."""
    system_info = {
        "hostname": platform.node(),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "physical_disks": get_physical_disks(),
        "apfs_containers": get_apfs_containers(),
        "volume_properties": get_volume_properties(),
        "io_totals": get_io_totals(),
        "filevault_enabled": get_filevault_status(),
        "snapshot_count": get_snapshot_count(),
    }
    try:
        requests.post(f"{BACKEND_URL}/api/system-info", json=system_info,
                      headers=AUTH_HEADERS, timeout=10).raise_for_status()
        print(f"✓ System info sent: {len(system_info['physical_disks'])} disk(s), FileVault {'on' if system_info['filevault_enabled'] else 'off'}")
    except Exception as e:
        print(f"✗ Error sending system info: {e}")
    return system_info["physical_disks"]

def report_alert(alert_type, severity, message):
    """Report an ad-hoc alert (not tied to a specific metrics sample) for AI explanation + storage."""
    try:
        requests.post(f"{BACKEND_URL}/api/alerts/report", headers=AUTH_HEADERS, json={
            "hostname": platform.node(),
            "alert_type": alert_type,
            "severity": severity,
            "message": message,
        }, timeout=10).raise_for_status()
        print(f"⚠ Alert reported: {alert_type} - {message}")
    except Exception as e:
        print(f"✗ Error reporting alert: {e}")

def check_disk_health(physical_disks):
    for d in physical_disks:
        status = d.get("smart_status")
        if status and status not in ("Verified", "Not Supported"):
            report_alert(
                "DISK_HEALTH_PROBLEM", "critical",
                f"Disk {d['device_identifier']} ({d['model']}) SMART status: {status}"
            )

previously_seen_volumes = None

def check_volume_changes(current_volumes):
    global previously_seen_volumes
    current_set = set(current_volumes)
    if previously_seen_volumes is not None:
        for vol in previously_seen_volumes - current_set:
            report_alert("VOLUME_DISAPPEARED", "warning", f"Volume {vol} is no longer mounted")
    previously_seen_volumes = current_set

def send_metrics(metrics):
    """POST metrics to backend."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/metrics",
            json=metrics,
            headers=AUTH_HEADERS,
            timeout=5
        )
        # A rejected token or payload would otherwise fail silently every cycle.
        response.raise_for_status()
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
    if not AGENT_TOKEN:
        print("⚠ AGENT_TOKEN is not set — generate one under Settings in the dashboard.\n")

    cycle = 0
    while True:
        try:
            volumes = get_monitored_volumes()
            check_volume_changes(volumes)

            for metrics in collect_metrics():
                send_metrics(metrics)

            # Disk/APFS info changes rarely — refresh every ~60s, not every cycle
            if cycle % 12 == 0:
                physical_disks = send_system_info()
                check_disk_health(physical_disks)

            cycle += 1
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n\nCollector stopped.")
            break
        except Exception as e:
            print(f"Error in collection loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
