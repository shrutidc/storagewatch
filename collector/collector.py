import psutil
import requests
import json
import platform
import subprocess
import time
from datetime import datetime

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

def collect_metrics():
    pass

def main():
    pass

if __name__ == "__main__":
    main()
