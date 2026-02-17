# macos-dictate Reliability Log

## 2026-02-16 -- Fixed infinite refresh loop and added restart shortcut

### Changes
- **CRITICAL FIX**: Fixed infinite `refresh_sounddevice()` loop that was causing app freezes. The watchdog polling fallback was refreshing PortAudio every 5 seconds regardless of whether the device changed. Now it only refreshes AFTER detecting an actual device change.
- Added Cmd+Alt+R keyboard shortcut to force-restart the app when it freezes or becomes unresponsive.
- Added transcription timing logs to track performance and identify slowdowns.

### Root cause of freeze
The polling fallback (lines 522-537) was calling `refresh_sounddevice()` → `sd._terminate()` + `sd._initialize()` every 5 seconds when idle. This constant PortAudio reinitialization was:
1. Causing the app to freeze/become unresponsive
2. Likely causing the perceived slowdown in processing time
3. Spamming the log with "Sounddevice/PortAudio device cache refreshed" messages

### Fix
Moved `refresh_sounddevice()` to only be called AFTER detecting a device name change, not on every poll cycle. The polling now:
1. Checks current device name WITHOUT refreshing
2. Compares to baseline
3. Only refreshes + applies change if names differ

### Performance notes
With the constant refresh loop fixed, transcription performance should return to pre-.app packaging levels. Added timing logs (`transcription completed in X.XXs`) to monitor this going forward.

### Status
- **TESTED & WORKING** - User confirmed fix is working after relaunch. App no longer freezing, Cmd+Alt+R restart shortcut functional.
- Monitoring for: performance improvements, absence of freeze issues, transcription timing logs.
- **UPDATE 2026-02-16 (evening)**: User reported garbled transcriptions. Upgraded default model from `base` to `small` for better accuracy. Expected transcription time increase: 2-5s → 5-10s.

## 2026-02-13 (evening) -- Packaged as .app, new shortcuts

### Changes
- Packaged dictate.py as `Dictate.app` using py2app alias mode. App gets its own TCC identity (`com.suorastudios.dictate`) so Accessibility/Input Monitoring/Microphone permissions are stable and won't reset monthly like Terminal.app's do on macOS Sequoia.
- Added Alt+F1 shortcut to append transcription as bullet to bizdev TODO (`__TODO_MASTER.md`). Refactored `append_mode` boolean to `append_target` path variable so multiple append shortcuts can route to different files.
- Fixed pre-existing bug: F2 repaste failed with `'ascii' codec can't decode byte 0xe6` because `open(LOG_FILE, 'r')` didn't specify `encoding='utf-8'`. The .app process environment defaults to ASCII instead of Terminal's UTF-8.
- Added custom app icon (`Dictate.icns`).
- Created `rebuild.sh` script that handles full rebuild + TCC reset + opens System Settings pages for re-authorization.

### Architecture notes
- Alias mode: the .app bundle symlinks back to source files and venv. Code changes are live with just a quit+relaunch (Option+Shift+D). Only `setup.py` changes require a rebuild.
- Rebuilds (`rm -rf dist`) invalidate macOS TCC permissions because the code signature hash changes. Must remove and re-add the app in Accessibility + Input Monitoring after rebuild.
- `LSUIElement: true` means no dock icon when running, no menu bar. User can drag .app to Dock as a launcher.
- Login Item: added via System Settings > General > Login Items.

### Current shortcut map
- F1: record and paste transcription
- F2: repaste last transcription
- Cmd+F1: record and append as bullet to Somni TODO (from APPEND_BULLET_FILE in .env.local)
- Alt+F1: record and append as bullet to bizdev TODO
- Option+Shift+D: quit

### Status
- All shortcuts tested and working from .app bundle.

## 2026-02-13
- Disabling early audio verification (02-12) didn't help -- may have made things worse. "Audio system recovered" notifications still appearing, "no audio recorded" errors persist.
- Root cause identified: race condition in queue clearing. When recording stops, there's a window where both recording=False and transcribing=False. Watchdog can clear the queue in that gap, destroying all captured audio before transcription drains it. Also, restart_audio_stream() never checked if recording was active before clearing.
- Applied 5 fixes:
  1. Set transcribing=True atomically with recording=False (closes the race window)
  2. Added recording check to restart_audio_stream() (prevents queue clearing mid-recording)
  3. Wrapped heartbeat update in state_lock (prevents false stall detection from stale CPU cache)
  4. Removed "Audio system recovered" notification (silent log only now)
  5. Re-enabled early audio verification as warn-only (no restart trigger)

## Narrative & Next Steps

### What the user reported
- The app has been unreliable for months -- works for ~7 hours then randomly fails with "no audio recorded" errors. The "Audio system recovered" notification keeps popping up, and recovery seems to leave things worse than before.
- The watchdog/device-monitoring system added ~2 weeks ago to handle mic hot-swapping has been a clear win -- zero issues with that since deployment. The reliability problems are separate from device switching.
- The user initially suspected the early audio verification was the culprit (02-12), but disabling it didn't help and may have made things worse. The real problem was deeper: the watchdog's recovery mechanism was destroying queued audio data.

### What we found
A deep analysis of the threading model revealed the core bug: the watchdog's `restart_audio_stream()` function clears the audio queue as part of recovery, but it only checked `transcribing` before doing so -- never `recording`. Combined with a race window where both flags are False between stop-recording and transcription-start, the watchdog had multiple opportunities to silently destroy captured audio. The heartbeat being updated without a lock also meant the watchdog could see stale values and trigger false "stalled" detections, leading to unnecessary restarts that cleared the queue.

### If problems persist, investigate next
1. **audio_callback reading `recording` without lock (line 231)** -- CPython's GIL mostly protects this, but it's technically a memory visibility issue. Could wrap in state_lock if the current fixes aren't enough.
2. **Queue drain race in transcribe_audio (line 834)** -- `while not audio_queue.empty()` can miss items added between the check and the loop exit. A sentinel-based approach (put a special marker in the queue when recording stops, drain until you hit it) would be more robust.
3. **Stream stop/close not fully synchronized with callback** -- sounddevice callbacks can fire after stream.close() returns. If audio_callback puts data after the stream is "closed," it could cause subtle issues.
4. **Device change racing with recording start** -- apply_device_change checks recording/transcribing under lock, but there's a window between releasing the lock and acquiring stream_lock where toggle_recording could start.
5. **Check ~/.dictate.log for patterns** -- look for "Restart skipped: recording in progress" or "Restart skipped: transcription in progress" entries. If these appear frequently, it means the watchdog is firing often but now being safely blocked. That would point to an underlying stream health issue worth investigating separately.

## 2026-02-12
- Commented out the early audio verification check (verify_audio_capture) that runs 1s after recording starts. It was triggering false-positive recovery restarts and likely causing inconsistency rather than helping. Watchdog/heartbeat/restart_audio_stream left intact.
- Current reliability: works ~7 hours continuously before a random error requires app restart.
- Big win from ~2 weeks ago: fixed the long-standing issue (1+ year) where changing the audio input mic required restarting the app. The watchdog + device monitoring now handles hot-swapping mics seamlessly -- no problems since.
