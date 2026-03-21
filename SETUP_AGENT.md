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
./venv/bin/python src/dictate.py --model small
```

## macOS Permissions

The app requires three permissions in **System Settings > Privacy & Security**. Grant these to your terminal app (or `Dictate.app` if running the packaged bundle):

1. **Accessibility** — keyboard event tap for intercepting shortcuts (F1, F2, etc.)
2. **Input Monitoring** — also required for the keyboard event tap
3. **Microphone** — prompted on first launch

Without Accessibility + Input Monitoring, hotkeys won't fire. Without Microphone, no audio is recorded.

## Project Structure

| File | Purpose |
|---|---|
| `src/dictate.py` | Main app (~1150 lines). All recording, transcription, keyboard shortcuts, watchdog, and threading logic. |
| `src/text_postprocessor.py` | Text cleanup pipeline: voice commands (`SIMPLE_MAPPINGS` + `COMPLEX_MAPPINGS`), smart quoting (`QUOTE_TRIGGERS`, `GREEDY_QUOTE_TRIGGERS`), punctuation normalization. Loads personal corrections from `mappings.local.json` into `SIMPLE_MAPPINGS`. |
| `src/keyboard.py` | Keyboard event tap and shortcut handler. Keycodes for F1/F2 and modifier combos defined here. |
| `src/device_monitor.py` | CoreAudio device change detection via ctypes. Handles hot-swap microphone switching with CFRunLoop listener + polling fallback. |
| `build-assets/setup.py` | py2app config for building `Dictate.app`. Plist settings, icon, package list. |
| `build-assets/rebuild.sh` | Full rebuild + codesign + TCC reset script. Run after `setup.py` changes. |
| `build-assets/entitlements.plist` | Code signing entitlements (microphone, unsigned-memory, disable-lib-validation). |
| `build-assets/Dictate.icns` | App icon. |
| `mappings.local.json` | User-specific word correction overrides (regex → replacement). Merged into `WORD_MAPPINGS` at import. Gitignored. |
| `.env.local` | User-specific config (file paths for append shortcuts). Copy from `.env.example`. Gitignored. |
| `.env.example` | Template for `.env.local`. |

## Key Variables

- `append_target` — global in `src/dictate.py`. When set to a file path, the next transcription appends as a markdown bullet (`- text`) to that file instead of pasting. Reset to `None` after each transcription.
- `APPEND_BULLET_FILE` / `APPEND_BULLET_FILE_2` — loaded from `.env.local` at startup. Drive the Cmd+F1 and Alt+F1 shortcuts.
- `OMP_NUM_THREADS` / `MKL_NUM_THREADS` — set at the very top of `src/dictate.py` before any imports. Critical for PyTorch multi-threading in `.app` environments. Without these, Whisper runs on a single CPU core.

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

- **Why `.app`**: macOS Sequoia resets Terminal TCC permissions monthly. The `.app` bundle (`dist/Dictate.app`) gets its own stable TCC identity so permissions persist.
- **Alias mode**: `python build-assets/setup.py py2app -A` — the `.app` symlinks to source files. Code changes in `src/` are live after quit + relaunch. No rebuild needed.
- **Full rebuild**: Only needed after `build-assets/setup.py` changes. Use `./build-assets/rebuild.sh`.
- **TCC permissions**: Every rebuild invalidates macOS TCC grants (Accessibility + Input Monitoring). Must re-add the app in System Settings after each rebuild.
- **Bundle ID**: `com.suorastudios.dictate` (in `build-assets/setup.py`). Change this if forking.

## Customization Points

- **Word corrections**: `src/text_postprocessor.py` has two mapping dicts. `SIMPLE_MAPPINGS` contains direct word swaps (colon, slash, etc.) — these run first. `COMPLEX_MAPPINGS` contains context-sensitive patterns with lookaheads (dot, dotfiles, new line) — these run second and depend on simple corrections being applied first. Users add personal corrections in `mappings.local.json` (copy from `mappings.example.json`), which is merged into `SIMPLE_MAPPINGS` at import time.
- **Quote triggers**: `QUOTE_TRIGGERS` list in `src/text_postprocessor.py` — trigger phrases that auto-wrap following words in quotes
- **Greedy quote triggers**: `GREEDY_QUOTE_TRIGGERS` in `src/text_postprocessor.py` — quotes everything to end of utterance
- **Keyboard shortcuts**: Keycodes in `src/keyboard.py` — F1 (`122`), F2 (`120`), with modifier checks for Cmd/Alt combos
- **Default model**: `default='small'` in `src/dictate.py` argparse
- **Append file targets**: `APPEND_BULLET_FILE` / `APPEND_BULLET_FILE_2` in `.env.local`

## Helping Contributors Customize

When a contributor asks to add or change voice commands, word mappings, or keyboard shortcuts, guide them based on `README.md` — it documents all customization points in detail. Key behaviors:

- If they want to **add personal word corrections** (names, brands, jargon): help them create or edit `mappings.local.json`. Ask what words Whisper gets wrong and what they should map to.
- If they want to **disable a built-in voice command** (e.g. "dot" or "new line" conflicts with how they speak): walk them through removing the entry from `WORD_MAPPINGS` or commenting out the relevant `re.sub` line in `cleanup_text()`.
- If they want to **add a new voice formatting command**: ask them to describe the behavior in natural language (e.g. "when I say 'bullet', start a list item"). Use the existing patterns in `WORD_MAPPINGS` and `cleanup_text()` as reference for implementation.
- If they want to **change keyboard shortcuts**: point them to `src/keyboard.py` and the keycode values.

Don't assume what the contributor wants — ask before making changes to voice commands or text processing behavior.

## Critical Rules

- All file opens **must** use `encoding='utf-8'` — the `.app` process defaults to ASCII
- `OMP_NUM_THREADS` must be set **before** `import torch` — placing it after has no effect
- Never call `refresh_sounddevice()` unconditionally in the watchdog poll loop — it reinitializes PortAudio every call and will freeze the app
- Never hardcode personal file paths in source — use `.env.local` environment variables
- `SIMPLE_MAPPINGS` and `COMPLEX_MAPPINGS` in source should only contain generic voice commands (dot, colon, slash, etc.) — user-specific corrections belong in `mappings.local.json`
- `text_postprocessor.py` uses `<<DOT>>`, `<<COMMA>>`, and `<<NL>>` placeholders internally to protect inline dots, thousand-separator commas, and newlines from the punctuation spacing step — don't use these strings in mappings

## Log File

All events log to `~/.dictate.log`. Key entries:
- `Whisper transcription completed in X.XXs` — performance benchmarks
- `CoreAudio: Default input device changed from X to Y` — mic switch detected
- `Restart skipped: recording in progress` — watchdog correctly deferred recovery
