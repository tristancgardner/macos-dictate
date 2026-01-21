#!/usr/bin/env python3
"""
Quick terminal test for audio device hot-swap functionality.
Run this, then change your default input device in System Preferences.
"""

import sys
import time
import sounddevice as sd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from device_monitor import (
    DeviceMonitor,
    refresh_sounddevice,
    get_current_default_device_name,
    get_default_input_device_id,
    COREAUDIO_AVAILABLE,
    COREFOUNDATION_AVAILABLE,
)


def on_device_change(old_id, new_id):
    """Callback when device changes."""
    print(f"\n[CALLBACK] Device changed!")
    print(f"  Old device ID: {old_id}")
    print(f"  New device ID: {new_id}")

    # Refresh and show new device info
    refresh_sounddevice()
    new_name = get_current_default_device_name()
    print(f"  New device name: {new_name}")
    print()


def list_input_devices():
    """List all available input devices."""
    print("\nAvailable input devices:")
    print("-" * 50)
    devices = sd.query_devices()
    default_input = sd.default.device[0]

    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            marker = " <-- DEFAULT" if i == default_input else ""
            print(f"  [{i}] {d['name']}{marker}")
    print()


def main():
    print("=" * 60)
    print("Audio Device Monitor Test")
    print("=" * 60)

    # Check CoreAudio availability
    print(f"\nCoreAudio available: {COREAUDIO_AVAILABLE}")
    print(f"CoreFoundation available: {COREFOUNDATION_AVAILABLE}")

    # Show current device
    current_id = get_default_input_device_id()
    current_name = get_current_default_device_name()
    print(f"\nCurrent default input device:")
    print(f"  AudioObjectID: {current_id}")
    print(f"  Name: {current_name}")

    # List all devices
    list_input_devices()

    # Start the monitor
    print("Starting CoreAudio device monitor...")
    monitor = DeviceMonitor(on_device_change)

    if monitor.start():
        print("[OK] Monitor started successfully")
    else:
        print("[WARN] Monitor failed to start, testing polling fallback only")

    print("\n" + "=" * 60)
    print("INSTRUCTIONS:")
    print("  1. Open System Preferences > Sound > Input")
    print("  2. Change the default input device")
    print("  3. Watch for callback messages here")
    print("  4. Press Ctrl+C to exit")
    print("=" * 60 + "\n")

    # Also test polling every 3 seconds
    last_name = current_name
    poll_count = 0

    try:
        while True:
            time.sleep(1)
            poll_count += 1

            # Poll every 3 seconds as backup test
            if poll_count >= 3:
                poll_count = 0
                refresh_sounddevice()
                new_name = get_current_default_device_name()

                if new_name != last_name:
                    print(f"[POLLING] Detected change: {last_name} -> {new_name}")
                    last_name = new_name
                else:
                    # Show heartbeat
                    print(".", end="", flush=True)

    except KeyboardInterrupt:
        print("\n\nStopping monitor...")
        monitor.stop()
        print("Done.")


if __name__ == "__main__":
    main()
