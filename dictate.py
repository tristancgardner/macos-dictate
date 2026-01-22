import whisper
import sounddevice as sd
import numpy as np
import threading
import queue
import os
import time
import argparse
import sys
import Quartz
import AppKit  # PyObjC library
import subprocess
import logging
from pathlib import Path
import re
import psutil
import atexit
import signal
import traceback
import random
from datetime import datetime

from pathlib import Path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
from text_postprocessor import cleanup_text, send_text_to_active_app
from device_monitor import DeviceMonitor, refresh_sounddevice, get_current_default_device_name, COREAUDIO_AVAILABLE

# --------------------------------------
# Command-line argument parsing
# --------------------------------------
def parse_arguments():
    parser = argparse.ArgumentParser(description="Whisper Dictation Tool")
    parser.add_argument(
        '--model',
        type=str,
        default='base',
        choices=['tiny', 'base', 'small', 'medium', 'large'],
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
# Global variables
# --------------------------------------
audio_queue = queue.Queue()
recording = False
transcribing = False
stream = None
last_heartbeat = datetime.now()
stream_healthy = False
watchdog_active = True
audio_timeout = 10  # seconds before we consider audio system stalled
device_monitor = None  # CoreAudio device change monitor
last_polled_device_name = None  # For polling fallback

LOG_FILE = Path.home() / '.dictate.log'
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

LOCK_FILE = "/tmp/dictate.lock"

# --------------------------------------
# Lock-file handling
# --------------------------------------
def setup_lock_file():
    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, "r") as f:
            old_pid = int(f.read().strip())
            if psutil.pid_exists(old_pid):
                print(f"Another instance is already running with PID {old_pid}. Exiting.")
                sys.exit(0)
    
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

def cleanup_lock_file():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
        print("Lock file removed.")

# --------------------------------------
# (Optional) Kill old processes
# Comment out if you suspect concurrency issues
# --------------------------------------
def kill_old_processes():
    try:
        result = subprocess.check_output(["pgrep", "-f", "dictate.py"]).decode().splitlines()
        current_pid = os.getpid()
        for pid in result:
            if int(pid) != current_pid:  # Skip the current process
                logging.info(f"Killing old process with PID {pid}")
                os.kill(int(pid), signal.SIGTERM)
    except subprocess.CalledProcessError:
        logging.info("No old processes found to kill.")

# --------------------------------------
# Event tap callback
# --------------------------------------
def tap_callback(proxy, type_, event, refcon):
    keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
    flags = Quartz.CGEventGetFlags(event)

    # F1 key => Toggle recording
    if keycode == 122:  # F1
        logging.info("F1 key detected.")
        toggle_recording()
        return None  # Suppress the F1 keystroke so it won't pass through

    # F2 key => Repaste last transcription
    if keycode == 120:  # F2
        logging.info("F2 key detected.")
        repaste_last_transcription()
        return None  # Suppress the F2 keystroke so it won't pass through

    # Option+Shift+D => Quit
    if type_ == Quartz.kCGEventKeyDown and keycode == 2:  # 'D'
        shift_pressed = (flags & Quartz.kCGEventFlagMaskShift) == Quartz.kCGEventFlagMaskShift
        option_pressed = (flags & Quartz.kCGEventFlagMaskAlternate) == Quartz.kCGEventFlagMaskAlternate
        
        if shift_pressed and option_pressed:
            logging.info("Option+Shift+D detected. Exiting.")
            cleanup_lock_file()
            os._exit(0)
    
    return event

# --------------------------------------
# Run the event tap in a separate thread
# --------------------------------------
def run_event_tap():
    event_mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault,
        event_mask,
        tap_callback,
        None
    )
    if not tap:
        logging.error("Failed to create event tap. Check Accessibility permissions.")
        sys.exit(1)

    run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(
        Quartz.CFRunLoopGetCurrent(),
        run_loop_source,
        Quartz.kCFRunLoopCommonModes
    )
    Quartz.CGEventTapEnable(tap, True)
    logging.info("Event tap started successfully.")
    Quartz.CFRunLoopRun()

# --------------------------------------
# Audio callback
# --------------------------------------
def audio_callback(indata, frames, time_info, status):
    try:
        if status:
            logging.warning(f"Audio callback status: {status}")
        
        if recording:
            audio_queue.put(indata.copy())
            
        # Update heartbeat regardless of recording status
        # This shows the audio system is active
        update_heartbeat()
    except Exception as e:
        logging.error(f"Error in audio callback: {e}")
        logging.error(traceback.format_exc())

# --------------------------------------
# Toggle recording function
# --------------------------------------
def toggle_recording():
    """
    - If not recording and not transcribing => Start a new InputStream 
    - If currently recording => Stop & transcribe 
    - If transcribing => ignore
    """
    global recording, transcribing, stream, stream_healthy

    if transcribing:
        logging.info("Ignored toggle: transcription in progress.")
        show_notification("Dictation", "Please wait, transcribing...")
        return

    if not recording:
        # Check if we need to create a new stream or use existing one
        stream_needs_restart = True
        
        # Check if stream exists and is valid
        if stream is not None:
            try:
                # Test if stream is active by checking if it's stopped
                if stream.active:
                    stream_needs_restart = False
                    logging.info("Using existing active stream")
                else:
                    logging.info("Stream exists but is not active, will restart")
            except Exception as e:
                logging.warning(f"Error checking stream status: {e}")
                stream_needs_restart = True
        
        # Restart stream if needed
        if stream_needs_restart:
            try:
                # Save current output device before any audio changes
                saved_output_device = get_current_output_device()

                # Close old stream if it exists
                if stream is not None:
                    try:
                        stream.stop()
                        stream.close()
                    except Exception as e:
                        logging.warning(f"Error stopping previous stream: {e}")

                device_index = select_input_device(args.device)
                device_name = sd.query_devices(device_index)['name']
                logging.info(f"Using input device: {device_name}")

                # Clear any old data from the queue
                while not audio_queue.empty():
                    audio_queue.get()

                stream = sd.InputStream(
                    callback=audio_callback,
                    channels=1,
                    samplerate=16000,
                    device=device_index
                )
                stream.start()

                # Restore output device if it was changed
                if saved_output_device:
                    restore_output_device(saved_output_device)

                # Verify stream started correctly
                if not stream.active:
                    raise RuntimeError("Stream failed to start")

                stream_healthy = True
                update_heartbeat()
                
            except Exception as e:
                logging.error(f"Failed to start stream: {e}")
                logging.error(traceback.format_exc())
                show_notification("Dictation Error", "Failed to start recording")
                stream_healthy = False
                return  # Exit without setting recording=True
        
        # Start recording with the stream
        recording = True
        show_notification("Dictation", "Recording started")
        logging.info("Recording started...")
        update_heartbeat()  # Reset heartbeat timer
    else:
        # Stop recording, start transcription
        recording = False
        show_notification("Dictation", "Recording stopped")
        logging.info("Recording stopped, starting transcription thread...")
        threading.Thread(target=transcribe_audio).start()

# --------------------------------------
# Repaste last transcription (F2)
# --------------------------------------
def repaste_last_transcription():
    """Repaste the last transcription by reading from the log file."""
    try:
        if not LOG_FILE.exists():
            logging.info("No log file found for repaste.")
            show_notification("Dictation", "No previous transcription")
            return

        # Read log file and search backwards for most recent transcription
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()

        # Search backwards for "Cleaned transcribed text:"
        pattern = re.compile(r"Cleaned transcribed text: '(.+)'$")
        for line in reversed(lines):
            match = pattern.search(line)
            if match:
                text = match.group(1)
                logging.info(f"Repasting from log: '{text}'")
                send_text_to_active_app(text)
                show_notification("Dictation", "Repasted last transcription")
                return

        logging.info("No transcription found in log file.")
        show_notification("Dictation", "No previous transcription")

    except Exception as e:
        logging.error(f"Error repasting from log: {e}")
        show_notification("Dictation", "Failed to repaste")

# --------------------------------------
# Watchdog function to monitor system health
# --------------------------------------
def watchdog_monitor():
    global watchdog_active, stream, stream_healthy, last_polled_device_name

    logging.info("Watchdog thread started")

    poll_counter = 0
    DEVICE_POLL_INTERVAL = 5  # seconds between device polling

    while watchdog_active:
        try:
            # Check if audio stream is healthy when recording
            if recording:
                time_since_heartbeat = (datetime.now() - last_heartbeat).total_seconds()

                if time_since_heartbeat > audio_timeout:
                    logging.warning(f"Audio system stalled! No heartbeat for {time_since_heartbeat:.1f}s")
                    show_notification("Dictation Error", "Audio system stalled, recovering...")

                    # Force restart the audio stream
                    restart_audio_stream()

            # Periodically check sounddevice status when not recording
            elif not recording and not transcribing and stream is None:
                # Every ~10 seconds, check that we can still access audio
                if random.random() < 0.1:  # 10% chance each cycle
                    try:
                        test_microphone_access()
                        stream_healthy = True
                    except Exception as e:
                        logging.error(f"Microphone access failed in watchdog: {e}")
                        stream_healthy = False

            # Polling fallback for device changes (backup for CoreAudio listener)
            poll_counter += 1
            if poll_counter >= DEVICE_POLL_INTERVAL and not recording and not transcribing:
                poll_counter = 0
                try:
                    # Refresh and check current default device
                    refresh_sounddevice()
                    current_device_name = get_current_default_device_name()

                    if last_polled_device_name is not None and current_device_name != last_polled_device_name:
                        logging.info(f"Polling detected device change: {last_polled_device_name} -> {current_device_name}")
                        apply_device_change()
                    else:
                        last_polled_device_name = current_device_name

                except Exception as e:
                    logging.warning(f"Device polling error: {e}")

            # Sleep to avoid consuming too much CPU
            time.sleep(1)

        except Exception as e:
            logging.error(f"Watchdog error: {e}")
            logging.error(traceback.format_exc())
            time.sleep(5)  # Wait longer after an error

def restart_audio_stream():
    """Safely restart the audio stream"""
    global stream, recording, transcribing, audio_queue
    
    logging.info("Attempting to restart audio stream")

    try:
        # Save current output device before any audio changes
        saved_output_device = get_current_output_device()

        # Close old stream if it exists
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as e:
                logging.warning(f"Error closing old stream: {e}")

        # Recreate stream with same device as before
        device_index = select_input_device(args.device)
        device_name = sd.query_devices(device_index)['name']
        logging.info(f"Recreating stream with device: {device_name}")

        stream = sd.InputStream(
            callback=audio_callback,
            channels=1,
            samplerate=16000,
            device=device_index
        )
        stream.start()

        # Restore output device if it was changed
        if saved_output_device:
            restore_output_device(saved_output_device)

        # Update status
        stream_healthy = True

        # Reset heartbeat
        update_heartbeat()

        show_notification("Dictation", "Audio system recovered")
        logging.info("Audio stream successfully restarted")
        
    except Exception as e:
        logging.error(f"Failed to restart audio stream: {e}")
        logging.error(traceback.format_exc())
        stream_healthy = False
        recording = False
        show_notification("Dictation Error", "Failed to restart audio")

def update_heartbeat():
    """Update the heartbeat timestamp"""
    global last_heartbeat
    last_heartbeat = datetime.now()


def apply_device_change(old_device_id=None, new_device_id=None):
    """
    Handle audio device change by refreshing sounddevice and recreating stream.

    Called by CoreAudio listener when default input device changes, or by
    polling fallback when a device change is detected.
    """
    global stream, stream_healthy, last_polled_device_name

    logging.info(f"Device change detected: {old_device_id} -> {new_device_id}")

    # Don't switch devices while actively recording
    if recording:
        logging.info("Device change ignored: recording in progress")
        return

    # Don't switch while transcribing
    if transcribing:
        logging.info("Device change ignored: transcription in progress")
        return

    try:
        # Close existing stream before refreshing device list
        if stream is not None:
            try:
                if stream.active:
                    stream.stop()
                stream.close()
                logging.info("Closed existing audio stream")
            except Exception as e:
                logging.warning(f"Error closing stream during device change: {e}")
            stream = None

        # Refresh sounddevice/PortAudio device cache
        refresh_sounddevice()

        # Get the new default device info
        new_device_name = get_current_default_device_name()
        last_polled_device_name = new_device_name
        logging.info(f"New default input device: {new_device_name}")

        # Pre-initialize new stream with new device
        device_index = select_input_device(args.device)
        actual_device_name = sd.query_devices(device_index)['name']
        logging.info(f"Creating new stream with device: {actual_device_name}")

        stream = sd.InputStream(
            callback=audio_callback,
            channels=1,
            samplerate=16000,
            device=device_index
        )

        stream_healthy = True
        update_heartbeat()

        show_notification("Dictation", f"Switched to: {actual_device_name}")
        logging.info("Audio stream recreated with new device")

    except Exception as e:
        logging.error(f"Failed to apply device change: {e}")
        logging.error(traceback.format_exc())
        stream_healthy = False
        show_notification("Dictation Error", "Failed to switch audio device")

# --------------------------------------
# Output device preservation functions
# --------------------------------------
def get_current_output_device():
    """Get the current system output device name."""
    try:
        # Try using SwitchAudioSource if available
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

    # Fallback to AppleScript
    try:
        script = 'tell application "System Preferences" to quit'
        subprocess.run(['osascript', '-e', script], capture_output=True, timeout=2)

        script = '''
        tell application "System Preferences"
            reveal anchor "output" of pane id "com.apple.preference.sound"
        end tell
        delay 0.5
        tell application "System Events"
            tell process "System Preferences"
                set outputDevice to value of text field 1 of row 1 of table 1 of scroll area 1 of tab group 1 of window 1
            end tell
        end tell
        tell application "System Preferences" to quit
        return outputDevice
        '''
        # This AppleScript approach is complex and may not work reliably
        # Instead, use sounddevice's default device query
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
        # Try using SwitchAudioSource if available
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

    # Note: AppleScript fallback for setting output device is complex and unreliable
    # If SwitchAudioSource is not available, log a warning
    logging.warning(f"Could not restore output device. Install SwitchAudioSource: brew install switchaudio-osx")
    return False

# --------------------------------------
# Select input device
# --------------------------------------
def select_input_device(device_arg):
    if device_arg is not None:
        devices = sd.query_devices()
        # Try to interpret as index
        try:
            idx = int(device_arg)
            if 0 <= idx < len(devices):
                return idx
        except ValueError:
            pass
        # Else try substring match by name
        for i, d in enumerate(devices):
            if device_arg.lower() in d['name'].lower():
                return i
        logging.warning(f"Specified device '{device_arg}' not found. Using default.")
    
    default_input_device = sd.default.device[0]
    if default_input_device is None:
        # fallback to first available
        for i, d in enumerate(sd.query_devices()):
            if d['max_input_channels'] > 0:
                logging.info(f"Found available device: {d['name']}")
                return i
        raise RuntimeError("No input devices found.")
    
    return default_input_device

# --------------------------------------
# Show macOS notification
# --------------------------------------
def show_notification(title, message):
    os.system(f'''osascript -e 'display notification "{message}" with title "{title}"' ''')

# --------------------------------------
# Transcribe audio (runs in a thread)
# --------------------------------------
def transcribe_audio():
    global transcribing
    transcribing = True
    transcribe_start_time = datetime.now()
    max_transcribe_time = 60  # seconds before transcription times out

    try:
        # Gather audio from the queue
        audio_data = []
        try:
            # Use a timeout when getting from the queue
            while not audio_queue.empty():
                try:
                    item = audio_queue.get(timeout=1.0)
                    audio_data.append(item)
                except queue.Empty:
                    break
        except Exception as e:
            logging.error(f"Error gathering audio data: {e}")
            
        if not audio_data:
            logging.info("No audio data captured; skipping transcription.")
            show_notification("Dictation", "No audio recorded")
            transcribing = False
            return

        audio = np.concatenate(audio_data, axis=0).flatten()
        logging.info(f"Captured {len(audio)} samples from queue.")

        # Check amplitude to avoid feeding near-empty audio
        max_amp = np.max(np.abs(audio))
        logging.info(f"Max amplitude of audio: {max_amp}")
        if max_amp < 1e-5:  # Arbitrary tiny threshold
            logging.info("Audio is essentially silent; skipping transcription.")
            show_notification("Dictation", "Audio too quiet, try again")
            transcribing = False
            return

        # Normalize
        audio = audio / max_amp

        # Transcribe with timeout monitoring in a separate thread
        logging.info("Beginning Whisper transcription...")
        
        # Create a thread-safe container for the result
        result_container = {"success": False, "result": None, "error": None}
        
        def transcribe_with_timeout():
            try:
                result_container["result"] = model.transcribe(audio, fp16=False)
                result_container["success"] = True
            except Exception as e:
                result_container["error"] = str(e)
                logging.error(f"Transcription error: {e}")
                logging.error(traceback.format_exc())
        
        # Start transcription in a separate thread
        transcribe_thread = threading.Thread(target=transcribe_with_timeout)
        transcribe_thread.daemon = True
        transcribe_thread.start()
        
        # Monitor the thread with timeout
        timeout_reached = False
        while transcribe_thread.is_alive():
            # Check if we've exceeded the time limit
            elapsed = (datetime.now() - transcribe_start_time).total_seconds()
            if elapsed > max_transcribe_time:
                timeout_reached = True
                logging.warning(f"Transcription timed out after {elapsed:.1f} seconds")
                show_notification("Dictation", "Transcription is taking too long, try again")
                # We can't stop the thread, but we can stop waiting for it
                break
            time.sleep(0.5)
            
        if timeout_reached:
            transcribing = False
            return
            
        if not result_container["success"]:
            logging.error(f"Transcription failed: {result_container['error']}")
            show_notification("Dictation Error", "Transcription failed")
            transcribing = False
            return
            
        # Process the transcription result
        result = result_container["result"]
        text = result['text'].strip()
        logging.info(f"Raw transcribed text: '{text}'")

        text = cleanup_text(text).strip() + " "
        logging.info(f"Cleaned transcribed text: '{text}'")

        # Send text to active application
        if text:
            send_text_to_active_app(text)
        else:
            logging.info("No text to paste (empty transcription).")
            show_notification("Dictation", "No text detected")

    except Exception as e:
        logging.error(f"Error in transcription process: {e}")
        logging.error(traceback.format_exc())
        show_notification("Dictation Error", "Transcription error")
    
    finally:
        transcribing = False

# --------------------------------------
# Test microphone access
# --------------------------------------
def test_microphone_access():
    try:
        sd.check_input_settings()
        logging.info("Microphone access test passed.")
    except Exception as e:
        logging.error(f"Microphone access test failed: {e}")

# --------------------------------------
# Main execution
# --------------------------------------
if __name__ == "__main__":
    try:
        # Parse arguments first so we have access to them in other functions
        args = parse_arguments()
        model_size = args.model
        
        # Configure more detailed logging for stability tracking
        logging.info("=" * 60)
        logging.info(f"Dictation tool starting (model: {model_size})")
        logging.info("=" * 60)
    
        # Start the event tap in a separate thread
        logging.info("Starting event tap thread...")
        threading.Thread(target=run_event_tap, daemon=True).start()
    
        # (Optional) kill old processes
        kill_old_processes()
    
        # Force macOS to show processes, ensuring the script is recognized
        os.system('osascript -e \'tell application "System Events" to get the name of every process\'')
    
        # Trigger mic permission prompt if needed
        test_microphone_access()
    
        # Setup lock file & cleanup
        setup_lock_file()
        atexit.register(cleanup_lock_file)
    
        def signal_exit_handler(signum, frame):
            logging.info(f"Received signal {signum}, shutting down...")
            global watchdog_active, device_monitor
            watchdog_active = False
            # Stop device monitor
            if device_monitor is not None:
                try:
                    device_monitor.stop()
                except Exception as e:
                    logging.warning(f"Error stopping device monitor: {e}")
            cleanup_lock_file()
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as e:
                    logging.warning(f"Error closing stream during shutdown: {e}")
            os._exit(0)
    
        signal.signal(signal.SIGINT, signal_exit_handler)
        signal.signal(signal.SIGTERM, signal_exit_handler)
        
        # Load the Whisper model
        logging.info(f"Loading Whisper model '{model_size}'...")
        model = whisper.load_model(model_size)
        logging.info("Model loaded successfully.")
        
        # Prepare audio stream for listening
        # Pre-initialize stream to avoid delays when starting to record
        try:
            # Save current output device before any audio changes
            saved_output_device = get_current_output_device()

            device_index = select_input_device(args.device)
            device_name = sd.query_devices(device_index)['name']
            logging.info(f"Pre-initializing input device: {device_name}")

            stream = sd.InputStream(
                callback=audio_callback,
                channels=1,
                samplerate=16000,
                device=device_index
            )

            # Restore output device if it was changed during initialization
            if saved_output_device:
                restore_output_device(saved_output_device)

            # Don't start the stream yet, just initialize it
            logging.info("Audio stream pre-initialized successfully.")
            update_heartbeat()
            stream_healthy = True
        except Exception as e:
            logging.error(f"Failed to pre-initialize audio stream: {e}")
            logging.error(traceback.format_exc())
            
        # Start the watchdog thread
        logging.info("Starting watchdog monitor thread...")
        watchdog_thread = threading.Thread(target=watchdog_monitor, daemon=True)
        watchdog_thread.start()

        # Initialize polling baseline
        last_polled_device_name = device_name

        # Start the device monitor (CoreAudio listener)
        logging.info("Starting device monitor...")
        device_monitor = DeviceMonitor(apply_device_change)
        if device_monitor.start():
            logging.info("CoreAudio device monitor started successfully")
        else:
            logging.warning("CoreAudio device monitor failed to start, using polling fallback only")
            device_monitor = None

        # Show notification that we're ready
        show_notification("Dictation", "Ready (F1=record, F2=repaste)")
    
        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("KeyboardInterrupt: Exiting...")
            watchdog_active = False
            if device_monitor is not None:
                try:
                    device_monitor.stop()
                except Exception as e:
                    logging.warning(f"Error stopping device monitor: {e}")
            cleanup_lock_file()
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as e:
                    logging.warning(f"Error closing stream during shutdown: {e}")
            os._exit(0)
    except Exception as e:
        logging.error(f"Critical error in main: {e}")
        logging.error(traceback.format_exc())
        show_notification("Dictation Error", "Program crashed, please restart")
        raise
