#!/usr/bin/env python3
"""Phase 1 local test: verify endpoints work with mock data."""

import sys
import json
from datetime import datetime
from models import Metrics
from alerts import detect_anomalies, check_capacity_alert, check_io_anomaly

def test_capacity_alert():
    """Test capacity alert detection."""
    print("\n[TEST] Capacity Alert Detection")

    # Normal (0-79%)
    alert = check_capacity_alert(50.0)
    assert alert is None, "50% should not trigger alert"
    print("✓ 50% capacity: no alert")

    # Warning (80-89%)
    alert = check_capacity_alert(85.0)
    assert alert is not None, "85% should trigger alert"
    assert alert["severity"] == "warning", "85% should be warning"
    print("✓ 85% capacity: warning alert")

    # Critical (90-100%)
    alert = check_capacity_alert(95.0)
    assert alert is not None, "95% should trigger alert"
    assert alert["severity"] == "critical", "95% should be critical"
    print("✓ 95% capacity: critical alert")

def test_write_anomaly():
    """Test write anomaly detection."""
    print("\n[TEST] Write Anomaly Detection")

    # Too few prior samples to judge yet
    for _ in range(5):
        assert check_io_anomaly(100_000_000) is None, "Needs 5 prior samples"
    print("✓ Warm-up (5 samples): no alert")

    # Normal write (100 MB/s, should not alert)
    result = check_io_anomaly(100_000_000)
    assert result is None, "Normal write should not alert"
    print("✓ Normal write (100 MB/s): no alert")

    # 5x the previous samples' mean crosses the 4x threshold. The spike must not
    # dampen its own baseline, so the ratio is exactly 5.
    result = check_io_anomaly(500_000_000)
    assert result is not None and result["ratio"] == 5.0, f"5x should alert, got {result}"
    print(f"✓ 5x baseline (500 MB/s): {result['message']}")

    # Another machine's baseline is separate, so it has no history yet
    assert check_io_anomaly(500_000_000, key="other-mac") is None, "Baselines must be per machine"
    print("✓ Per-machine baseline")

    # On an idle Mac a tiny write is a big ratio; below 50 MB/s it isn't an alert
    for _ in range(5):
        check_io_anomaly(400_000, key="idle-mac")
    assert check_io_anomaly(2_000_000, key="idle-mac") is None, "2 MB/s must not alert"
    print("✓ 2 MB/s at 5x baseline: no alert (below 50 MB/s)")

def test_metrics_model():
    """Test Metrics model validation."""
    print("\n[TEST] Metrics Model Validation")

    data = {
        "timestamp": datetime.now().isoformat() + "Z",
        "hostname": "test-mac",
        "filesystem": "/",
        "filesystem_type": "APFS",
        "total_bytes": 1000000000,
        "used_bytes": 600000000,
        "free_bytes": 400000000,
        "used_percent": 60.0,
        "read_bytes_per_sec": 150000000,
        "write_bytes_per_sec": 50000000,
    }

    metrics = Metrics(**data)
    assert metrics.hostname == "test-mac"
    assert metrics.used_percent == 60.0
    print("✓ Metrics model created successfully")
    print(f"  Hostname: {metrics.hostname}")
    print(f"  Used: {metrics.used_percent}%")

def test_anomaly_detection():
    """Test full anomaly detection pipeline."""
    print("\n[TEST] Full Anomaly Detection")

    metrics = Metrics(
        timestamp=datetime.now().isoformat() + "Z",
        hostname="test-mac",
        filesystem="/",
        filesystem_type="APFS",
        total_bytes=1000000000,
        used_bytes=850000000,  # 85% capacity
        free_bytes=150000000,
        used_percent=85.0,
        read_bytes_per_sec=150000000,
        write_bytes_per_sec=100000000,
    )

    anomalies = detect_anomalies(metrics)
    print(f"✓ Detected {len(anomalies)} anomaly/anomalies:")
    for anom in anomalies:
        print(f"  - {anom['type']}: {anom['message']}")

if __name__ == "__main__":
    print("=" * 60)
    print("StorageWatch Phase 1 Test Suite")
    print("=" * 60)

    try:
        test_capacity_alert()
        test_write_anomaly()
        test_metrics_model()
        test_anomaly_detection()

        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
