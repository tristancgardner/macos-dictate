"""Whisper backend abstraction. Switch between openai-whisper and faster-whisper via env var."""

import os
import logging
import numpy as np

BACKEND = os.environ.get("WHISPER_BACKEND", "faster-whisper")

# Auto-fallback: if faster-whisper requested but not installed, use openai-whisper
if BACKEND == "faster-whisper":
    try:
        from faster_whisper import WhisperModel
        logging.info("Using faster-whisper backend (CTranslate2)")
    except ImportError:
        logging.warning("faster-whisper not installed, falling back to openai-whisper")
        BACKEND = "openai-whisper"

if BACKEND == "openai-whisper":
    import whisper
    logging.info("Using openai-whisper backend")


def load_model(model_size):
    logging.info(f"whisper_backend: loading '{model_size}' with backend='{BACKEND}'")
    if BACKEND == "faster-whisper":
        return WhisperModel(model_size, device="cpu", compute_type="int8")
    else:
        return whisper.load_model(model_size)


def transcribe(model, audio):
    if BACKEND == "faster-whisper":
        audio = audio.astype(np.float32)
        segments, info = model.transcribe(audio, beam_size=5)
        text = " ".join(seg.text for seg in segments)
        return {"text": text}
    else:
        return model.transcribe(audio, fp16=False)
