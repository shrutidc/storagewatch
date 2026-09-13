import psutil
import requests
import json
import re
import os
import platform
import subprocess
import time
import plistlib
import secrets
import shutil
import sys
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from dotenv import load_dotenv

# The collector runs from its own directory but the .env lives at the project
# root, so point at it explicitly rather than relying on the search path.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# The agent stays on the Mac while the backend may run elsewhere, so this has
# to be configurable for any deployment that isn't all-on-one-machine.
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Where the administrator signs in to connect this Mac. Production serves the
# dashboard from the backend's origin; local development runs it on Vite.
DASHBOARD_URL = os.getenv("DASHBOARD_URL") or (
    "http://localhost:3000" if BACKEND_URL == "http://localhost:8000" else BACKEND_URL)

# The agent has no user to sign in as, so it authenticates to the backend with
# an agent token tied to the administrator's account. It is obtained once
# through the browser (see enroll_via_browser) and kept here.
TOKEN_FILE = Path.home() / ".storagewatch" / "agent_token"
AUTH_HEADERS = {}  # set in main() once the token is known

def get_volume_info(mountpoint):
    """Everything diskutil knows about a mounted volume, in one call."""
    try:
        out = subprocess.run(
            ["diskutil", "info", "-plist", mountpoint], capture_output=True, timeout=15
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
    """Real, user-relevant volumes: the boot volume, anything under /Volumes,
    and every shared volume wherever it happens to be mounted.

    Excludes macOS's internal /System/Volumes/* container slices (VM, Preboot,
    Update, etc.) which aren't independently meaningful to an end user — but
    a shared volume mounted under that path is still a shared volume, so the
    network check comes first.
    """
    volumes = []
    try:
        partitions = psutil.disk_partitions(all=True)
    except Exception as e:
        print(f"Error listing mounts: {e}")
        return volumes

    for p in partitions:
        if p.fstype.lower() in NETWORK_FS_TYPES:
            volumes.append(p.mountpoint)
        elif p.mountpoint == "/" or p.mountpoint.startswith("/Volumes/"):
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
            # Not a plain call: on a shared volume whose server has gone away
            # this blocks inside the kernel forever, and the local disks would
            # stop being reported along with it.
            disk = with_timeout(lambda mp=mountpoint: psutil.disk_usage(mp), 5)
            if disk is None:
                print(f"✗ {mountpoint} did not answer within 5s — skipped this cycle")
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

def get_apfs_volume_detail(device):
    """Where a volume is mounted, and whether it is sealed or read-only.

    `diskutil apfs list -plist` carries none of this — it is why the answer to
    "where is Preboot mounted?" used to be a trip to Terminal — so each volume
    costs one more diskutil call. Measured at ~80 ms each, against a system
    info refresh that runs once a minute.
    """
    try:
        d = plistlib.loads(subprocess.run(
            ["diskutil", "info", "-plist", device], capture_output=True).stdout)
    except Exception as e:
        print(f"Error reading APFS volume detail for {device}: {e}")
        return {}
    return {
        # Empty for a volume that isn't mounted — including the sealed system
        # volume, which is reached through its booted snapshot instead.
        "mount_point": d.get("MountPoint") or "",
        # A string "Yes"/"No" here, unlike every other flag diskutil returns.
        "sealed": d.get("Sealed") == "Yes",
        "writable": bool(d.get("WritableVolume", False)),
        "bootable": bool(d.get("Bootable", False)),
        # Shared by the System and Data volumes that make up one macOS install.
        "volume_group": d.get("APFSVolumeGroupID", ""),
    }

def get_booted_snapshot():
    """The read-only snapshot macOS is running from, if it is booted that way.

    On a sealed system volume `/` is not the volume itself but a snapshot of
    it, which is why the System volume shows no mount point of its own. The
    dashboard would otherwise just say "not mounted" for the volume the
    machine is running on.
    """
    try:
        d = plistlib.loads(subprocess.run(
            ["diskutil", "info", "-plist", "/"], capture_output=True).stdout)
    except Exception:
        return None
    if not d.get("APFSSnapshot"):
        return None
    return {
        "device_identifier": d.get("DeviceIdentifier", ""),
        "name": d.get("APFSSnapshotName", ""),
        "uuid": d.get("APFSSnapshotUUID", ""),
        "mount_point": d.get("MountPoint") or "/",
    }

def get_apfs_containers():
    """Real APFS container/volume info: capacity, roles, FileVault, encryption,
    and where each volume is actually mounted."""
    try:
        out = subprocess.run(["diskutil", "apfs", "list", "-plist"], capture_output=True).stdout
        data = plistlib.loads(out)
    except Exception as e:
        print(f"Error listing APFS containers: {e}")
        return []

    # One call for the whole machine rather than one per volume: only the
    # booted volume can have it, and it is found by device prefix below.
    snapshot = get_booted_snapshot()

    containers = []
    for c in data.get("Containers", []):
        # Skip macOS's tiny internal system containers (ISC, bare Recovery) —
        # not independently meaningful to an end user. 10GB threshold cleanly
        # separates these (<6GB) from any real user-facing container.
        if c.get("CapacityCeiling", 0) < 10_000_000_000:
            continue

        # Six sequential `diskutil info` calls cost ~690 ms; run concurrently
        # they cost about as much as the slowest one. They are independent
        # processes reading the same static layout, so there is nothing to
        # serialise them for.
        raw_volumes = c.get("Volumes", [])
        with ThreadPoolExecutor(max_workers=8) as pool:
            details = list(pool.map(get_apfs_volume_detail,
                                    [v.get("DeviceIdentifier", "") for v in raw_volumes]))

        volumes = []
        for v, detail in zip(raw_volumes, details):
            device = v.get("DeviceIdentifier", "")
            volume = {
                "name": v.get("Name", "Unknown"),
                "device_identifier": device,
                "uuid": v.get("APFSVolumeUUID", ""),
                "roles": v.get("Roles", []),
                "filevault": bool(v.get("FileVault")),
                "encrypted": bool(v.get("Encryption")),
                "locked": bool(v.get("Locked")),
                "capacity_in_use": v.get("CapacityInUse", 0),
                "capacity_quota": v.get("CapacityQuota", 0),
                "capacity_reserve": v.get("CapacityReserve", 0),
                **detail,
            }
            # "disk3s1s1" is a snapshot of "disk3s1": the machine boots from it
            # while the volume underneath stays unmounted.
            if snapshot and device and snapshot["device_identifier"].startswith(device):
                volume["snapshot"] = snapshot
            volumes.append(volume)

        store = (c.get("PhysicalStores") or [{}])[0]
        containers.append({
            "container_reference": c.get("ContainerReference", "Unknown"),
            "uuid": c.get("APFSContainerUUID", ""),
            "physical_store": c.get("DesignatedPhysicalStore", ""),
            "physical_store_uuid": store.get("DiskUUID", ""),
            "physical_store_size": store.get("Size", 0),
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

# --- block storage health ---------------------------------------------------

def _first_bsd_name(node):
    """The BSD disk a driver node belongs to, which sits on a child IOMedia."""
    if node.get("BSD Name"):
        return node["BSD Name"]
    for child in node.get("IORegistryEntryChildren", []):
        name = _first_bsd_name(child)
        if name:
            return name
    return None

def get_block_health():
    """Per-disk I/O errors, retries and service time, straight from the kernel.

    diskutil's SMART status is a single word — "Verified" — and stays that way
    until a disk is already failing. The block storage driver counts every I/O
    it had to retry or gave up on, and how long the hardware took to answer,
    which is the earliest warning a Mac gives without installing smartctl.
    """
    try:
        nodes = plistlib.loads(subprocess.run(
            ["ioreg", "-rc", "IOBlockStorageDriver", "-a", "-d2", "-l"],
            capture_output=True, timeout=15).stdout)
    except Exception as e:
        print(f"Error reading block storage statistics: {e}")
        return {}

    health = {}
    for node in nodes:
        stats = node.get("Statistics") or {}
        bsd = _first_bsd_name(node)
        # Drivers with no traffic are disk images and empty card readers.
        if not bsd or not stats.get("Operations (Read)"):
            continue
        reads = stats.get("Operations (Read)", 0)
        writes = stats.get("Operations (Write)", 0)
        health[bsd] = {
            "read_errors": stats.get("Errors (Read)", 0),
            "write_errors": stats.get("Errors (Write)", 0),
            "read_retries": stats.get("Retries (Read)", 0),
            "write_retries": stats.get("Retries (Write)", 0),
            "read_ops_total": reads,
            "write_ops_total": writes,
            "read_bytes_total": stats.get("Bytes (Read)", 0),
            "write_bytes_total": stats.get("Bytes (Write)", 0),
            # "Total Time" is nanoseconds spent servicing I/O, so this is the
            # average time one operation took. It climbs long before a disk
            # reports itself unhealthy.
            "avg_read_latency_us": round(stats.get("Total Time (Read)", 0) / reads / 1000, 1),
            "avg_write_latency_us": (round(stats.get("Total Time (Write)", 0) / writes / 1000, 1)
                                     if writes else 0.0),
        }
    return health

# Cumulative counters only say what has happened since boot, so the rate is
# taken between two refreshes of the system info.
previous_block_health = {}
previous_block_health_time = None

def add_block_io_rates(health):
    """Turn the cumulative counters into IOPS and MB/s over the last refresh."""
    global previous_block_health, previous_block_health_time
    now = time.time()
    elapsed = now - previous_block_health_time if previous_block_health_time else 0
    for bsd, cur in health.items():
        prev = previous_block_health.get(bsd)
        if prev and elapsed > 0:
            cur["read_iops"] = round((cur["read_ops_total"] - prev["read_ops_total"]) / elapsed, 1)
            cur["write_iops"] = round((cur["write_ops_total"] - prev["write_ops_total"]) / elapsed, 1)
            cur["read_bytes_per_sec"] = int((cur["read_bytes_total"] - prev["read_bytes_total"]) / elapsed)
            cur["write_bytes_per_sec"] = int((cur["write_bytes_total"] - prev["write_bytes_total"]) / elapsed)
        else:
            # First refresh after start: a rate needs two readings, and null
            # says "not measured yet" where 0 would claim an idle disk.
            cur["read_iops"] = cur["write_iops"] = None
            cur["read_bytes_per_sec"] = cur["write_bytes_per_sec"] = None
    previous_block_health = {k: dict(v) for k, v in health.items()}
    previous_block_health_time = now
    return health


# --- shared volumes (NFS, SMB, AFP) -----------------------------------------

# psutil.disk_partitions(all=False) keeps only local devices, which is why
# shared storage was invisible to the dashboard entirely.
NETWORK_FS_TYPES = {"nfs", "nfsv4", "smbfs", "afpfs", "webdav", "cifs", "ftp"}

def with_timeout(fn, timeout, default=None):
    """Run fn on a worker thread and give up on it after `timeout` seconds.

    A shared volume whose server has gone away leaves statvfs() blocked inside
    the kernel with no way to interrupt it, and the collector would stop
    reporting anything at all — including the local disks that are still fine.
    The thread is abandoned rather than killed, because Python cannot kill one;
    it is a daemon, so it never holds the process open.
    """
    result = {}
    def run():
        try:
            result["value"] = fn()
        except Exception as e:
            result["error"] = e
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout)
    return result.get("value", default)

def get_nfs_mount_parameters():
    """Per-mount NFS detail: protocol version, and whether pNFS is in use.

    `nfsstat -m` prints a block per mount whose first line is
    "<mountpoint> from <server>:<export>", followed by indented parameters.
    """
    try:
        out = subprocess.run(["nfsstat", "-m"], capture_output=True,
                             text=True, timeout=15).stdout
    except Exception:
        return {}

    params, mountpoint = {}, None
    for line in out.splitlines():
        if line and not line[0].isspace() and " from " in line:
            mountpoint = line.split(" from ")[0].strip()
            params[mountpoint] = {"detail": "", "nfs_version": "", "pnfs": False}
        elif mountpoint and line.strip():
            detail = params[mountpoint]
            detail["detail"] = (detail["detail"] + " " + line.strip()).strip()
            low = line.lower()
            # Written as "vers=4.1" in the parameter line and "nfsv4" in the
            # flag summary, depending on the macOS release.
            match = re.search(r"vers=(\d+(?:\.\d+)?)", low) or re.search(r"nfsv(\d(?:\.\d)?)", low)
            if match and not detail["nfs_version"]:
                detail["nfs_version"] = match.group(1)
            if "pnfs" in low:
                detail["pnfs"] = True
    return params

def get_network_mounts():
    """Shared volumes mounted on this Mac, with capacity where reachable."""
    parameters = get_nfs_mount_parameters()
    mounts = []
    try:
        partitions = psutil.disk_partitions(all=True)
    except Exception as e:
        print(f"Error listing mounts: {e}")
        return []

    for p in partitions:
        if p.fstype.lower() not in NETWORK_FS_TYPES:
            continue
        server, _, export = p.device.partition(":")
        usage = with_timeout(lambda mp=p.mountpoint: psutil.disk_usage(mp), 5)
        mount = {
            "mountpoint": p.mountpoint,
            "device": p.device,
            "fstype": p.fstype,
            "server": server if export else "",
            "export": export,
            "options": p.opts,
            "read_only": "ro" in p.opts.split(","),
            # False means the server did not answer in five seconds — a stale
            # mount, not an empty one, and the difference matters to whoever
            # is on call.
            "reachable": usage is not None,
            "total_bytes": usage.total if usage else 0,
            "used_bytes": usage.used if usage else 0,
            "free_bytes": usage.free if usage else 0,
            "used_percent": round(usage.used / usage.total * 100, 1) if usage and usage.total else 0.0,
            **parameters.get(p.mountpoint, {}),
        }
        mounts.append(mount)
    return mounts

def get_nfs_client_stats():
    """NFS client RPC counts by operation — the shared-volume equivalent of
    the local disk's read/write counters, and the only view of what this Mac
    is actually asking its servers to do."""
    try:
        out = subprocess.run(["nfsstat", "-c"], capture_output=True,
                             text=True, timeout=15).stdout
    except Exception:
        return {}

    stats, section, headers = {}, None, None
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.endswith("RPC Counts:"):
            section = stripped.replace(" RPC Counts:", "").strip()
            headers = None
            continue
        if not section or not stripped:
            continue
        fields = stripped.split()
        if all(f.isdigit() for f in fields) and headers and len(fields) == len(headers):
            # A row of numbers belongs to the header row directly above it.
            for name, value in zip(headers, fields):
                stats[f"{section}.{name}"] = int(value)
            headers = None
        elif not any(f.isdigit() for f in fields):
            headers = fields
    return stats

# --- users, quotas and who is filling the disk ------------------------------

def get_user_accounts():
    """Real people with home directories on this Mac.

    Below uid 500 is macOS's own service accounts (_spotlight, _www and some
    two hundred others), which own no user data and would bury the real ones.
    """
    try:
        out = subprocess.run(["dscl", ".", "-list", "/Users", "UniqueID"],
                             capture_output=True, text=True, timeout=15).stdout
    except Exception as e:
        print(f"Error listing user accounts: {e}")
        return []

    users = []
    for line in out.splitlines():
        fields = line.split()
        if len(fields) != 2 or not fields[1].isdigit():
            continue
        username, uid = fields[0], int(fields[1])
        if uid < 500 or username.startswith("_"):
            continue
        home = f"/Users/{username}"
        try:
            read = subprocess.run(["dscl", ".", "-read", f"/Users/{username}",
                                   "NFSHomeDirectory"], capture_output=True,
                                  text=True, timeout=10).stdout
            if ":" in read:
                home = read.split(":", 1)[1].strip() or home
        except Exception:
            pass
        users.append({"username": username, "uid": uid, "home": home})
    return users

def parse_quota_output(text):
    """Pull usage and limits out of `quota -v` for one user.

    Two shapes: "…: none" when the filesystem has no quotas turned on, or a
    table of filesystems with block and file limits. macOS ships quotas off,
    and saying so is a better answer for an administrator than an empty panel.
    """
    if "none" in text.lower():
        return {"enabled": False, "filesystems": []}

    filesystems, headers = [], None
    for line in text.splitlines():
        fields = line.split()
        if not fields or line.rstrip().endswith(":"):
            continue
        if fields[0].lower() in ("filesystem", "disk"):
            headers = fields
            continue
        # A quota row is a filesystem followed by numbers; grace columns are
        # blank when nothing is over its limit, so positions are not reliable
        # and only the leading numeric run is read.
        if headers and fields[0].startswith("/"):
            numbers = []
            for f in fields[1:]:
                if f.rstrip("*").isdigit():
                    numbers.append(int(f.rstrip("*")))
                else:
                    break
            if len(numbers) >= 3:
                filesystems.append({
                    "filesystem": fields[0],
                    # `quota` reports in 1 KiB blocks.
                    "used_bytes": numbers[0] * 1024,
                    "soft_limit_bytes": numbers[1] * 1024,
                    "hard_limit_bytes": numbers[2] * 1024,
                    "file_count": numbers[3] if len(numbers) > 3 else 0,
                    "file_soft_limit": numbers[4] if len(numbers) > 4 else 0,
                    "file_hard_limit": numbers[5] if len(numbers) > 5 else 0,
                })
    return {"enabled": bool(filesystems), "filesystems": filesystems}

def get_user_quotas(users):
    """Quota limits per user, where the filesystem has quotas enabled."""
    quotas = {}
    for user in users:
        try:
            out = subprocess.run(["quota", "-v", user["username"]],
                                 capture_output=True, text=True, timeout=15).stdout
        except Exception:
            continue
        quotas[user["username"]] = parse_quota_output(out)
    return quotas

# Sizing a home directory means walking it: `du -skx` over a 68 GB home took
# 77 seconds on the machine this was written on. Far too slow for a five-second
# loop, so it runs on its own thread and the loop only ever reads the last
# finished result.
USER_USAGE_INTERVAL = int(os.getenv("USER_USAGE_INTERVAL_SECONDS", "1800"))
USER_USAGE_TIMEOUT = int(os.getenv("USER_USAGE_TIMEOUT_SECONDS", "900"))
_user_usage = {"users": [], "measured_at": None, "measuring": False}
_user_usage_lock = threading.Lock()

def measure_user_usage(users):
    """Size every home directory, and the largest folders inside each.

    `-d 2` costs nothing extra — the walk happens either way — and turns "this
    user has 68 GB" into "and here is where it is", which is the question an
    administrator asks next.
    """
    measured = []
    for user in users:
        try:
            # `nice` so a background audit never competes with the user's work.
            out = subprocess.run(
                ["nice", "-n", "10", "du", "-kxd", "2", user["home"]],
                capture_output=True, text=True, timeout=USER_USAGE_TIMEOUT).stdout
        except subprocess.TimeoutExpired:
            print(f"✗ Sizing {user['home']} took longer than {USER_USAGE_TIMEOUT}s — skipped")
            continue
        except Exception as e:
            print(f"✗ Error sizing {user['home']}: {e}")
            continue

        total, children = 0, []
        for line in out.splitlines():
            size, _, path = line.partition("\t")
            if not path or not size.strip().isdigit():
                continue
            size_bytes = int(size) * 1024
            if path == user["home"]:
                total = size_bytes
            else:
                children.append({"path": path, "used_bytes": size_bytes})
        children.sort(key=lambda c: c["used_bytes"], reverse=True)
        measured.append({**user, "used_bytes": total,
                         "largest_folders": children[:10]})
    return measured

def user_usage_worker():
    """Re-measure every USER_USAGE_INTERVAL seconds, forever."""
    while True:
        users = get_user_accounts()
        if users:
            with _user_usage_lock:
                _user_usage["measuring"] = True
            measured = measure_user_usage(users)
            with _user_usage_lock:
                _user_usage.update(users=measured, measuring=False,
                                   measured_at=datetime.now(timezone.utc)
                                   .isoformat().replace("+00:00", "Z"))
            print(f"✓ Sized {len(measured)} home director"
                  f"{'y' if len(measured) == 1 else 'ies'}")
        time.sleep(USER_USAGE_INTERVAL)

def start_user_usage_worker():
    thread = threading.Thread(target=user_usage_worker, daemon=True)
    thread.start()
    return thread

def get_user_report():
    """Everything known about who is using the disk, for one report."""
    accounts = get_user_accounts()
    quotas = get_user_quotas(accounts)
    with _user_usage_lock:
        sized = {u["username"]: u for u in _user_usage["users"]}
        measured_at = _user_usage["measured_at"]
        measuring = _user_usage["measuring"]

    users = []
    for account in accounts:
        measurement = sized.get(account["username"], {})
        users.append({
            **account,
            # 0 until the first background pass finishes, which `measured_at`
            # being null distinguishes from a genuinely empty home directory.
            "used_bytes": measurement.get("used_bytes", 0),
            "largest_folders": measurement.get("largest_folders", []),
            "quota": quotas.get(account["username"], {"enabled": False, "filesystems": []}),
        })
    return {"users": users, "measured_at": measured_at, "measuring": measuring,
            "interval_seconds": USER_USAGE_INTERVAL}

def get_local_snapshots():
    """Time Machine's local snapshots, which silently hold space that `df`
    reports as free until macOS decides to thin them."""
    snapshots = []
    try:
        out = subprocess.run(["tmutil", "listlocalsnapshots", "/"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return snapshots
    for line in out.splitlines():
        name = line.strip()
        if not name.startswith("com.apple"):
            continue
        # Trailing component is the creation time: com.apple.TimeMachine.2026-09-12-154321
        stamp = name.rsplit(".", 1)[-1]
        snapshots.append({"name": name, "created": stamp if stamp[:2].isdigit() else ""})
    return snapshots

def get_inode_usage():
    """Inodes used and free per mounted filesystem.

    APFS allocates inodes dynamically so this rarely constrains a Mac, but a
    shared volume exported from anything else can run out of them while still
    reporting free space — a failure that looks like nothing else.
    """
    usage = []
    try:
        out = subprocess.run(["df", "-i"], capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return usage
    PSEUDO = ("devfs", "map", "autofs")
    for line in out.splitlines()[1:]:
        fields = line.split()
        # filesystem blocks used avail capacity iused ifree %iused mounted-on
        if len(fields) < 9 or not fields[5].isdigit() or not fields[6].isdigit():
            continue
        # devfs reports zero free inodes permanently, which reads as a
        # filesystem at 100% forever; neither it nor an automounter map is a
        # thing an administrator can run out of.
        if fields[0].startswith(PSEUDO):
            continue
        used, free = int(fields[5]), int(fields[6])
        usage.append({
            "filesystem": fields[0],
            "mountpoint": " ".join(fields[8:]),
            "inodes_used": used,
            "inodes_free": free,
            "inodes_used_percent": round(used / (used + free) * 100, 2) if used + free else 0.0,
        })
    return usage

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
        "snapshots": get_local_snapshots(),
        "block_health": add_block_io_rates(get_block_health()),
        "network_mounts": get_network_mounts(),
        "nfs_client_stats": get_nfs_client_stats(),
        "inode_usage": get_inode_usage(),
    }
    try:
        requests.post(f"{BACKEND_URL}/api/system-info", json=system_info,
                      headers=AUTH_HEADERS, timeout=10).raise_for_status()
        print(f"✓ System info sent: {len(system_info['physical_disks'])} disk(s), FileVault {'on' if system_info['filevault_enabled'] else 'off'}")
    except Exception as e:
        print(f"✗ Error sending system info: {e}")
    return system_info

def send_user_report():
    """POST who is using the disk, and under what quota.

    Separate from system info because it is answered by a background thread on
    its own schedule — home directories take minutes to size — and because the
    backend keeps a history of it to spot a user's usage running away.
    """
    report = get_user_report()
    report["hostname"] = platform.node()
    report["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        requests.post(f"{BACKEND_URL}/api/user-usage", json=report,
                      headers=AUTH_HEADERS, timeout=10).raise_for_status()
        print(f"✓ User report sent: {len(report['users'])} user(s)"
              f"{', sizing in progress' if report['measuring'] else ''}")
    except Exception as e:
        print(f"✗ Error sending user report: {e}")
    return report

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

# Counters are cumulative since boot, so an alert fires on a rise rather than
# on any non-zero value — a disk that logged one retry a year ago is not news
# every sixty seconds for the rest of its life.
previous_error_counts = {}

def check_block_health(block_health):
    """Alert on I/O the hardware got wrong, which SMART will not report until
    much later — often not until the disk has already lost data."""
    global previous_error_counts
    for bsd, h in block_health.items():
        errors = h["read_errors"] + h["write_errors"]
        retries = h["read_retries"] + h["write_retries"]
        was = previous_error_counts.get(bsd, {"errors": errors, "retries": retries})
        if errors > was["errors"]:
            report_alert("DISK_IO_ERRORS", "critical",
                         f"{bsd} reported {errors - was['errors']} new I/O error(s) "
                         f"({errors} since boot) — the disk failed to complete a read or write")
        elif retries > was["retries"]:
            report_alert("DISK_IO_RETRIES", "warning",
                         f"{bsd} retried {retries - was['retries']} I/O operation(s) "
                         f"({retries} since boot) — an early sign of a failing disk or cable")
        previous_error_counts[bsd] = {"errors": errors, "retries": retries}

previously_reachable_mounts = {}

def check_network_mounts(mounts):
    """Alert when a shared volume stops answering.

    A hung NFS mount is invisible to a capacity check — it reports nothing at
    all rather than reporting a problem — so it is worth its own alert.
    """
    global previously_reachable_mounts
    for m in mounts:
        was = previously_reachable_mounts.get(m["mountpoint"])
        if was and not m["reachable"]:
            report_alert("SHARE_UNREACHABLE", "critical",
                         f"{m['fstype'].upper()} share {m['device']} mounted at "
                         f"{m['mountpoint']} stopped responding")
        elif was is False and m["reachable"]:
            report_alert("SHARE_RECOVERED", "info",
                         f"{m['fstype'].upper()} share {m['device']} at "
                         f"{m['mountpoint']} is responding again")
        previously_reachable_mounts[m["mountpoint"]] = m["reachable"]

previously_seen_volumes = None

def check_volume_changes(current_volumes):
    global previously_seen_volumes
    current_set = set(current_volumes)
    if previously_seen_volumes is not None:
        for vol in previously_seen_volumes - current_set:
            report_alert("VOLUME_DISAPPEARED", "warning", f"Volume {vol} is no longer mounted")
    previously_seen_volumes = current_set

def send_metrics(metrics):
    """POST metrics to backend. Returns the backend's reply, or None on failure."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/metrics",
            json=metrics,
            headers=AUTH_HEADERS,
            timeout=5
        )
    except Exception as e:
        print(f"✗ Error sending metrics: {e}")
        return None
    if response.status_code == 401:
        raise TokenRejected()
    if not response.ok:
        # A rejected payload would otherwise fail silently every cycle.
        print(f"✗ Backend rejected metrics: HTTP {response.status_code} {response.text[:200]}")
        return None
    print(f"✓ Metrics sent: {metrics['used_percent']:.1f}% used, R:{metrics['read_bytes_per_sec']/1e6:.0f}MB/s W:{metrics['write_bytes_per_sec']/1e6:.0f}MB/s")
    return response.json()

# The menu bar app reads this instead of calling the API, so it needs no login:
# the collector already holds the credentials.
STATUS_FILE = TOKEN_FILE.parent / "status.json"

def write_status(samples, alerts, system_info):
    """Latest reading for the menu bar app, replaced atomically each cycle."""
    boot = next((m for m in samples if m["filesystem"] == "/"), samples[0] if samples else {})
    status = {
        "hostname": platform.node(),
        "dashboard_url": DASHBOARD_URL,
        "read_bytes_per_sec": boot.get("read_bytes_per_sec", 0),
        "write_bytes_per_sec": boot.get("write_bytes_per_sec", 0),
        "volumes": [{k: m[k] for k in ("filesystem", "filesystem_type", "total_bytes",
                                        "used_bytes", "free_bytes", "used_percent")}
                    for m in samples],
        "alerts": alerts,
        "disks": [{"model": d["model"], "smart_status": d["smart_status"]}
                  for d in system_info.get("physical_disks", [])],
        "filevault_enabled": system_info.get("filevault_enabled"),
        "snapshot_count": system_info.get("snapshot_count"),
    }
    STATUS_FILE.parent.mkdir(mode=0o700, exist_ok=True)
    tmp = STATUS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(status))
    tmp.replace(STATUS_FILE)

notified_alerts = None  # ids already announced; None until the first reply

def notify_new_alerts(alerts):
    """Raise a macOS notification for each alert that wasn't open last cycle.
    Alerts already open when the collector starts are not re-announced."""
    global notified_alerts
    if notified_alerts is not None:
        for a in alerts:
            if a["id"] not in notified_alerts:
                subprocess.run([
                    "osascript",
                    "-e", "on run argv",
                    "-e", "display notification (item 1 of argv) with title \"StorageWatch\" subtitle (item 2 of argv)",
                    "-e", "end run",
                    a["message"], a["alert_type"].replace("_", " ").title(),
                ], capture_output=True)
    notified_alerts = (notified_alerts or set()) | {a["id"] for a in alerts}

def load_or_enroll_token():
    """This Mac's agent token: from .env if set, else saved by an earlier
    sign-in, else obtained now through the browser."""
    if os.getenv("AGENT_TOKEN"):
        return os.getenv("AGENT_TOKEN")
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return connect_this_mac()

def connect_this_mac():
    """Sign in through the browser and save the resulting token."""
    token = enroll_via_browser()
    save_token(token)
    print(f"✓ Connected. Token saved to {TOKEN_FILE}\n")
    return token

def save_token(token):
    TOKEN_FILE.parent.mkdir(mode=0o700, exist_ok=True)
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)  # a credential: readable by this user only

class TokenRejected(Exception):
    """The backend no longer accepts this Mac's token."""

def enroll_via_browser():
    """Connect this Mac by signing in on the dashboard — nothing copied by hand.

    Opens the dashboard's /connect page. The administrator signs in with Auth0
    there and clicks Connect; the page mints an agent token and redirects the
    browser to this one-shot listener on 127.0.0.1. `state` ties the answer to
    this request, so no other page can plant a token of its own.
    """
    state = secrets.token_urlsafe(16)
    received = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            if query.get("state") == [state] and query.get("token"):
                received["token"] = query["token"][0]
                # Straight back to the dashboard, which fills in within seconds.
                self.send_response(302)
                self.send_header("Location", DASHBOARD_URL)
                self.end_headers()
            else:
                self.send_error(400, "Not a StorageWatch connect response")

        def log_message(self, *args):
            pass  # keep the terminal quiet

    server = HTTPServer(("127.0.0.1", 0), Callback)
    url = f"{DASHBOARD_URL}/connect?" + urlencode({
        "port": server.server_address[1], "state": state, "host": platform.node(),
    })
    print(f"Connect this Mac: sign in on the page opening in your browser.\n  {url}\n")
    webbrowser.open(url)
    try:
        while "token" not in received:
            server.handle_request()
    finally:
        server.server_close()
    return received["token"]

def main():
    """Run collector loop."""
    global AUTH_HEADERS, previous_counters, previous_time
    print(f"Starting StorageWatch collector...")
    print(f"Backend: {BACKEND_URL}")
    AUTH_HEADERS = {"Authorization": f"Bearer {load_or_enroll_token()}"}
    print(f"Sampling every 5 seconds...\n")
    # A rate needs two readings. Take the first now so the very first report —
    # the one a newly connected dashboard shows — carries real throughput, not 0.
    previous_counters, previous_time = psutil.disk_io_counters(), time.time()
    # Home directories take minutes to walk, so sizing starts now and runs on
    # its own thread; the first report simply carries no sizes yet.
    start_user_usage_worker()
    time.sleep(1)

    cycle = 0
    system_info = {}
    alerts = []
    # What the backend has been told about the menu bar app here. None until
    # the first report, so a restarted collector states the truth once and then
    # stays quiet — the dashboard needs this to distinguish "applied" from
    # "still applying", and reporting it every cycle would be a write per Mac
    # per five seconds for a value that almost never changes.
    reported_menu_bar = None
    while True:
        try:
            volumes = get_monitored_volumes()
            check_volume_changes(volumes)

            samples = collect_metrics()
            for metrics in samples:
                if metrics["filesystem"] == "/" and menu_bar_installed() != reported_menu_bar:
                    metrics["menu_bar_installed"] = menu_bar_installed()
                reply = send_metrics(metrics)
                if reply and "active_alerts" in reply:
                    if "menu_bar_installed" in metrics:
                        reported_menu_bar = metrics["menu_bar_installed"]
                    alerts = reply["active_alerts"]
                    notify_new_alerts(alerts)
                    # Older backends don't send this; they get the behaviour
                    # they always had, which is the app left in place.
                    apply_menu_bar(reply.get("menu_bar", True))

            # Disk/APFS info changes rarely — refresh every ~60s, not every cycle
            if cycle % 12 == 0:
                system_info = send_system_info()
                check_disk_health(system_info["physical_disks"])
                check_block_health(system_info["block_health"])
                check_network_mounts(system_info["network_mounts"])
                send_user_report()

            write_status(samples, alerts, system_info)
            cycle += 1
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n\nCollector stopped.")
            break
        except TokenRejected:
            # e.g. the token was minted against a different backend or database.
            print("✗ The backend rejected this Mac's token — reconnecting through the browser.")
            if os.getenv("AGENT_TOKEN"):
                print("  Remove AGENT_TOKEN from .env so the new token is used next time.")
            TOKEN_FILE.unlink(missing_ok=True)
            AUTH_HEADERS = {"Authorization": f"Bearer {connect_this_mac()}"}
        except Exception as e:
            print(f"Error in collection loop: {e}")
            time.sleep(5)

# The installed copy runs from ~/.storagewatch rather than wherever it was
# downloaded: macOS privacy controls stop background processes reading
# ~/Documents, ~/Desktop and ~/Downloads.
INSTALL_DIR = TOKEN_FILE.parent
LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "tech.storagewatch.collector.plist"

def install():
    """Connect this Mac, then run the collector in the background at every
    login, restarted if it exits — nobody has to start the script again."""
    save_token(load_or_enroll_token())  # the browser step happens now, in the foreground
    script = INSTALL_DIR / "collector.py"
    if Path(__file__).resolve() != script:
        shutil.copy(__file__, script)
    log = INSTALL_DIR / "collector.log"
    LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENT.write_bytes(plistlib.dumps({
        "Label": "tech.storagewatch.collector",
        "ProgramArguments": [sys.executable, str(script)],
        "EnvironmentVariables": {"BACKEND_URL": BACKEND_URL, "PYTHONUNBUFFERED": "1"},
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    }))
    subprocess.run(["launchctl", "unload", str(LAUNCH_AGENT)], capture_output=True)
    subprocess.run(["launchctl", "load", "-w", str(LAUNCH_AGENT)], check=True)
    print("✓ StorageWatch now runs in the background whenever you're logged in to this Mac.")
    print(f"  Log:    {log}")
    print(f"  Remove: {sys.executable} {script} --uninstall")
    # Not installed here: the collector that just started reconciles the menu
    # bar app against the dashboard's setting within a few seconds. Doing it
    # here as well would put the app back on a Mac where the administrator had
    # switched it off, only to remove it again moments later.
    print("  The menu bar app follows the Menu bar app switch on your dashboard.")

MENU_BAR_APP = Path.home() / "Applications" / "StorageWatch.app"
MENU_BAR_AGENT = Path.home() / "Library" / "LaunchAgents" / "tech.storagewatch.menubar.plist"

def menu_bar_installed():
    """Whether the menu bar app is on this Mac — the ground truth the dashboard
    is shown, rather than whatever was last asked for."""
    return MENU_BAR_APP.is_dir()

# A download that fails — no network, an older backend — must not be retried on
# every five-second cycle.
_menu_bar_retry_after = 0.0

def apply_menu_bar(enabled):
    """Make this Mac match the dashboard's Menu bar app switch.

    The dashboard cannot reach this Mac, so the setting arrives with the reply
    to a report and is applied here. A machine already in the wanted state does
    no work, which is every cycle but the one right after somebody flips it.
    """
    global _menu_bar_retry_after
    if enabled == menu_bar_installed():
        return
    if not enabled:
        remove_menu_bar()
    elif time.time() >= _menu_bar_retry_after:
        # Held off first, so a download that fails — no network, a backend
        # without the app — isn't retried on every five-second cycle. Cleared
        # again on success, otherwise switching the app off and back on inside
        # five minutes would quietly do nothing.
        _menu_bar_retry_after = time.time() + 300
        install_menu_bar()
        if menu_bar_installed():
            _menu_bar_retry_after = 0.0

def remove_menu_bar():
    """Take the menu bar app off this Mac. Monitoring is untouched: only the
    at-a-glance display is switched off, and the dashboard still fills in."""
    subprocess.run(["launchctl", "unload", str(MENU_BAR_AGENT)], capture_output=True)
    MENU_BAR_AGENT.unlink(missing_ok=True)
    subprocess.run(["pkill", "-x", "StorageWatch"], capture_output=True)
    shutil.rmtree(MENU_BAR_APP, ignore_errors=True)
    (INSTALL_DIR / "StorageWatch.zip").unlink(missing_ok=True)
    print("✓ Menu bar app removed — switched off in the dashboard.")

def install_menu_bar():
    """Put the StorageWatch menu bar app in ~/Applications and open it at login.

    Downloaded by this script rather than a browser, so macOS doesn't
    quarantine it and Gatekeeper doesn't block the ad-hoc-signed app.
    """
    try:
        r = requests.get(f"{BACKEND_URL}/StorageWatch.zip", timeout=60)
        r.raise_for_status()
        # A backend without the app answers unknown paths with the dashboard
        # page (200, HTML), which would otherwise be unzipped and fail.
        if r.content[:2] != b"PK":
            raise ValueError("this server doesn't provide the menu bar app yet")
    except Exception as e:
        print(f"✗ Menu bar app not installed: {e}")
        return
    archive = INSTALL_DIR / "StorageWatch.zip"
    archive.write_bytes(r.content)
    subprocess.run(["pkill", "-x", "StorageWatch"], capture_output=True)  # replace a running copy
    shutil.rmtree(MENU_BAR_APP, ignore_errors=True)
    MENU_BAR_APP.parent.mkdir(exist_ok=True)
    subprocess.run(["ditto", "-x", "-k", str(archive), str(MENU_BAR_APP.parent)], check=True)
    MENU_BAR_AGENT.write_bytes(plistlib.dumps({
        "Label": "tech.storagewatch.menubar",
        "ProgramArguments": ["/usr/bin/open", "-a", str(MENU_BAR_APP)],
        "RunAtLoad": True,
    }))
    subprocess.run(["launchctl", "unload", str(MENU_BAR_AGENT)], capture_output=True)
    subprocess.run(["launchctl", "load", "-w", str(MENU_BAR_AGENT)], check=True)
    print("✓ StorageWatch is in your menu bar (top right) and opens at login.")

def uninstall():
    for agent in (LAUNCH_AGENT, MENU_BAR_AGENT):
        subprocess.run(["launchctl", "unload", str(agent)], capture_output=True)
        agent.unlink(missing_ok=True)
    subprocess.run(["pkill", "-x", "StorageWatch"], capture_output=True)
    shutil.rmtree(MENU_BAR_APP, ignore_errors=True)
    print("✓ Background collector and menu bar app removed.")

if __name__ == "__main__":
    if "--install" in sys.argv:
        install()
    elif "--uninstall" in sys.argv:
        uninstall()
    else:
        main()
