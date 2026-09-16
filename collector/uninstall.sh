#!/bin/sh
# Stops StorageWatch on this Mac and removes everything it put there:
#   curl -fsSL https://storagewatch.tech/uninstall.sh | sh
# Works for both the Terminal install and the downloaded app. Logging out of the
# dashboard doesn't do this: the collector reports with its own token, not the
# browser session. Metrics already reported stay on the dashboard.

# launchd restarts whatever it runs, so its jobs go before the processes do.
for label in tech.storagewatch.collector tech.storagewatch.menubar tech.storagewatch.app; do
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null
  rm -f "$HOME/Library/LaunchAgents/$label.plist"
done

# The downloaded app restarts its bundled collector, so the app goes first.
pkill -x StorageWatch
pkill -f storagewatch-collector
pkill -f '\.storagewatch/collector\.py'

rm -rf "$HOME/Applications/StorageWatch.app" "$HOME/.storagewatch"
rm -rf /Applications/StorageWatch.app 2>/dev/null

echo "✓ StorageWatch has stopped and been removed from this Mac."
