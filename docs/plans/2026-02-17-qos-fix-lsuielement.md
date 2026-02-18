# Fix .app Bundle QoS Slowdown Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate the 5-8x transcription slowdown in the .app bundle caused by `LSUIElement: True` clamping all threads to E-cores.

**Architecture:** Remove `LSUIElement: True` from the plist so the app launches as a foreground app with P-core QoS, then immediately call `NSApp.setActivationPolicy_(1)` in Python to hide the Dock icon. Delete the now-unnecessary `qos_fix.py` module and all references to it.

**Tech Stack:** py2app, AppKit (PyObjC), macOS QoS scheduling

**IMPERATIVE: Do NOT rebuild the .app (`rebuild.sh`) until the user explicitly says to. All code changes are live in alias mode except plist changes -- the rebuild is the user's call.**

---

### Task 1: Remove LSUIElement and LSEnvironment from setup.py

**Files:**
- Modify: `build-assets/setup.py:29` (LSUIElement), `build-assets/setup.py:33-37` (LSEnvironment)

**Step 1: Remove `LSUIElement: True` line**

Delete line 29 from `build-assets/setup.py`:
```python
'LSUIElement': True,  # No dock icon
```

**Step 2: Remove the `LSEnvironment` block**

Delete lines 33-37 from `build-assets/setup.py`:
```python
'LSEnvironment': {
    'OMP_NUM_THREADS': '8',
    'MKL_NUM_THREADS': '8',
    'VECLIB_MAXIMUM_THREADS': '8',
},
```

**Step 3: Remove `qos_fix` from includes list**

Delete line 57 from `build-assets/setup.py`:
```python
'qos_fix',
```

**Step 4: Commit**

```bash
git add build-assets/setup.py
git commit -m "fix: remove LSUIElement, LSEnvironment, qos_fix from plist config"
```

---

### Task 2: Add Dock-hiding to dictate.py and remove qos_fix references

**Files:**
- Modify: `src/dictate.py:15-16` (qos_fix import + call), `src/dictate.py:247` (qos_diagnose call), `src/dictate.py:237+` (__main__ block)

**Step 1: Remove the qos_fix import and call at top of file**

Delete lines 15-16 from `src/dictate.py`:
```python
from qos_fix import force_performance_qos, diagnose as qos_diagnose
force_performance_qos()
```

**Step 2: Remove the `qos_diagnose()` call in __main__**

Delete line 247 from `src/dictate.py`:
```python
qos_diagnose()
```

Also remove any blank line left behind to keep formatting clean.

**Step 3: Add Dock-hiding early in __main__, before model load**

Insert these lines early in the `if __name__ == "__main__":` block (after logging setup, before `kill_old_processes()`). The `AppKit` import already exists at line 18, so just add:

```python
# Launch as foreground app (P-core QoS), then immediately hide Dock icon
NSApp = AppKit.NSApplication.sharedApplication()
NSApp.setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory
```

**Step 4: Commit**

```bash
git add src/dictate.py
git commit -m "fix: remove qos_fix usage, add Dock-hiding via setActivationPolicy"
```

---

### Task 3: Remove qos_fix reference from transcription.py

**Files:**
- Modify: `src/transcription.py:130-132` (inside `transcribe_with_timeout()`)

**Step 1: Remove the local qos_fix import and call**

Delete lines 130-132 from `src/transcription.py` (inside the `transcribe_with_timeout` nested function):
```python
# Force P-core QoS on this thread -- daemon threads may inherit background QoS
from qos_fix import force_performance_qos
force_performance_qos()
```

The function body should then just be:
```python
def transcribe_with_timeout():
    try:
        result_container["result"] = model.transcribe(audio, fp16=False)
        result_container["success"] = True
    except Exception as e:
```

**Step 2: Commit**

```bash
git add src/transcription.py
git commit -m "fix: remove qos_fix import from transcription thread"
```

---

### Task 4: Delete qos_fix.py

**Files:**
- Delete: `src/qos_fix.py`

**Step 1: Delete the file**

```bash
rm src/qos_fix.py
```

**Step 2: Commit**

```bash
git add src/qos_fix.py
git commit -m "chore: delete qos_fix.py (no longer needed)"
```

---

### Task 5: Verify rebuild.sh is clean

**Files:**
- Read: `build-assets/rebuild.sh`

**Step 1: Inspect rebuild.sh for any qos_fix or shell launcher references**

The file is already clean -- no references to `qos_fix`, `LSUIElement`, or shell launchers. No changes needed.

**Step 2: Run the app directly from Python to test code changes**

Since code changes are live in alias mode (except plist), test by running Python directly:

```bash
cd /Users/tristangardner/Documents/Programming/01_Apps/macos-dictate
.pyenv-venv/bin/python src/dictate.py
```

Verify:
- App launches without import errors
- No `qos_fix` module-not-found errors in logs
- Dock icon behavior (may still show since running via Python, not .app)

---

### Task 6: Rebuild and verify (USER-TRIGGERED ONLY)

**DO NOT START THIS TASK. Wait for user to explicitly request the rebuild.**

**Step 1: Rebuild the .app**

```bash
./build-assets/rebuild.sh
```

**Step 2: Re-add TCC permissions**

Add `Dictate.app` in both System Settings pages that open (Accessibility + Input Monitoring).

**Step 3: Launch and check QoS**

```bash
open dist/Dictate.app
```

Wait for it to start, then check thread priorities:

```bash
ps -M -p $(pgrep -f "Dictate") | head -20
```

Expected: PRI values of 26-31T (P-core scheduling), NOT 4T (E-core/background).

**Step 4: Test transcription speed**

- Press F1, speak ~9 words, press F1
- Transcription should complete in 1-2 seconds (not 5-10s)

**Step 5: Verify Dock icon is hidden**

- Dock should NOT show a Dictate icon (or it flashes briefly then disappears)

**Step 6: Fallback if QoS drops after setActivationPolicy**

If `ps -M` shows PRI 4T after adding `setActivationPolicy_(1)`:
- Remove the `setActivationPolicy_(1)` call
- Accept the Dock icon as a tradeoff for P-core performance
- Rebuild and re-test

**Step 7: Final commit**

```bash
git add -A
git commit -m "verified: .app runs on P-cores with Dock hidden"
```
