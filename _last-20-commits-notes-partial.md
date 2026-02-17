  macos-dictate: Progress Summary                                                                   
                                                                                                    
  Performance                                                     

  - PyTorch single-threading fixed -- The .app bundle was running Whisper on 1 CPU core due to
  missing env vars. Set OMP_NUM_THREADS=8 + MKL_NUM_THREADS=8 to use all M2 Max performance cores.
  Eliminated the 5-7x slowdown vs terminal.
  - Upgraded to small model -- Better transcription accuracy than base with acceptable speed now
  that threading is fixed.
  - Plist App Nap optimizations -- Added NSAppSleepDisabled and NSSupportsAutomaticGraphicsSwitching
   to prevent macOS throttling the .app in the background.

  Reliability

  - Fixed infinite refresh loop -- Watchdog was calling refresh_sounddevice() every 5 seconds,
  reinitializing PortAudio constantly. Fixed to only refresh on actual device changes. This was
  causing freezes and log spam.
  - Fixed race conditions in audio recording -- Multiple fixes for "no audio recorded" errors caused
   by the watchdog clearing the queue in the gap between recording=False and transcribing=True.
  - Fixed watchdog death loop -- Watchdog was crashing and respawning endlessly. Added state
  management safety nets and capped stall recovery retries.
  - Fixed zombie process on app failure -- Cleaned up crash/exit handling to prevent stale processes
   blocking relaunches.

  App Packaging

  - Packaged as Dictate.app via py2app alias mode -- App gets its own TCC identity
  (com.suorastudios.dictate), stable Accessibility/Input Monitoring permissions that don't reset
  monthly.

  Shortcuts & Features

  - Cmd+Alt+R -- Force restart the app when frozen (detects .app vs script context, relaunches
  correctly)
  - Cmd+F1 -- Append transcription as bullet to Somni TODO
  - Alt+F1 -- Append transcription as bullet to bizdev TODO
  - F2 repaste -- Fixed UTF-8 encoding crash in .app environment

  Text Post-Processing

  - Greedy quoting -- Handles "say/to say" trigger phrases for inline quotes
  - Contextual quoting + colon substitution -- Smarter punctuation post-processing
  - Custom corrections -- e.g. "Sora" → "Suora" transcription fixes

  Diagnostics

  - Transcription timing logs -- Added "Whisper transcription completed in X.XXs" to log for
  performance monitoring
  - Transcription start timestamps -- Full timing visibility in .dictate.log