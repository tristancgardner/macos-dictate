"""Audio transcription and text output."""

import logging
import threading
import time
import re
import numpy as np
import traceback
from pathlib import Path
from datetime import datetime

from process import show_notification
from audio import audio_queue, state_lock
from text_postprocessor import cleanup_text, send_text_to_active_app

# Transcription state
transcribing = False
transcribe_start = None
append_target = None  # When set, transcription appends as bullet to this file path

# Set by dictate.py after model load
model = None

# Loaded from .env.local by dictate.py
APPEND_BULLET_FILE = None

LOG_FILE = Path.home() / '.dictate.log'


def append_bullet_to_file(text, file_path=None):
    """Append text as a bullet point to the specified markdown file."""
    target = Path(file_path or APPEND_BULLET_FILE)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)

        needs_newline = False
        if target.exists():
            with open(target, 'rb') as f:
                f.seek(0, 2)
                if f.tell() > 0:
                    f.seek(-1, 2)
                    needs_newline = f.read(1) != b'\n'

        with open(target, 'a') as f:
            if needs_newline:
                f.write('\n')
            f.write(f'- {text}\n')

        logging.info(f"Appended bullet to {target}: '- {text}'")
        safe_text = text.replace("'", "'\\''").replace('"', '\\"')
        show_notification("TODO Added", safe_text)
        return True
    except Exception as e:
        logging.error(f"Failed to append bullet to {target}: {e}")
        show_notification("Dictation Error", "Failed to append to file")
        return False


def repaste_last_transcription():
    """Repaste the last transcription by reading from the log file."""
    try:
        if not LOG_FILE.exists():
            logging.info("No log file found for repaste.")
            show_notification("Dictation", "No previous transcription")
            return

        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()

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


def transcribe_audio():
    global transcribing, append_target, transcribe_start
    transcribe_start_time = datetime.now()
    max_transcribe_time = 60

    logging.info(f"Transcription started at {transcribe_start_time}")

    try:
        audio_data = []
        try:
            while not audio_queue.empty():
                try:
                    item = audio_queue.get(timeout=1.0)
                    audio_data.append(item)
                except Exception:
                    break
        except Exception as e:
            logging.error(f"Error gathering audio data: {e}")

        if not audio_data:
            logging.info("No audio data captured; skipping transcription.")
            show_notification("Dictation", "No audio recorded")
            return

        audio = np.concatenate(audio_data, axis=0).flatten()
        logging.info(f"Captured {len(audio)} samples from queue.")

        max_amp = np.max(np.abs(audio))
        logging.info(f"Max amplitude of audio: {max_amp}")
        if max_amp < 1e-5:
            logging.info("Audio is essentially silent; skipping transcription.")
            show_notification("Dictation", "Audio too quiet, try again")
            return

        audio = audio / max_amp

        logging.info("Beginning Whisper transcription...")

        result_container = {"success": False, "result": None, "error": None}

        def transcribe_with_timeout():
            try:
                result_container["result"] = model.transcribe(audio, fp16=False)
                result_container["success"] = True
            except Exception as e:
                result_container["error"] = str(e)
                logging.error(f"Transcription error: {e}")
                logging.error(traceback.format_exc())

        transcribe_thread = threading.Thread(target=transcribe_with_timeout)
        transcribe_thread.daemon = True
        transcribe_thread.start()

        timeout_reached = False
        while transcribe_thread.is_alive():
            elapsed = (datetime.now() - transcribe_start_time).total_seconds()
            if elapsed > max_transcribe_time:
                timeout_reached = True
                logging.warning(f"Transcription timed out after {elapsed:.1f} seconds")
                show_notification("Dictation", "Transcription is taking too long, try again")
                break
            time.sleep(0.5)

        if timeout_reached:
            return

        if not result_container["success"]:
            logging.error(f"Transcription failed: {result_container['error']}")
            show_notification("Dictation Error", "Transcription failed")
            return

        result = result_container["result"]
        transcribe_elapsed = (datetime.now() - transcribe_start_time).total_seconds()
        logging.info(f"Whisper transcription completed in {transcribe_elapsed:.2f}s")

        text = result['text'].strip()
        logging.info(f"Raw transcribed text: '{text}'")

        text = cleanup_text(text).strip()
        logging.info(f"Cleaned transcribed text: '{text}'")

        if text:
            if append_target:
                append_bullet_to_file(text, append_target)
            else:
                send_text_to_active_app(text + " ")
        else:
            logging.info("No text to paste (empty transcription).")
            show_notification("Dictation", "No text detected")

    except Exception as e:
        logging.error(f"Error in transcription process: {e}")
        logging.error(traceback.format_exc())
        show_notification("Dictation Error", "Transcription error")

    finally:
        with state_lock:
            transcribing = False
            transcribe_start = None
            append_target = None
