"""Audio stream management and input device selection."""

import logging
import threading
import queue
import traceback
import subprocess
import sounddevice as sd
from datetime import datetime

from process import show_notification

# Audio globals
audio_queue = queue.Queue()
recording = False
stream = None
stream_healthy = False
last_heartbeat = datetime.now()
callback_invocation_count = 0

# Thread synchronization
state_lock = threading.RLock()   # Protects: recording, transcribing, stream_healthy, last_heartbeat, callback_count
stream_lock = threading.Lock()   # Protects: stream object, restart operations


def update_heartbeat():
    """Update the heartbeat timestamp under lock for cross-thread visibility"""
    global last_heartbeat
    with state_lock:
        last_heartbeat = datetime.now()


def audio_callback(indata, frames, time_info, status):
    global callback_invocation_count
    try:
        if status:
            logging.warning(f"Audio callback status: {status}")

        callback_invocation_count += 1

        if recording:
            audio_queue.put(indata.copy())

        update_heartbeat()
    except Exception as e:
        logging.error(f"Error in audio callback: {e}")
        logging.error(traceback.format_exc())


def select_input_device(device_arg):
    if device_arg is not None:
        devices = sd.query_devices()
        try:
            idx = int(device_arg)
            if 0 <= idx < len(devices):
                return idx
        except ValueError:
            pass
        for i, d in enumerate(devices):
            if device_arg.lower() in d['name'].lower():
                return i
        logging.warning(f"Specified device '{device_arg}' not found. Using default.")

    default_input_device = sd.default.device[0]
    if default_input_device is None:
        for i, d in enumerate(sd.query_devices()):
            if d['max_input_channels'] > 0:
                logging.info(f"Found available device: {d['name']}")
                return i
        raise RuntimeError("No input devices found.")

    return default_input_device


def test_microphone_access():
    try:
        sd.check_input_settings()
        logging.info("Microphone access test passed.")
    except Exception as e:
        logging.error(f"Microphone access test failed: {e}")


def get_current_output_device():
    """Get the current system output device name."""
    try:
        result = subprocess.run(
            ['SwitchAudioSource', '-c', '-t', 'output'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            device_name = result.stdout.strip()
            logging.info(f"Current output device: {device_name}")
            return device_name
    except FileNotFoundError:
        logging.debug("SwitchAudioSource not found, using AppleScript fallback")
    except Exception as e:
        logging.warning(f"Error getting output device via SwitchAudioSource: {e}")

    try:
        default_output = sd.default.device[1]
        if default_output is not None:
            devices = sd.query_devices()
            if 0 <= default_output < len(devices):
                device_name = devices[default_output]['name']
                logging.info(f"Current output device (via sounddevice): {device_name}")
                return device_name
    except Exception as e:
        logging.warning(f"Error getting output device: {e}")

    return None


def restore_output_device(device_name):
    """Restore the system output device to the specified device."""
    if device_name is None:
        return

    try:
        result = subprocess.run(
            ['SwitchAudioSource', '-s', device_name, '-t', 'output'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            logging.info(f"Restored output device to: {device_name}")
            return True
    except FileNotFoundError:
        logging.debug("SwitchAudioSource not found, cannot restore output device")
    except Exception as e:
        logging.warning(f"Error restoring output device via SwitchAudioSource: {e}")

    logging.warning(f"Could not restore output device. Install SwitchAudioSource: brew install switchaudio-osx")
    return False
