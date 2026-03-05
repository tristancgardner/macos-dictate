import os
os.environ['OMP_NUM_THREADS'] = '8'
os.environ['MKL_NUM_THREADS'] = '8'
os.environ['VECLIB_MAXIMUM_THREADS'] = '8'

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import AppKit
_process_info = AppKit.NSProcessInfo.processInfo()
_process_info.disableAutomaticTermination_("Dictation active")
_perf_activity = _process_info.beginActivityWithOptions_reason_(
    0x00FFFFFF | 0xFF00000000,
    "Whisper transcription requires performance cores")

import torch
torch.set_num_threads(8)
torch.set_num_interop_threads(4)

import whisper_backend
import sounddevice as sd
import threading
import time
import argparse
import logging
import traceback
import atexit
import signal
from datetime import datetime

src_dir = Path(__file__).parent
project_root = src_dir.parent

from process import show_notification, setup_lock_file, cleanup_lock_file, kill_old_processes
from audio import (
    audio_queue, state_lock, stream_lock,
    audio_callback, select_input_device, test_microphone_access,
    get_current_output_device, restore_output_device, update_heartbeat,
)
import audio
import transcription
import watchdog as watchdog_mod
from keyboard import event_tap_ready, event_tap_failed, run_event_tap
import keyboard as keyboard_mod
from device_monitor import DeviceMonitor

# --------------------------------------
# Command-line argument parsing
# --------------------------------------
def parse_arguments():
    parser = argparse.ArgumentParser(description="Whisper Dictation Tool")
    parser.add_argument(
        '--model',
        type=str,
        default='medium',
        choices=['tiny', 'base', 'small', 'medium', 'large', 'turbo'],
        help='Choose the Whisper model size.'
    )
    parser.add_argument(
        '--device',
        type=str,
        default=None,
        help='Specify input device by name or index. If not provided, uses default input device.'
    )
    return parser.parse_args()

# --------------------------------------
# Load .env.local
# --------------------------------------
ENV_LOCAL_FILE = project_root / '.env.local'
if ENV_LOCAL_FILE.exists():
    with open(ENV_LOCAL_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())

APPEND_BULLET_FILE = os.environ.get('APPEND_BULLET_FILE')
APPEND_BULLET_FILE_2 = os.environ.get('APPEND_BULLET_FILE_2')

LOG_FILE = Path.home() / '.dictate.log'
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --------------------------------------
# Toggle recording function
# --------------------------------------
def toggle_recording():
    """
    - If not recording and not transcribing => Start a new InputStream
    - If currently recording => Stop & transcribe
    - If transcribing => ignore
    """
    with state_lock:
        if transcription.transcribing:
            logging.info("Ignored toggle: transcription in progress.")
            show_notification("Dictation", "Please wait, transcribing...")
            return
        is_recording = audio.recording

    if not is_recording:
        stream_needs_restart = True

        with stream_lock:
            if audio.stream is not None:
                try:
                    if audio.stream.active:
                        stream_needs_restart = False
                        logging.info("Using existing active stream")
                    else:
                        logging.info("Stream exists but is not active, will restart")
                except Exception as e:
                    logging.warning(f"Error checking stream status: {e}")
                    stream_needs_restart = True

            if stream_needs_restart:
                try:
                    saved_output_device = get_current_output_device()

                    if audio.stream is not None:
                        try:
                            audio.stream.stop()
                            audio.stream.close()
                        except Exception as e:
                            logging.warning(f"Error stopping previous stream: {e}")

                    device_index = select_input_device(args.device)
                    device_name = sd.query_devices(device_index)['name']
                    logging.info(f"Using input device: {device_name}")

                    while not audio_queue.empty():
                        audio_queue.get()

                    audio.stream = sd.InputStream(
                        callback=audio_callback,
                        channels=1,
                        samplerate=16000,
                        device=device_index
                    )
                    audio.stream.start()

                    if saved_output_device:
                        restore_output_device(saved_output_device)

                    if not audio.stream.active:
                        raise RuntimeError("Stream failed to start")

                    with state_lock:
                        audio.stream_healthy = True
                        update_heartbeat()

                except Exception as e:
                    logging.error(f"Failed to start stream: {e}")
                    logging.error(traceback.format_exc())
                    show_notification("Dictation Error", "Failed to start recording")
                    with state_lock:
                        audio.stream_healthy = False
                    return

        with state_lock:
            audio.recording = True
            update_heartbeat()
        watchdog_mod.stall_recovery_count = 0
        show_notification("Dictation", "Recording started")
        logging.info("Recording started...")

        def verify_audio_capture():
            with state_lock:
                initial_count = audio.callback_invocation_count
            initial_queue_size = audio_queue.qsize()
            time.sleep(1.0)
            with state_lock:
                if not audio.recording:
                    return
                new_count = audio.callback_invocation_count
                is_still_recording = audio.recording
            new_queue_size = audio_queue.qsize()
            callbacks_received = new_count - initial_count
            items_queued = new_queue_size - initial_queue_size
            min_expected_callbacks = 5
            logging.info(f"Audio verification: {callbacks_received} callbacks, {items_queued} items queued in 1000ms")
            if callbacks_received < min_expected_callbacks:
                logging.warning(f"Audio verification FAILED: Only {callbacks_received} callbacks (expected >= {min_expected_callbacks})")
                stream_active = None
                with stream_lock:
                    if audio.stream is not None:
                        try:
                            stream_active = audio.stream.active
                        except Exception:
                            pass
                logging.warning(f"Stream active: {stream_active}")
                show_notification("Dictation Warning", "Audio may not be flowing - try stopping and restarting")
            elif items_queued == 0 and is_still_recording:
                logging.warning("Audio verification WARNING: Callbacks running but no audio queued")
        threading.Thread(target=verify_audio_capture, daemon=True).start()
    else:
        with state_lock:
            audio.recording = False
            transcription.transcribing = True
            transcription.transcribe_start = datetime.now()
        show_notification("Dictation", "Recording stopped")
        logging.info("Recording stopped, starting transcription thread...")
        threading.Thread(target=transcription.transcribe_audio).start()

# --------------------------------------
# Wire up cross-module references
# --------------------------------------
def _set_append_target(path):
    transcription.append_target = path

keyboard_mod.APPEND_BULLET_FILE = APPEND_BULLET_FILE
keyboard_mod.APPEND_BULLET_FILE_2 = APPEND_BULLET_FILE_2
keyboard_mod._toggle_recording = toggle_recording
keyboard_mod._repaste_last_transcription = transcription.repaste_last_transcription
keyboard_mod._set_append_target = _set_append_target
keyboard_mod._set_auto_enter = lambda v: setattr(transcription, 'auto_enter', v)

transcription.APPEND_BULLET_FILE = APPEND_BULLET_FILE

watchdog_mod._get_device_arg = lambda: args.device

# --------------------------------------
# Main execution
# --------------------------------------
if __name__ == "__main__":
    try:
        args = parse_arguments()
        model_size = args.model

        logging.info("=" * 60)
        logging.info(f"Dictation tool starting (model: {model_size})")
        logging.info("=" * 60)

        # Launch as foreground app (P-core QoS), then immediately hide Dock icon
        NSApp = AppKit.NSApplication.sharedApplication()
        NSApp.setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory

        kill_old_processes()
        time.sleep(0.5)

        logging.info("Starting event tap thread...")
        threading.Thread(target=run_event_tap, daemon=True).start()

        logging.info("Waiting for event tap to initialize...")
        event_tap_ready.wait(timeout=3.0)

        if event_tap_failed.is_set() or not event_tap_ready.is_set():
            logging.error("Event tap failed to start. Exiting.")
            show_notification("Dictation Error", "Accessibility permission denied. Add Python to Accessibility settings.")
            cleanup_lock_file()
            sys.exit(1)

        logging.info("Event tap initialized successfully.")

        os.system('osascript -e \'tell application "System Events" to get the name of every process\'')

        test_microphone_access()

        setup_lock_file()
        atexit.register(cleanup_lock_file)

        device_monitor = None

        def signal_exit_handler(signum, frame):
            logging.info(f"Received signal {signum}, shutting down...")
            watchdog_mod.watchdog_active = False
            if device_monitor is not None:
                try:
                    device_monitor.stop()
                except Exception as e:
                    logging.warning(f"Error stopping device monitor: {e}")
            cleanup_lock_file()
            if audio.stream is not None:
                try:
                    audio.stream.stop()
                    audio.stream.close()
                except Exception as e:
                    logging.warning(f"Error closing stream during shutdown: {e}")
            os._exit(0)

        signal.signal(signal.SIGINT, signal_exit_handler)
        signal.signal(signal.SIGTERM, signal_exit_handler)

        # Load the Whisper model
        logging.info(f"Loading Whisper model '{model_size}'...")
        model = whisper_backend.load_model(model_size)
        transcription.model = model
        logging.info(f"Model loaded successfully. torch.get_num_threads()={torch.get_num_threads()}, "
                     f"torch.get_num_interop_threads()={torch.get_num_interop_threads()}, "
                     f"OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS')}, "
                     f"cpu_count={os.cpu_count()}")

        # Pre-initialize audio stream
        try:
            saved_output_device = get_current_output_device()

            device_index = select_input_device(args.device)
            device_name = sd.query_devices(device_index)['name']
            logging.info(f"Pre-initializing input device: {device_name}")

            audio.stream = sd.InputStream(
                callback=audio_callback,
                channels=1,
                samplerate=16000,
                device=device_index
            )

            if saved_output_device:
                restore_output_device(saved_output_device)

            logging.info("Audio stream pre-initialized successfully.")
            update_heartbeat()
            audio.stream_healthy = True
        except Exception as e:
            logging.error(f"Failed to pre-initialize audio stream: {e}")
            logging.error(traceback.format_exc())

        # Start watchdog
        logging.info("Starting watchdog monitor thread...")
        watchdog_mod.last_polled_device_name = device_name
        watchdog_thread = threading.Thread(target=watchdog_mod.watchdog_monitor, daemon=True)
        watchdog_thread.start()

        # Start device monitor
        logging.info("Starting device monitor...")
        device_monitor = DeviceMonitor(watchdog_mod.apply_device_change)
        if device_monitor.start():
            logging.info("CoreAudio device monitor started successfully")
        else:
            logging.warning("CoreAudio device monitor failed to start, using polling fallback only")
            device_monitor = None

        ready_msg = "Ready (F1=record, F2=repaste"
        if APPEND_BULLET_FILE:
            ready_msg += ", Cmd+F1=TODO"
        ready_msg += ")"
        show_notification("Dictation", ready_msg)

        # Main loop
        try:
            consecutive_failures = 0
            MAX_WATCHDOG_FAILURES = 10
            while True:
                time.sleep(1)
                if not watchdog_thread.is_alive():
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_WATCHDOG_FAILURES:
                        logging.error("Watchdog thread dead for too long, exiting for clean relaunch")
                        show_notification("Dictation Error", "App crashed, please relaunch")
                        cleanup_lock_file()
                        os._exit(1)
                else:
                    consecutive_failures = 0
        except KeyboardInterrupt:
            logging.info("KeyboardInterrupt: Exiting...")
            watchdog_mod.watchdog_active = False
            if device_monitor is not None:
                try:
                    device_monitor.stop()
                except Exception as e:
                    logging.warning(f"Error stopping device monitor: {e}")
            cleanup_lock_file()
            if audio.stream is not None:
                try:
                    audio.stream.stop()
                    audio.stream.close()
                except Exception as e:
                    logging.warning(f"Error closing stream during shutdown: {e}")
            os._exit(0)
    except Exception as e:
        logging.error(f"Critical error in main: {e}")
        logging.error(traceback.format_exc())
        show_notification("Dictation Error", "Program crashed, please restart")
        raise
