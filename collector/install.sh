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

# Any Python 3.9 or newer runs the collector — including Apple's own 3.9.6 from
# the Command Line Tools, so a Mac needs nothing macOS doesn't provide. The
# newest one found is preferred.
PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  path=$(command -v "$candidate" 2>/dev/null) || continue
  # Without the Command Line Tools, /usr/bin/python3 is only a stub that opens
  # an install window; that case is handled below, with an explanation.
  if [ "$path" = /usr/bin/python3 ] && ! xcode-select -p >/dev/null 2>&1; then continue; fi
  "$path" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null || continue
  PYTHON="$path"
  break
done
if [ -z "$PYTHON" ]; then
  if ! xcode-select -p >/dev/null 2>&1; then
    echo "This Mac needs Apple's Command Line Tools, which include Python."
    echo "A window is opening to install them: click Install, wait for it to"
    echo "finish (a few minutes), then run this command again."
    xcode-select --install >/dev/null 2>&1 || true
  else
    echo "StorageWatch needs Python 3.9 or newer; found $(python3 -V 2>&1)."
  fi
  exit 1
fi
echo "Using $("$PYTHON" -V 2>&1) at $PYTHON"

mkdir -p "$DIR"
echo "Downloading the StorageWatch collector..."
curl -fsSL "$URL/collector.py" -o "$DIR/collector.py"

# Rebuilt on every install: a virtualenv keeps the interpreter that created it,
# so an older or since-removed Python would otherwise linger.
"$PYTHON" -m venv --clear "$DIR/venv"
"$DIR/venv/bin/pip" install --quiet --disable-pip-version-check psutil requests python-dotenv
BACKEND_URL="$URL" "$DIR/venv/bin/python" "$DIR/collector.py" --install
