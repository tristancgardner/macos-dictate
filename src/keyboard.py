"""Keyboard event tap for global hotkeys."""

import os
import sys
import logging
import threading
import subprocess
import time
from datetime import datetime

import Quartz

from process import show_notification, cleanup_lock_file

# Event tap status - signals main thread if event tap fails
event_tap_ready = threading.Event()
event_tap_failed = threading.Event()

# Event tap heartbeat - updated on every callback, monitored by watchdog
tap_heartbeat = datetime.now()
tap_heartbeat_lock = threading.Lock()

# Set by dictate.py after env loading
APPEND_BULLET_FILE = None
APPEND_BULLET_FILE_2 = None

# Callback references set by dictate.py
_toggle_recording = None
_repaste_last_transcription = None
_get_append_target = None
_set_append_target = None
_set_auto_enter = None


def _dispatch(fn, *args):
    """Run a function on a background thread so the event tap callback returns immediately."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def tap_callback(proxy, type_, event, refcon):
    global tap_heartbeat

    keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
    flags = Quartz.CGEventGetFlags(event)

    # Update heartbeat on every key event so watchdog knows the tap is alive
    with tap_heartbeat_lock:
        tap_heartbeat = datetime.now()

    # Cmd+F1 => Append to APPEND_BULLET_FILE (from .env.local)
    # Alt+F1 => Append to bizdev TODO
    # Plain F1 => Toggle recording (also stops append-mode recording)
    if keycode == 122:  # F1
        cmd_pressed = (flags & Quartz.kCGEventFlagMaskCommand) == Quartz.kCGEventFlagMaskCommand
        alt_pressed = (flags & Quartz.kCGEventFlagMaskAlternate) == Quartz.kCGEventFlagMaskAlternate
        shift_pressed = (flags & Quartz.kCGEventFlagMaskShift) == Quartz.kCGEventFlagMaskShift
        if cmd_pressed and APPEND_BULLET_FILE:
            _set_append_target(APPEND_BULLET_FILE)
            logging.info("Cmd+F1 detected: append-to-file mode activated.")
            _dispatch(_toggle_recording)
        elif alt_pressed and APPEND_BULLET_FILE_2:
            _set_append_target(APPEND_BULLET_FILE_2)
            logging.info("Alt+F1 detected: append to secondary TODO file.")
            _dispatch(_toggle_recording)
        elif shift_pressed:
            _set_auto_enter(True)
            logging.info("Shift+F1 detected: auto-enter mode activated.")
            _dispatch(_toggle_recording)
        else:
            logging.info("F1 key detected.")
            _dispatch(_toggle_recording)
        return None

    # F2 key => Repaste last transcription
    if keycode == 120:  # F2
        logging.info("F2 key detected.")
        _dispatch(_repaste_last_transcription)
        return None

    # Option+Shift+D => Quit (runs inline — fast, no risk of blocking)
    if type_ == Quartz.kCGEventKeyDown and keycode == 2:  # 'D'
        shift_pressed = (flags & Quartz.kCGEventFlagMaskShift) == Quartz.kCGEventFlagMaskShift
        option_pressed = (flags & Quartz.kCGEventFlagMaskAlternate) == Quartz.kCGEventFlagMaskAlternate

        if shift_pressed and option_pressed:
            logging.info("Option+Shift+D detected. Exiting.")
            cleanup_lock_file()
            os._exit(0)

    # Cmd+Alt+R => Force restart (runs inline — must complete before exit)
    if type_ == Quartz.kCGEventKeyDown and keycode == 15:  # 'R'
        cmd_pressed = (flags & Quartz.kCGEventFlagMaskCommand) == Quartz.kCGEventFlagMaskCommand
        alt_pressed = (flags & Quartz.kCGEventFlagMaskAlternate) == Quartz.kCGEventFlagMaskAlternate

        if cmd_pressed and alt_pressed:
            logging.info("Cmd+Alt+R detected. Force restarting app...")
            show_notification("Dictation", "Restarting Dictation App...")
            try:
                current_path = os.path.abspath(sys.executable)
                if '.app/Contents/' in current_path:
                    bundle_path = current_path.split('.app/Contents/')[0] + '.app'
                    logging.info(f"Relaunching .app bundle: {bundle_path}")
                    subprocess.Popen(['open', '-n', bundle_path],
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                else:
                    script_path = os.path.abspath(sys.modules['__main__'].__file__)
                    logging.info(f"Relaunching Python script: {script_path}")
                    subprocess.Popen([sys.executable, script_path],
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)

                time.sleep(0.5)
            except Exception as e:
                logging.error(f"Failed to relaunch: {e}")

            cleanup_lock_file()
            os._exit(0)

    return event


def run_event_tap():
    event_mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault,
        event_mask,
        tap_callback,
        None
    )
    if not tap:
        logging.error("Failed to create event tap. Check Accessibility permissions.")
        event_tap_failed.set()
        return

    run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(
        Quartz.CFRunLoopGetCurrent(),
        run_loop_source,
        Quartz.kCFRunLoopCommonModes
    )
    Quartz.CGEventTapEnable(tap, True)
    logging.info("Event tap started successfully.")
    event_tap_ready.set()
    Quartz.CFRunLoopRun()
