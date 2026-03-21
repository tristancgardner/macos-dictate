#!/bin/bash
# Rebuild Dictate.app (alias mode)
# Only needed when setup.py or build-assets change -- code changes are live via symlinks
# Run from anywhere: ./build-assets/rebuild.sh

set -e

# Always operate from project root
SCRIPT_DIR="$(dirname "$0")"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON="$PROJECT_ROOT/venv/bin/python"
BUNDLE_ID="com.suorastudios.dictate"
APP="dist/Dictate.app"

echo "==> Killing running instance..."
osascript -e "tell application \"Dictate\" to quit" 2>/dev/null || true
sleep 0.5

echo "==> Cleaning build artifacts..."
rm -rf build dist

echo "==> Building Dictate.app (alias mode)..."
$PYTHON build-assets/setup.py py2app -A

echo "==> Code signing with entitlements..."
codesign --deep --force --options=runtime --entitlements build-assets/entitlements.plist -s - "$APP"

echo "==> Resetting TCC permissions for $BUNDLE_ID..."
tccutil reset Accessibility "$BUNDLE_ID" 2>/dev/null || true
tccutil reset ListenEvent "$BUNDLE_ID" 2>/dev/null || true

echo "==> Opening System Settings for re-authorization..."
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
sleep 1
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"

echo ""
echo "==> Build complete: $APP"
echo ""
echo "Next steps:"
echo "  1. Add Dictate.app in both Settings pages that just opened"
echo "  2. Then run:  open dist/Dictate.app"
