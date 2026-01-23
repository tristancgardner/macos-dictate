# Thread Safety Debugging Guide

## Problem Summary

Intermittent errors over extended use (~1 issue per hour):
- "no audio recorded" errors
- One process crash
- Premature timeouts

## Root Cause Analysis

6+ concurrent threads accessing shared state with zero synchronization:

| Thread | Accesses |
|--------|----------|
| Event tap | `recording`, `transcribing`, `stream` |
| Audio callback | `recording`, `callback_count`, `last_heartbeat` |
| Watchdog | `recording`, `stream`, `last_heartbeat` |
| Verification | `recording`, `callback_count`, `stream` |
| Transcription | `transcribing`, `audio_queue` |
| Device monitor | `stream`, `stream_healthy` |

## Changes Made (2026-01-23)

### 1. Added Lock Primitives (line 65-67)

```python
state_lock = threading.RLock()   # Protects: recording, transcribing, stream_healthy, last_heartbeat, callback_count
stream_lock = threading.Lock()    # Protects: stream object, restart operations
restart_in_progress = False       # Prevents concurrent restarts
```

### 2. Fixed `restart_audio_stream()`
- Non-blocking `stream_lock.acquire()` to skip if restart already running
- Checks `transcribing` flag BEFORE clearing queue (prevents data loss)
- `restart_in_progress` flag with cleanup in `finally`

### 3. Fixed `verify_audio_capture()`
- Timeout increased: 500ms -> 750ms
- Added minimum callback threshold (5 callbacks)
- State reads under `state_lock`

### 4. Fixed `watchdog_monitor()`
- Copies state under `state_lock` at iteration start
- Uses copied values (avoids TOCTOU)
- Safe stream access with `stream_lock`

### 5. Fixed `toggle_recording()`
- State checks under `state_lock`
- Stream operations under `stream_lock`

### 6. Fixed `transcribe_audio()`
- `transcribing` flag set/cleared under `state_lock`
- Consolidated flag clearing in `finally` block

### 7. Fixed `apply_device_change()`
- State checks under `state_lock`
- Stream operations under `stream_lock`

### 8. Kept `audio_callback()` Lock-Free
- Must remain lightweight (no blocking)
- Benign race on `recording` read acceptable

---

## If Issues Persist

### Step 1: Check Logs for New Patterns

```bash
tail -100 ~/.dictate.log | grep -E "(skipped|FAILED|error|WARNING)"
```

Look for:
- `"restart skipped: another restart in progress"` - lock working
- `"restart skipped: transcription in progress"` - queue protection working
- Any new error patterns

### Step 2: Increase Verification Timeout

If still getting false-positive "audio not flowing" on busy systems:

```python
# In verify_audio_capture() - try 1000ms
time.sleep(1.0)  # Was 0.75
min_expected_callbacks = 8  # Was 5
```

### Step 3: Add Deadlock Detection

If app freezes completely, add timeout to lock acquisitions:

```python
# In toggle_recording(), replace:
with stream_lock:

# With:
if not stream_lock.acquire(timeout=5.0):
    logging.error("DEADLOCK: stream_lock acquisition timeout in toggle_recording")
    return
try:
    # ... existing code ...
finally:
    stream_lock.release()
```

### Step 4: Add More Granular Logging

Temporarily add lock acquisition logging:

```python
# At top of restart_audio_stream():
logging.info(f"restart_audio_stream called from thread: {threading.current_thread().name}")

# After acquiring stream_lock:
logging.info("stream_lock acquired")
```

### Step 5: Check for Queue Corruption

If "no audio recorded" persists, the queue might still have issues:

```python
# In transcribe_audio(), after gathering audio_data:
logging.info(f"Queue state: empty={audio_queue.empty()}, approx_size={audio_queue.qsize()}")
logging.info(f"Audio data chunks: {len(audio_data)}, total_samples={sum(len(chunk) for chunk in audio_data) if audio_data else 0}")
```

### Step 6: Consider Thread-Safe Queue Alternative

If queue issues persist, consider using `collections.deque` with explicit locking or a bounded queue:

```python
from collections import deque
audio_buffer = deque(maxlen=1000)  # Auto-drops old data if full
audio_buffer_lock = threading.Lock()
```

---

## Potential Remaining Issues

### 1. GIL Limitations
Python's GIL doesn't guarantee atomic operations for complex objects. If issues persist with datetime comparisons, consider using `time.monotonic()` instead:

```python
last_heartbeat_monotonic = time.monotonic()

def update_heartbeat():
    global last_heartbeat_monotonic
    last_heartbeat_monotonic = time.monotonic()
```

### 2. CoreAudio Callback Thread
The `audio_callback` runs on CoreAudio's thread, not a Python thread. Excessive work in the callback can cause buffer underruns. Current implementation is minimal but monitor for:
- `Audio callback status:` warnings in logs
- Crackling/glitchy audio

### 3. Device Change During Recording
Current implementation ignores device changes during recording. If user unplugs mic mid-recording, stream may become invalid. Consider:
- Forcing stop recording on device change
- Adding stream validity checks in audio_callback

### 4. Memory Pressure
Long recordings with slow transcription could fill the queue. Monitor:
```bash
# Check queue size growth in logs
grep "queue_size" ~/.dictate.log
```

---

## Testing Checklist

1. [ ] Run for 1+ hour continuous
2. [ ] Rapid F1 toggling (10x in 5 seconds)
3. [ ] Toggle during high CPU load
4. [ ] Unplug/replug microphone while idle
5. [ ] Unplug/replug microphone while recording
6. [ ] Very short recordings (<1 second)
7. [ ] Very long recordings (>30 seconds)
8. [ ] Silent recordings (no speech)

---

## Quick Reference: Log File

```bash
# View recent logs
tail -f ~/.dictate.log

# Search for errors
grep -i error ~/.dictate.log | tail -20

# Search for thread safety messages
grep -E "(skipped|lock|restart)" ~/.dictate.log | tail -20
```
