#!/bin/zsh
# Kill any existing dictate processes
pkill -9 -f "dictate.py" 2>/dev/null
sleep 0.5

# Restart via launchctl
launchctl kickstart -k gui/$(id -u)/com.tristangardner.dictate 2>/dev/null || launchctl start com.tristangardner.dictate

echo "Dictate restarted"
sleep 1
