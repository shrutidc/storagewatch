#!/bin/sh
# Builds the downloadable StorageWatch.app: the menu bar app with the Python
# collector bundled inside as one self-contained executable (PyInstaller), so a
# Mac needs no Python and no Terminal. Output: menubar/StorageWatch-Mac.zip.
#
# Needs swiftc, and a Python with PyInstaller and the collector's dependencies:
#   python3 -m venv /tmp/pyi && /tmp/pyi/bin/pip install pyinstaller psutil requests python-dotenv
#   PYTHON=/tmp/pyi/bin/python menubar/build-app.sh
# Both executables are built for this Mac's architecture only.
set -e
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
OUT=build/standalone
APP=$OUT/StorageWatch.app

rm -rf "$OUT"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
swiftc -O -parse-as-library -target "$(uname -m)-apple-macos13" StorageWatchBar.swift \
  -o "$APP/Contents/MacOS/StorageWatch"
"$PYTHON" -m PyInstaller --onefile --noconfirm --log-level WARN \
  --name storagewatch-collector --distpath "$OUT/dist" --workpath "$OUT/work" \
  --specpath "$OUT" ../collector/collector.py
cp "$OUT/dist/storagewatch-collector" "$APP/Contents/MacOS/"
cp Info.plist "$APP/Contents/"
cp AppIcon.icns "$APP/Contents/Resources/"
codesign --force --deep --sign - "$APP"

rm -f StorageWatch-Mac.zip
ditto -c -k --keepParent "$APP" StorageWatch-Mac.zip
echo "built menubar/StorageWatch-Mac.zip"
