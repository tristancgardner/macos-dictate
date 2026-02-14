#!/bin/bash
# Rebuild Dictate.app (alias mode)
# Only needed when setup.py changes -- code changes are live via symlinks

set -e
cd "$(dirname "$0")"

PYTHON="/Users/tristangardner/.pyenv/versions/3.12.7/envs/venv/bin/python"
BUNDLE_ID="com.suorastudios.dictate"
APP="dist/Dictate.app"

echo "==> Killing running instance..."
osascript -e "tell application \"Dictate\" to quit" 2>/dev/null || true
sleep 0.5

echo "==> Cleaning build artifacts..."
rm -rf build dist

echo "==> Building Dictate.app (alias mode)..."
$PYTHON setup.py py2app -A

echo "==> Code signing with entitlements..."
codesign --deep --force --options=runtime --entitlements entitlements.plist -s - "$APP"

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
