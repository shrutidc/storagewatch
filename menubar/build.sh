#!/bin/sh
# Builds StorageWatch.app (universal: Apple Silicon + Intel, ad-hoc signed) and
# zips it to menubar/StorageWatch.zip, which the backend serves to the installer.
# Needs Apple's Command Line Tools (swiftc). Run from anywhere.
set -e
cd "$(dirname "$0")"

rm -rf build
mkdir -p build/StorageWatch.app/Contents/MacOS
for arch in arm64 x86_64; do
  swiftc -O -parse-as-library -target "$arch-apple-macos13" StorageWatchBar.swift -o "build/StorageWatch-$arch"
done
lipo -create build/StorageWatch-arm64 build/StorageWatch-x86_64 \
  -output build/StorageWatch.app/Contents/MacOS/StorageWatch
cp Info.plist build/StorageWatch.app/Contents/
codesign --force --sign - build/StorageWatch.app

rm -f StorageWatch.zip
ditto -c -k --keepParent build/StorageWatch.app StorageWatch.zip
echo "built menubar/StorageWatch.zip"
