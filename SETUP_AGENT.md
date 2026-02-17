# macos-dictate — Agent Setup Guide

This document gives any AI coding assistant (Claude Code, Cursor, Copilot, etc.) the context it needs to work on this project effectively.

## Python Environment

Requires Python 3.10+ with a venv containing PyObjC (Quartz). Create it:

```bash
python3 -m venv venv
source venv/bin/activate
pip install torch sounddevice numpy pyobjc psutil
pip install git+https://github.com/openai/whisper.git
pip install py2app  # only needed for .app builds
```

Run the app with:

```bash
./venv/bin/python dictate.py --model small
```

## Project Structure

| File | Purpose |
|---|---|
| `dictate.py` | Main app (~1150 lines). All recording, transcription, keyboard shortcuts, watchdog, and threading logic. |
| `text_postprocessor.py` | Text cleanup pipeline: custom word corrections (`WORD_MAPPINGS`), smart quoting (`QUOTE_TRIGGERS`, `GREEDY_QUOTE_TRIGGERS`), punctuation normalization. |
| `device_monitor.py` | CoreAudio device change detection via ctypes. Handles hot-swap microphone switching with CFRunLoop listener + polling fallback. |
| `setup.py` | py2app config for building `Dictate.app`. Plist settings, icon, package list. |
| `rebuild.sh` | Full rebuild + codesign + TCC permission reset script. Run after `setup.py` changes. |
| `entitlements.plist` | Code signing entitlements (microphone, unsigned-memory, disable-lib-validation). |
| `.env.local` | User-specific config (file paths for append shortcuts). Copy from `.env.example`. Gitignored. |
| `.env.example` | Template for `.env.local`. |

## Key Variables

- `append_target` — global in `dictate.py`. When set to a file path, the next transcription appends as a markdown bullet (`- text`) to that file instead of pasting. Reset to `None` after each transcription.
- `APPEND_BULLET_FILE` / `APPEND_BULLET_FILE_2` — loaded from `.env.local` at startup. Drive the Cmd+F1 and Alt+F1 shortcuts.
- `OMP_NUM_THREADS` / `MKL_NUM_THREADS` — set at the very top of `dictate.py` before any imports. Critical for PyTorch multi-threading in `.app` environments. Without these, Whisper runs on a single CPU core.

## Keyboard Shortcuts

| Key | Action |
|---|---|
| F1 | Start/stop recording, paste transcription |
| F2 | Repaste last transcription |
| Cmd+F1 | Record and append bullet to `APPEND_BULLET_FILE` |
| Alt+F1 | Record and append bullet to `APPEND_BULLET_FILE_2` |
| Cmd+Alt+R | Force restart app |
| Opt+Shift+D | Quit |

## App Packaging (py2app)

- **Alias mode**: `python setup.py py2app -A` — the `.app` symlinks to source files. Code changes are live after quit + relaunch. No rebuild needed.
- **Full rebuild**: Only needed after `setup.py` changes. Use `./rebuild.sh`.
- **TCC permissions**: Every rebuild invalidates macOS TCC grants (Accessibility + Input Monitoring). Must re-add the app in System Settings after each rebuild.
- **Bundle ID**: `com.suorastudios.dictate` (in `setup.py`). Change this if forking.

## Customization Points

- **Word corrections**: `WORD_MAPPINGS` dict in `text_postprocessor.py` — regex pattern → replacement string
- **Quote triggers**: `QUOTE_TRIGGERS` list in `text_postprocessor.py` — trigger phrases that auto-wrap following words in quotes
- **Greedy quote triggers**: `GREEDY_QUOTE_TRIGGERS` in `text_postprocessor.py` — quotes everything to end of utterance
- **Default model**: `default='small'` in `dictate.py` argparse
- **Append file targets**: `APPEND_BULLET_FILE` / `APPEND_BULLET_FILE_2` in `.env.local`

## Critical Rules

- All file opens **must** use `encoding='utf-8'` — the `.app` process defaults to ASCII
- `OMP_NUM_THREADS` must be set **before** `import torch` — placing it after has no effect
- Never call `refresh_sounddevice()` unconditionally in the watchdog poll loop — it reinitializes PortAudio every call and will freeze the app
- Never hardcode personal file paths in `dictate.py` — use `.env.local` environment variables

## Log File

All events log to `~/.dictate.log`. Key entries:
- `Whisper transcription completed in X.XXs` — performance benchmarks
- `CoreAudio: Default input device changed from X to Y` — mic switch detected
- `Restart skipped: recording in progress` — watchdog correctly deferred recovery
