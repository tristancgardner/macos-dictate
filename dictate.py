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
    return parser.parse_args()

# Global variables
audio_queue = queue.Queue()
result_queue = queue.Queue()
recording = False
transcribing = False

# Function to toggle recording
def toggle_recording():
    global recording, transcribing
    if not recording and not transcribing:
        print("Recording started...")
        recording = True
        show_notification("Dictation", "Recording started")
    elif recording:
        print("Recording stopped.")
        recording = False
        show_notification("Dictation", "Recording stopped")
        threading.Thread(target=transcribe_audio).start()
    else:
        print("Transcription in progress, please wait...")

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
            print("No audio data to transcribe.")
            transcribing = False
            return
        # Transcribe with Whisper
        print("Transcribing...")
        result = model.transcribe(audio, fp16=False)
        text = result['text']
        result_queue.put(text)
    transcribing = False
    # Send text to active application
    while not result_queue.empty():
        text = result_queue.get()
        print("Transcribed Text:", text)
        send_text_to_active_app(text)

# Function to send text to active application
def send_text_to_active_app(text):
    # Set clipboard content safely
    process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
    process.communicate(input=text.encode('utf-8'))
    # Simulate Command+V to paste
    os.system('osascript -e \'tell application "System Events" to keystroke "v" using {command down}\'')

# Event tap callback function
def tap_callback(proxy, type_, event, refcon):
    keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
    # F1 keycode is 122
    if keycode == 122:
        toggle_recording()
        return None  # Suppress the event to prevent system beep
    else:
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
        print("Failed to create event tap. Please ensure the script has accessibility permissions.")
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
    print(f"Loading Whisper model '{model_size}'...")
    model = whisper.load_model(model_size)

    # Set up audio stream
    stream = sd.InputStream(callback=audio_callback, channels=1, samplerate=16000)
    stream.start()

    # Start the event tap thread
    threading.Thread(target=run_event_tap, daemon=True).start()

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting...")
        stream.stop()
        stream.close()
        sys.exit(0)
