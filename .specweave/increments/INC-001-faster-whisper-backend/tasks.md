---
id: INC-001
title: Faster-Whisper Backend Abstraction
---

# Tasks

- [x] **T1** Create `src/whisper_backend.py` with `load_model()` and `transcribe()` [AC-1, AC-2, AC-3, AC-6]
- [x] **T2** Update `src/dictate.py` to use `whisper_backend` instead of direct whisper import [AC-4]
- [x] **T3** Update `src/transcription.py` to use `whisper_backend.transcribe()` [AC-4]
- [x] **T4** Install `faster-whisper` in venv [AC-6]
- [x] **T5** Add `WHISPER_BACKEND=faster-whisper` to `.env.local` [AC-2]
- [x] **T6** Smoke test: transcribe with faster-whisper, verify paste + auto-enter [AC-5] — TESTED, works but no speed gain
- [x] **T7** Smoke test: switch to openai-whisper via env var, verify still works [AC-2, AC-5] — verified
- [x] **T8** Compare transcription times in `~/.dictate.log` for both backends [AC-6] — no improvement on Apple Silicon CPU

## Outcome: ABANDONED
faster-whisper showed no transcription speed improvement over openai-whisper on Apple Silicon (M-series) CPU. The "4x faster" claims apply to CUDA/GPU setups. All changes reverted, back to openai-whisper + small model.
