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


# Command-line argument parsing
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

# Global variables
audio_queue = queue.Queue()
result_queue = queue.Queue()
recording = False
transcribing = False
stream = None

log_file = Path.home() / '.dictate.log'
logging.basicConfig(
    filename=str(log_file),
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

LOCK_FILE = "/tmp/dictate.lock"

def setup_lock_file():
    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, "r") as f:
            old_pid = int(f.read().strip())
            if psutil.pid_exists(old_pid):
                print(f"Another instance is already running with PID {old_pid}. Exiting.")
                sys.exit(0)
    
    # Create the lock file
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

def cleanup_lock_file():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
        print("Lock file removed.")

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

# Function to toggle recording
def toggle_recording():
    global recording, transcribing, stream
    if not recording and not transcribing:
        # (Re)Initialize the input stream with the currently selected device
        if stream is not None:
            # If a stream is already open, close it before reopening
            stream.stop()
            stream.close()

        # Determine the input device
        device_index = select_input_device(args.device)
        device_name = sd.query_devices(device_index)['name']
        logging.info(f"Using input device: {device_name}")

        stream = sd.InputStream(callback=audio_callback, channels=1, samplerate=16000, device=device_index)
        stream.start()

        logging.info("Recording started...")
        recording = True
        show_notification("Dictation", "Recording started")
    elif recording:
        logging.info("Recording stopped.")
        recording = False
        show_notification("Dictation", "Recording stopped")
        threading.Thread(target=transcribe_audio).start()
    else:
        logging.info("Transcription in progress, please wait...")

# Function to select input device
def select_input_device(device_arg):
    # If the user specified a device by name or index, try to find it
    if device_arg is not None:
        devices = sd.query_devices()
        # Try to interpret device_arg as an index first
        try:
            idx = int(device_arg)
            if 0 <= idx < len(devices):
                return idx
        except ValueError:
            pass
        # If not an index, try by name
        for i, d in enumerate(devices):
            if device_arg.lower() in d['name'].lower():
                return i
        logging.warning(f"Specified device '{device_arg}' not found. Using default device.")
    
    # If no device specified or not found, use default
    default_input_device = sd.default.device[0]
    if default_input_device is None:
        logging.warning("No default input device found. Attempting to use the first available input.")
        for i, d in enumerate(sd.query_devices()):
            if d['max_input_channels'] > 0:
                logging.info(f"Found available input device: {d['name']} with {d['max_input_channels']} channels.")
                return i
        raise RuntimeError("No available input devices found.")

    logging.info(f"Default input device: {sd.query_devices(default_input_device)['name']}")
    return default_input_device

# Function to show macOS notification
def show_notification(title, message):
    os.system(f'''osascript -e 'display notification "{message}" with title "{title}"' ''')

# Audio callback function
def audio_callback(indata, frames, time_info, status):
    if recording:
        audio_queue.put(indata.copy())


# Transcription function
def transcribe_audio():
    global transcribing
    transcribing = True
    audio_data = []
    while not audio_queue.empty():
        audio_data.append(audio_queue.get())
    if audio_data:
        audio = np.concatenate(audio_data, axis=0).flatten()
        # Normalize audio
        if np.max(np.abs(audio)) != 0:
            audio = audio / np.max(np.abs(audio))
        else:
            logging.info("No audio data to transcribe.")
            transcribing = False
            return
        logging.info("Transcribing...")
        result = model.transcribe(audio, fp16=False)
        text = result['text'].strip()

        # Clean up punctuation and whitespace
        text = cleanup_text(text)

        result_queue.put(text)
    transcribing = False
    # Send text to active application
    while not result_queue.empty():
        text = result_queue.get()
        logging.info("Transcribed Text: %s", text)
        send_text_to_active_app(text)


# Text cleanup function
def cleanup_text(text):
    # Ensure single spaces after periods, commas, and question marks
    text = re.sub(r'\s*([.,?!])\s*', r'\1 ', text)

    # Remove unnecessary commas or periods before a newline
    text = re.sub(r'[.,]\s*\n', r'\n', text)

    # Standardize multiple newlines into exactly two
    text = re.sub(r'\n+', '\n\n', text)

    # Remove extra spaces at the start or end of each line
    text = "\n".join(line.strip() for line in text.splitlines())

    # Ensure the text ends with a single newline
    text = text.strip() + "\n"

    return text

# Function to send text to active application
import subprocess

def send_text_to_active_app(text):
    # Step 1: Capture the current clipboard content
    try:
        old_clip = subprocess.check_output(['pbpaste'])
    except subprocess.CalledProcessError:
        old_clip = b''

    # Step 2: Put the transcription text into the clipboard
    process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
    process.communicate(input=text.encode('utf-8'))

    # Step 3: Wait briefly to ensure the clipboard is updated
    time.sleep(0.1)  # Add a short delay to ensure clipboard updates

    # Step 4: Simulate Command+V to paste the transcribed text
    os.system('osascript -e \'tell application "System Events" to keystroke "v" using {command down}\'')

    # Step 5: Restore the old clipboard content
    process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
    process.communicate(input=old_clip)

# Event tap callback function
def tap_callback(proxy, type_, event, refcon):
    keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
    flags = Quartz.CGEventGetFlags(event)
    
    # F1 key to toggle recording
    if keycode == 122:
        logging.info("F1 key detected.")
        toggle_recording()
        return None  # Suppress the event
    
    # Option+Shift+D to quit
    if type_ == Quartz.kCGEventKeyDown and keycode == 2:  # 'D' key
        shift_pressed = (flags & Quartz.kCGEventFlagMaskShift) == Quartz.kCGEventFlagMaskShift
        option_pressed = (flags & Quartz.kCGEventFlagMaskAlternate) == Quartz.kCGEventFlagMaskAlternate
        
        if shift_pressed and option_pressed:
            logging.info("Option+Shift+D detected. Exiting.")
            cleanup_lock_file()  # Remove the lock file
            os._exit(0)  # Immediately terminate the process
    
    return event

# Run the event tap in a separate thread
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
        logging.error("Failed to create event tap. Please ensure the script has Accessibility permissions.")
        logging.error("Ensure the app is listed in System Settings > Privacy & Security > Accessibility.")
        logging.error("Additionally, verify the app is running outside of a restricted environment.")
        sys.exit(1)
    run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetCurrent(), run_loop_source, Quartz.kCFRunLoopCommonModes)
    Quartz.CGEventTapEnable(tap, True)
    logging.info("Event tap started successfully.")
    Quartz.CFRunLoopRun()

# Test microphone input to trigger macOS permissions prompt
def test_microphone_access():
    try:
        sd.check_input_settings()
        logging.info("Microphone access test passed.")
    except Exception as e:
        logging.error(f"Microphone access test failed: {e}")

# Main execution
if __name__ == "__main__":
    # Start the event tap thread with logging
    logging.info("Starting event tap thread.")
    threading.Thread(target=run_event_tap, daemon=True).start()
    
    # Kill any stale processes first
    kill_old_processes()
    
    os.system('osascript -e \'tell application "System Events" to get the name of every process\'')
    
    # Test microphone access early to trigger permissions prompt if needed
    test_microphone_access()
    
    # Setup lock file and register cleanup handlers
    setup_lock_file()
    atexit.register(cleanup_lock_file)

    def signal_exit_handler(signum, frame):
        cleanup_lock_file()  # Explicitly call cleanup before exiting
        os._exit(0)  # Use os._exit instead of sys.exit

    # Handle manual termination (Ctrl+C or kill commands)
    signal.signal(signal.SIGINT, signal_exit_handler)
    signal.signal(signal.SIGTERM, signal_exit_handler)
    
    args = parse_arguments()
    model_size = args.model

    # Load the Whisper model
    logging.info(f"Loading Whisper model '{model_size}'...")
    model = whisper.load_model(model_size)

    

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Exiting...")
        cleanup_lock_file()
        if stream is not None:
            stream.stop()
            stream.close()
        os._exit(0)  # Use os._exit instead of sys.exit