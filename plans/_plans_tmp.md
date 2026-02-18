# Fix .app bundle 5-8x transcription slowdown on Apple Silicon

## Root cause
`LSUIElement: True` in Info.plist tells macOS this is an "agent" app. launchd assigns a permanent background QoS clamp (PRI 4T) to all agent apps, locking every thread to E-cores (~1050 MHz vs P-cores ~4512 MHz). This clamp cannot be overridden from within the process -- setpriority, pthread QoS, taskpolicy, NSProcessInfo activity assertions all fail. This is not a py2app bug; any .app with LSUIElement gets clamped.

## The fix
1. Remove `LSUIElement: True` from plist -- app launches as normal foreground app with P-core QoS
2. Immediately hide Dock icon in Python code via `NSApp.setActivationPolicy_(1)` (Accessory mode)

## Changes

### `build-assets/setup.py`
- Remove `'LSUIElement': True` from plist dict
- Remove `'LSEnvironment'` block (env vars in dictate.py are sufficient without QoS clamp)
- Remove `'qos_fix'` from includes list

### `src/dictate.py`
- Remove `qos_fix` import and `force_performance_qos()` call at top
- Remove `qos_diagnose()` call in main
- In `__main__` block, early (before model load), add Dock-hiding:
  `NSApp = AppKit.NSApplication.sharedApplication()`
  `NSApp.setActivationPolicy_(1)`

### `src/transcription.py`
- Remove the `from qos_fix import force_performance_qos` and `force_performance_qos()` call inside `transcribe_with_timeout()`

### `src/qos_fix.py`
- Delete entirely

### `build-assets/rebuild.sh`
- Verify it's clean (no shell launcher remnants)

## Risk & fallback
If macOS re-evaluates QoS when activation policy changes to Accessory, we lose P-cores. Test incrementally:
1. Build without LSUIElement, NO setActivationPolicy -- confirm PRI 26-31T via `ps -M`
2. Add setActivationPolicy_(1) -- confirm PRI still 26-31T
3. If step 2 fails: keep the Dock icon (remove LSUIElement but skip setActivationPolicy)

## Verification
- Rebuild .app, re-add TCC permissions, launch
- `ps -M -p <pid>` -- PRI 26-31T (not 4T)
- F1 record, speak, F1 stop -- transcription in 1-2s
- Dock icon hidden (or briefly flashes then disappears)
