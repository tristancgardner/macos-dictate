# macos-dictate Reliability Log

## 2026-02-12
- Commented out the early audio verification check (verify_audio_capture) that runs 1s after recording starts. It was triggering false-positive recovery restarts and likely causing inconsistency rather than helping. Watchdog/heartbeat/restart_audio_stream left intact.
- Current reliability: works ~7 hours continuously before a random error requires app restart.
- Big win from ~2 weeks ago: fixed the long-standing issue (1+ year) where changing the audio input mic required restarting the app. The watchdog + device monitoring now handles hot-swapping mics seamlessly -- no problems since.
