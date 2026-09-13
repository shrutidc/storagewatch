import psutil
import requests
import json
import os
import platform
import subprocess
import time
import plistlib
import secrets
import shutil
import sys
import webbrowser
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

        volumes = []
        for v in c.get("Volumes", []):
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
                **get_apfs_volume_detail(device),
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
    return system_info

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
