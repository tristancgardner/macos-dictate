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
# Watchdog function to monitor system health
# --------------------------------------
def watchdog_monitor():
    global watchdog_active, stream, stream_healthy
    
    logging.info("Watchdog thread started")
    
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
            global watchdog_active
            watchdog_active = False
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
            device_index = select_input_device(args.device)
            device_name = sd.query_devices(device_index)['name']
            logging.info(f"Pre-initializing input device: {device_name}")
            
            stream = sd.InputStream(
                callback=audio_callback,
                channels=1,
                samplerate=16000,
                device=device_index
            )
            
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
        
        # Show notification that we're ready
        show_notification("Dictation", "Ready (press F1 to start)")
    
        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("KeyboardInterrupt: Exiting...")
            watchdog_active = False
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
