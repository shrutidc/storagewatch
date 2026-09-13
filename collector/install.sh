#!/bin/sh
# StorageWatch collector installer for macOS:
#
#   curl -fsSL https://storagewatch.tech/install.sh | sh
#
# Downloads the collector into ~/.storagewatch, connects this Mac to your
# account through the browser, and runs it in the background at every login.
set -e

URL="${STORAGEWATCH_URL:-https://storagewatch.tech}"
DIR="$HOME/.storagewatch"

[ "$(uname)" = Darwin ] || { echo "StorageWatch monitors macOS only."; exit 1; }

mkdir -p "$DIR"
echo "Downloading the StorageWatch collector..."
curl -fsSL "$URL/collector.py" -o "$DIR/collector.py"
python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install --quiet --disable-pip-version-check psutil requests python-dotenv
BACKEND_URL="$URL" "$DIR/venv/bin/python" "$DIR/collector.py" --install
