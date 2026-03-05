---
increment: INC-001-faster-whisper-backend
title: "Faster-Whisper Backend Abstraction"
type: feature
status: abandoned
priority: high
created: 2026-03-05
---

# INC-001: Faster-Whisper Backend Abstraction

## Problem
The app uses OpenAI's `whisper` library which is slow on CPU. The `medium` model (best quality for our use) takes ~3.5s per transcription vs `small` at ~1.5s. Users want medium-quality output at small-model speeds.

## Solution
Create a thin backend abstraction (`whisper_backend.py`) that wraps either `openai-whisper` or `faster-whisper` (CTranslate2). Switching between backends is a single env var change — zero code modifications needed.

`faster-whisper` reimplements Whisper using CTranslate2 with int8 quantization, delivering ~4x speedup at equivalent accuracy.

## Acceptance Criteria

- **AC-1**: New `src/whisper_backend.py` module exposes `load_model(size)` and `transcribe(model, audio)` functions
- **AC-2**: Backend selection via `WHISPER_BACKEND` env var in `.env.local` (values: `faster-whisper`, `openai-whisper`)
- **AC-3**: Default backend is `faster-whisper` when the package is installed, falls back to `openai-whisper` otherwise
- **AC-4**: `src/dictate.py` and `src/transcription.py` use the abstraction — no direct whisper imports
- **AC-5**: Existing functionality unchanged — record, transcribe, paste, Shift+F1 auto-enter all work
- **AC-6**: `faster-whisper` uses CPU with int8 compute type for optimized inference

## Out of Scope
- GPU/MPS acceleration
- WhisperX integration
- Model fine-tuning
- Changing the transcription pipeline beyond the backend swap
