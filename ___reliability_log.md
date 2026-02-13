# macos-dictate Reliability Log

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
