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

# The collector needs Python 3.10 or newer. Plain `python3` on macOS is
# Apple's 3.9.6 from the Command Line Tools, so the newest suitable interpreter
# is chosen explicitly rather than taking whatever the name happens to resolve
# to — otherwise the agent silently ends up on 3.9.
PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
  path=$(command -v "$candidate" 2>/dev/null) || continue
  "$path" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null || continue
  PYTHON="$path"
  break
done
if [ -z "$PYTHON" ]; then
  echo "StorageWatch needs Python 3.10 or newer; the newest one found is $(python3 -V 2>&1)."
  echo "Install a newer Python (for example: brew install python@3.12) and run this again."
  exit 1
fi
echo "Using $("$PYTHON" -V 2>&1) at $PYTHON"

mkdir -p "$DIR"
echo "Downloading the StorageWatch collector..."
curl -fsSL "$URL/collector.py" -o "$DIR/collector.py"

# A virtualenv keeps whichever interpreter built it, so one created by an older
# Python has to be replaced rather than reused — `venv` on an existing
# directory will not change it.
if [ -x "$DIR/venv/bin/python" ] && \
   ! "$DIR/venv/bin/python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "Replacing the existing virtualenv, which was built with $("$DIR/venv/bin/python" -V 2>&1)..."
  rm -rf "$DIR/venv"
fi
"$PYTHON" -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install --quiet --disable-pip-version-check psutil requests python-dotenv
BACKEND_URL="$URL" "$DIR/venv/bin/python" "$DIR/collector.py" --install
