---
id: INC-001
title: Faster-Whisper Backend Abstraction
---

# Implementation Plan

## Architecture Decision
Single new module `src/whisper_backend.py` acts as a facade. It reads `WHISPER_BACKEND` from env, imports the correct library, and normalizes the API surface. Only 3 existing lines change across 2 files.

## Steps

### 1. Create `src/whisper_backend.py`
- Read `WHISPER_BACKEND` env var (default: `faster-whisper`)
- `faster-whisper` path: `WhisperModel(size, device="cpu", compute_type="int8")`, transcribe returns segments generator — collect into `{"text": joined_text}`
- `openai-whisper` path: pass-through to existing `whisper.load_model()` and `model.transcribe(audio, fp16=False)`
- Auto-fallback: if `faster-whisper` is set but not installed, fall back to `openai-whisper` with a log warning

### 2. Update `src/dictate.py`
- Replace `import whisper` with `import whisper_backend`
- Replace `whisper.load_model(model_size)` with `whisper_backend.load_model(model_size)`

### 3. Update `src/transcription.py`
- Replace `model.transcribe(audio, fp16=False)` with `whisper_backend.transcribe(model, audio)`

### 4. Install faster-whisper
- `pip install faster-whisper` into the venv
- Add to requirements if one exists

### 5. Configure `.env.local`
- Add `WHISPER_BACKEND=faster-whisper`

### 6. Manual smoke test
- Record and transcribe with faster-whisper backend
- Switch env var to `openai-whisper`, verify still works
- Compare transcription speed in `~/.dictate.log`

## Risk
- Low: CTranslate2 wheels exist for macOS ARM64
- Low: API surface is tiny (2 functions), rollback is trivial
