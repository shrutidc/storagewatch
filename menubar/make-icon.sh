#!/bin/sh
# Builds menubar/AppIcon.icns — the Finder/Dock icon of StorageWatch.app — from
# frontend/public/logo.svg. The tile is squared off to fill the whole canvas:
# macOS 26 rounds a full-bleed icon itself, but puts any other shape on a white
# plate. Uses only macOS's own tools.
set -e
cd "$(dirname "$0")"
T=$(mktemp -d)

sed 's/<rect width="64" height="64" rx="14"/<rect width="64" height="64"/' \
  ../frontend/public/logo.svg > "$T/icon.svg"
qlmanage -t -s 1024 -o "$T" "$T/icon.svg" >/dev/null 2>&1

mkdir "$T/AppIcon.iconset"
for s in 16 32 128 256 512; do
  sips -z $s $s "$T/icon.svg.png" --out "$T/AppIcon.iconset/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) "$T/icon.svg.png" --out "$T/AppIcon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$T/AppIcon.iconset" -o AppIcon.icns
rm -rf "$T"
echo "built menubar/AppIcon.icns"
