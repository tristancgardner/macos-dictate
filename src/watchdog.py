"""Watchdog monitor for audio stream health and device changes."""

import os
import sys
import logging
import subprocess
import time
import random
import traceback
import queue
import sounddevice as sd
from datetime import datetime

from process import show_notification, cleanup_lock_file
from audio import (
    audio_queue, stream_lock, state_lock,
    audio_callback, select_input_device, test_microphone_access,
    get_current_output_device, restore_output_device, update_heartbeat,
)
from device_monitor import refresh_sounddevice, get_current_default_device_name
import audio
import transcription

# Watchdog state
restart_in_progress = False
stall_recovery_count = 0
MAX_STALL_RETRIES = 3
audio_timeout = 5
last_polled_device_name = None
watchdog_active = True

# Event tap unresponsive threshold (seconds without any keypress going through the tap)
EVENT_TAP_TIMEOUT = 300  # 5 minutes with zero key events = likely frozen

# Set by dictate.py
_get_device_arg = None


def watchdog_monitor():
    global last_polled_device_name, stall_recovery_count, watchdog_active

    logging.info("Watchdog thread started")

    poll_counter = 0
    DEVICE_POLL_INTERVAL = 5

    while watchdog_active:
        try:
            with state_lock:
                is_recording = audio.recording
                is_transcribing = transcription.transcribing
                heartbeat_copy = audio.last_heartbeat
                callback_count_copy = audio.callback_invocation_count
                transcribe_start_copy = transcription.transcribe_start

            if is_recording:
                time_since_heartbeat = (datetime.now() - heartbeat_copy).total_seconds()

                if time_since_heartbeat > 2:
                    stream_active = None
                    with stream_lock:
                        if audio.stream is not None:
                            try:
                                stream_active = audio.stream.active
                            except Exception:
                                pass
                    if stream_active is not None:
                        logging.warning(f"Heartbeat stale ({time_since_heartbeat:.1f}s) but stream.active={stream_active}, callbacks={callback_count_copy}")

                if time_since_heartbeat > audio_timeout:
                    logging.warning(f"Audio system stalled! No heartbeat for {time_since_heartbeat:.1f}s")
                    stream_active = None
                    with stream_lock:
                        if audio.stream is not None:
                            try:
                                stream_active = audio.stream.active
                            except Exception:
                                pass
                    logging.warning(f"Stream state: active={stream_active}, queue_size={audio_queue.qsize()}")

                    with state_lock:
                        audio.recording = False
                        audio.last_heartbeat = datetime.now()

                    stall_recovery_count += 1
                    if stall_recovery_count > MAX_STALL_RETRIES:
                        logging.error(f"Stall recovery failed {stall_recovery_count} times, giving up. User must restart.")
                        show_notification("Dictation Error", "Audio system unresponsive. Please restart the app.")
                        continue
                    else:
                        show_notification("Dictation Error", f"Audio stalled, recovering (attempt {stall_recovery_count}/{MAX_STALL_RETRIES})...")
                        restart_audio_stream()

            if is_transcribing and transcribe_start_copy is not None:
                transcribe_elapsed = (datetime.now() - transcribe_start_copy).total_seconds()
                if transcribe_elapsed > 90:
                    logging.error(f"Transcription stuck for {transcribe_elapsed:.0f}s, force-clearing state")
                    with state_lock:
                        transcription.transcribing = False
                        transcription.transcribe_start = None
                        transcription.append_target = None
                    show_notification("Dictation Error", "Transcription timed out, ready for new recording")

            # Check event tap heartbeat — if no key events for EVENT_TAP_TIMEOUT, the tap is frozen
            from keyboard import tap_heartbeat, tap_heartbeat_lock
            with tap_heartbeat_lock:
                tap_age = (datetime.now() - tap_heartbeat).total_seconds()
            if tap_age > EVENT_TAP_TIMEOUT:
                logging.error(f"Event tap unresponsive for {tap_age:.0f}s — auto-restarting app")
                show_notification("Dictation", "Event tap frozen, restarting...")
                _force_restart()

            if not is_recording and not is_transcribing:
                stream_is_none = False
                with stream_lock:
                    stream_is_none = (audio.stream is None)

                if stream_is_none:
                    if random.random() < 0.1:
                        try:
                            test_microphone_access()
                            with state_lock:
                                audio.stream_healthy = True
                        except Exception as e:
                            logging.error(f"Microphone access failed in watchdog: {e}")
                            with state_lock:
                                audio.stream_healthy = False

            poll_counter += 1
            if poll_counter >= DEVICE_POLL_INTERVAL and not is_recording and not is_transcribing:
                poll_counter = 0
                try:
                    current_device_name = get_current_default_device_name()

                    if last_polled_device_name is not None and current_device_name != last_polled_device_name:
                        logging.info(f"Polling detected device change: {last_polled_device_name} -> {current_device_name}")
                        refresh_sounddevice()
                        apply_device_change()

                    last_polled_device_name = current_device_name

                except Exception as e:
                    logging.warning(f"Device polling error: {e}")

            time.sleep(1)

        except Exception as e:
            logging.error(f"Watchdog error: {e}")
            logging.error(traceback.format_exc())
            time.sleep(5)


def _force_restart():
    """Force-restart the app by spawning a new instance and exiting."""
    try:
        current_path = os.path.abspath(sys.executable)
        if '.app/Contents/' in current_path:
            bundle_path = current_path.split('.app/Contents/')[0] + '.app'
            logging.info(f"Watchdog relaunching .app bundle: {bundle_path}")
            subprocess.Popen(['open', '-n', bundle_path],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        else:
            script_path = os.path.abspath(sys.modules['__main__'].__file__)
            logging.info(f"Watchdog relaunching Python script: {script_path}")
            subprocess.Popen([sys.executable, script_path],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        time.sleep(0.5)
    except Exception as e:
        logging.error(f"Watchdog failed to relaunch: {e}")
    cleanup_lock_file()
    os._exit(1)


def restart_audio_stream():
    """Safely restart the audio stream with thread-safe guards"""
    global restart_in_progress

    if not stream_lock.acquire(blocking=False):
        logging.info("Restart skipped: another restart in progress (lock held)")
        return

    try:
        if restart_in_progress:
            logging.info("Restart skipped: another restart in progress (flag set)")
            return

        restart_in_progress = True

        with state_lock:
            if transcription.transcribing:
                logging.info("Restart skipped: transcription in progress")
                return
            if audio.recording:
                logging.info("Restart skipped: recording in progress (protecting queued audio)")
                return

        logging.info("Attempting to restart audio stream")

        saved_output_device = get_current_output_device()

        if audio.stream is not None:
            try:
                audio.stream.stop()
                audio.stream.close()
            except Exception as e:
                logging.warning(f"Error closing old stream: {e}")

        queue_cleared = 0
        while not audio_queue.empty():
            try:
                audio_queue.get_nowait()
                queue_cleared += 1
            except queue.Empty:
                break
        if queue_cleared > 0:
            logging.info(f"Cleared {queue_cleared} stale items from audio queue")

        device_arg = _get_device_arg() if _get_device_arg else None
        device_index = select_input_device(device_arg)
        device_name = sd.query_devices(device_index)['name']
        logging.info(f"Recreating stream with device: {device_name}")

        audio.stream = sd.InputStream(
            callback=audio_callback,
            channels=1,
            samplerate=16000,
            device=device_index
        )
        audio.stream.start()

        if saved_output_device:
            restore_output_device(saved_output_device)

        with state_lock:
            audio.stream_healthy = True
            update_heartbeat()

        logging.info("Audio stream restarted successfully (silent recovery)")

    except Exception as e:
        logging.error(f"Failed to restart audio stream: {e}")
        logging.error(traceback.format_exc())
        with state_lock:
            audio.stream_healthy = False
            audio.recording = False
        show_notification("Dictation Error", "Failed to restart audio")
    finally:
        restart_in_progress = False
        stream_lock.release()


def apply_device_change(old_device_id=None, new_device_id=None):
    """Handle audio device change by refreshing sounddevice and recreating stream."""
    global last_polled_device_name

    logging.info(f"Device change detected: {old_device_id} -> {new_device_id}")

    with state_lock:
        if audio.recording:
            logging.info("Device change ignored: recording in progress")
            return
        if transcription.transcribing:
            logging.info("Device change ignored: transcription in progress")
            return

    with stream_lock:
        try:
            if audio.stream is not None:
                try:
                    if audio.stream.active:
                        audio.stream.stop()
                    audio.stream.close()
                    logging.info("Closed existing audio stream")
                except Exception as e:
                    logging.warning(f"Error closing stream during device change: {e}")
                audio.stream = None

            refresh_sounddevice()

            new_device_name = get_current_default_device_name()
            last_polled_device_name = new_device_name
            logging.info(f"New default input device: {new_device_name}")

            device_arg = _get_device_arg() if _get_device_arg else None
            device_index = select_input_device(device_arg)
            actual_device_name = sd.query_devices(device_index)['name']
            logging.info(f"Creating new stream with device: {actual_device_name}")

            audio.stream = sd.InputStream(
                callback=audio_callback,
                channels=1,
                samplerate=16000,
                device=device_index
            )
            audio.stream.start()
            logging.info("Started new audio stream after device change")

            with state_lock:
                audio.stream_healthy = True
                update_heartbeat()

            show_notification("Dictation", f"Switched to: {actual_device_name}")
            logging.info("Audio stream recreated with new device")

        except Exception as e:
            logging.error(f"Failed to apply device change: {e}")
            logging.error(traceback.format_exc())
            with state_lock:
                audio.stream_healthy = False
            show_notification("Dictation Error", "Failed to switch audio device")
