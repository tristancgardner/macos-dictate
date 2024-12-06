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
    # Default input device is sd.default.device[0], which returns the index of the default input
    default_input_device = sd.default.device[0]
    if default_input_device is None:
        # If for some reason there's no default, pick device 0 or any available input
        logging.warning("No default input device found. Attempting to use the first available input.")
        for i, d in enumerate(sd.query_devices()):
            if d['max_input_channels'] > 0:
                return i
        raise RuntimeError("No available input devices found.")
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
        text = result['text'].strip()  # Strip leading/trailing whitespace
        result_queue.put(text)
    transcribing = False
    # Send text to active application
    while not result_queue.empty():
        text = result_queue.get()
        logging.info("Transcribed Text: %s", text)
        send_text_to_active_app(text)

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

    # Step 3: Simulate Command+V to paste the transcribed text
    os.system('osascript -e \'tell application "System Events" to keystroke "v" using {command down}\'')

    # Step 4: Restore the old clipboard content
    process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
    process.communicate(input=old_clip)

# Event tap callback function
def tap_callback(proxy, type_, event, refcon):
    keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
    flags = Quartz.CGEventGetFlags(event)
    
    # F1 keycode is 122
    # Check if F1 is pressed for toggling recording
    if keycode == 122:
        toggle_recording()
        return None  # Suppress the event
    
    # Check for Option+Shift+D
    # 'd' is usually keycode 2
    # Ensure the event is a keydown event before checking modifiers
    if type_ == Quartz.kCGEventKeyDown and keycode == 2:
        # Check if Option and Shift are pressed
        # Note: We use a bitwise AND to ensure these flags are present
        shift_pressed = (flags & Quartz.kCGEventFlagMaskShift) == Quartz.kCGEventFlagMaskShift
        option_pressed = (flags & Quartz.kCGEventFlagMaskAlternate) == Quartz.kCGEventFlagMaskAlternate
        
        if shift_pressed and option_pressed:
            logging.info("Quitting on user request (Option+Shift+D).")
            sys.exit(0)
    
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
        logging.error("Failed to create event tap. Please ensure the script has accessibility permissions.")
        sys.exit(1)
    run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetCurrent(), run_loop_source, Quartz.kCFRunLoopCommonModes)
    Quartz.CGEventTapEnable(tap, True)
    Quartz.CFRunLoopRun()

# Main execution
if __name__ == "__main__":
    args = parse_arguments()
    model_size = args.model

    # Load the Whisper model
    logging.info(f"Loading Whisper model '{model_size}'...")
    model = whisper.load_model(model_size)

    # Don't initialize the stream here permanently. Instead, do it in toggle_recording each time.
    # Just start the event tap and keep main thread alive.
    threading.Thread(target=run_event_tap, daemon=True).start()

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Exiting...")
        if stream is not None:
            stream.stop()
            stream.close()
        sys.exit(0)