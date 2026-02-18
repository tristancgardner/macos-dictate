"""Process management and notifications."""

import os
import sys
import signal
import logging
import subprocess
import psutil

LOCK_FILE = "/tmp/dictate.lock"


def show_notification(title, message):
    os.system(f'''osascript -e 'display notification "{message}" with title "{title}"' ''')


def setup_lock_file():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                old_pid = int(f.read().strip())
                if psutil.pid_exists(old_pid):
                    try:
                        proc = psutil.Process(old_pid)
                        cmdline = ' '.join(proc.cmdline())
                        if 'dictate.py' in cmdline or 'Dictate.app' in cmdline:
                            logging.info(f"Killing stale instance with PID {old_pid}")
                            os.kill(old_pid, signal.SIGKILL)
                            import time
                            time.sleep(0.3)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
        except (ValueError, IOError):
            pass

    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def cleanup_lock_file():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
        print("Lock file removed.")


def kill_old_processes():
    try:
        result = subprocess.check_output(["pgrep", "-f", "dictate.py|Dictate.app"]).decode().splitlines()
        current_pid = os.getpid()
        killed_any = False
        for pid in result:
            if int(pid) != current_pid:
                logging.info(f"Killing old process with PID {pid}")
                try:
                    os.kill(int(pid), signal.SIGKILL)
                    killed_any = True
                except ProcessLookupError:
                    logging.info(f"Process {pid} already dead")
                except PermissionError:
                    logging.warning(f"Permission denied killing process {pid}")
        if killed_any:
            logging.info("Waiting for old processes to terminate...")
    except subprocess.CalledProcessError:
        logging.info("No old processes found to kill.")
