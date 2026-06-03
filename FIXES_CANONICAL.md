# macos-dictate — Deferred Fixes

## Notification Show Opens TODO File

**Status:** Deferred

**Context:** Cmd+F1 and Alt+F1 append-mode notifications currently use AppleScript `display notification`. The macOS `Show` button opens the notifying app instead of the associated TODO master file.

**Preserve:** Existing notification titles, messages, and timing. Do not replace the user-facing notification flow while fixing click behavior.

**Likely scope:**
- `src/process.py`
- `src/dictate.py`
- `src/transcription.py`

**Next review:** Confirm the smallest possible callback or app-reopen route that maps the current append target to VS Code without changing normal notification content.
