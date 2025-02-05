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
    if recording:
        audio_queue.put(indata.copy())

# --------------------------------------
# Toggle recording function
# --------------------------------------
def toggle_recording():
    """
    - If not recording and not transcribing => Start a new InputStream 
    - If currently recording => Stop & transcribe 
    - If transcribing => ignore
    """
    global recording, transcribing, stream

    if transcribing:
        logging.info("Ignored toggle: transcription in progress.")
        return

    if not recording:
        # Re-initialize the stream with the user-selected (or default) device
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as e:
                logging.warning(f"Error stopping previous stream: {e}")

        device_index = select_input_device(args.device)
        device_name = sd.query_devices(device_index)['name']
        logging.info(f"Using input device: {device_name}")

        stream = sd.InputStream(
            callback=audio_callback,
            channels=1,
            samplerate=16000,
            device=device_index
        )
        stream.start()

        recording = True
        show_notification("Dictation", "Recording started")
        logging.info("Recording started...")
    else:
        # Stop recording, start transcription
        recording = False
        show_notification("Dictation", "Recording stopped")
        logging.info("Recording stopped, starting transcription thread...")
        threading.Thread(target=transcribe_audio).start()

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

    # Gather audio from the queue
    audio_data = []
    while not audio_queue.empty():
        audio_data.append(audio_queue.get())
    if not audio_data:
        logging.info("No audio data captured; skipping transcription.")
        transcribing = False
        return

    audio = np.concatenate(audio_data, axis=0).flatten()
    logging.info(f"Captured {len(audio)} samples from queue.")

    # Check amplitude to avoid feeding near-empty audio
    max_amp = np.max(np.abs(audio))
    logging.info(f"Max amplitude of audio: {max_amp}")
    if max_amp < 1e-5:  # Arbitrary tiny threshold
        logging.info("Audio is essentially silent; skipping transcription.")
        transcribing = False
        return

    # Normalize
    audio = audio / max_amp

    # Transcribe
    logging.info("Beginning Whisper transcription...")
    result = model.transcribe(audio, fp16=False)
    text = result['text'].strip()
    logging.info(f"Raw transcribed text: '{text}'")

    text = cleanup_text(text).strip() + " "
    logging.info(f"Cleaned transcribed text: '{text}'")

    # Send text to active application
    if text:
        send_text_to_active_app(text)
    else:
        logging.info("No text to paste (empty transcription).")

    transcribing = False

# --------------------------------------
# Text cleanup
# --------------------------------------
def cleanup_text(text):
    # Single spaces after punctuation
    text = re.sub(r'\s*([.,?!])\s*', r'\1 ', text)

    # Remove extra punctuation before a newline
    text = re.sub(r'[.,]\s*\n', r'\n', text)

    # Standardize multiple newlines => double newline
    text = re.sub(r'\n+', '\n\n', text)

    # Trim each line
    text = "\n".join(line.strip() for line in text.splitlines())

    return text

# --------------------------------------
# Send text to active app via clipboard and Cmd+V
# --------------------------------------
def send_text_to_active_app(text):
    # Step 1: Capture the current clipboard content
    try:
        old_clip = subprocess.check_output(['pbpaste'])
    except subprocess.CalledProcessError:
        old_clip = b''

    # Step 2: Copy the new text
    try:
        copy_proc = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
        copy_proc.communicate(input=text.encode('utf-8'))

        # Wait a bit for the system to register new clipboard content
        time.sleep(0.3)

        # Step 3: Paste via Cmd+V
        os.system('osascript -e \'tell application "System Events" to keystroke "v" using {command down}\'')

        # Optional: wait for paste action to complete on slow systems
        time.sleep(0.2)

    finally:
        # Step 4: Restore old clipboard content
        restore_proc = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
        restore_proc.communicate(input=old_clip)

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
        cleanup_lock_file()
        os._exit(0)

    signal.signal(signal.SIGINT, signal_exit_handler)
    signal.signal(signal.SIGTERM, signal_exit_handler)
    
    args = parse_arguments()
    model_size = args.model

    # Load the Whisper model
    logging.info(f"Loading Whisper model '{model_size}'...")
    model = whisper.load_model(model_size)

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt: Exiting...")
        cleanup_lock_file()
        if stream is not None:
            stream.stop()
            stream.close()
        os._exit(0)
