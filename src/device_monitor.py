"""
CoreAudio Device Monitor for macOS

Monitors changes to the default input audio device using CoreAudio's
property listener API via ctypes. Falls back gracefully if CoreAudio
bindings fail.
"""

import ctypes
from ctypes import c_void_p, c_uint32, c_int32, CFUNCTYPE, POINTER, byref, sizeof
import threading
import logging
import sounddevice as sd

# CoreAudio constants
kAudioObjectSystemObject = 1
kAudioHardwarePropertyDefaultInputDevice = 0x64496E20  # 'dIn '
kAudioObjectPropertyScopeGlobal = 0x676C6F62  # 'glob'
kAudioObjectPropertyElementMain = 0

# OSStatus codes
kAudioHardwareNoError = 0

# Type aliases for CoreAudio
AudioObjectID = c_uint32
AudioObjectPropertySelector = c_uint32
AudioObjectPropertyScope = c_uint32
AudioObjectPropertyElement = c_uint32
OSStatus = c_int32


class AudioObjectPropertyAddress(ctypes.Structure):
    _fields_ = [
        ("mSelector", AudioObjectPropertySelector),
        ("mScope", AudioObjectPropertyScope),
        ("mElement", AudioObjectPropertyElement),
    ]


# Callback type for property listener
# OSStatus (*AudioObjectPropertyListenerProc)(AudioObjectID, UInt32, const AudioObjectPropertyAddress*, void*)
AudioObjectPropertyListenerProc = CFUNCTYPE(
    OSStatus,
    AudioObjectID,
    c_uint32,
    POINTER(AudioObjectPropertyAddress),
    c_void_p
)

# Load CoreAudio framework
try:
    _coreaudio = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreAudio.framework/CoreAudio"
    )

    # AudioObjectAddPropertyListener
    _coreaudio.AudioObjectAddPropertyListener.argtypes = [
        AudioObjectID,
        POINTER(AudioObjectPropertyAddress),
        AudioObjectPropertyListenerProc,
        c_void_p
    ]
    _coreaudio.AudioObjectAddPropertyListener.restype = OSStatus

    # AudioObjectRemovePropertyListener
    _coreaudio.AudioObjectRemovePropertyListener.argtypes = [
        AudioObjectID,
        POINTER(AudioObjectPropertyAddress),
        AudioObjectPropertyListenerProc,
        c_void_p
    ]
    _coreaudio.AudioObjectRemovePropertyListener.restype = OSStatus

    # AudioObjectGetPropertyData
    _coreaudio.AudioObjectGetPropertyData.argtypes = [
        AudioObjectID,
        POINTER(AudioObjectPropertyAddress),
        c_uint32,
        c_void_p,
        POINTER(c_uint32),
        c_void_p
    ]
    _coreaudio.AudioObjectGetPropertyData.restype = OSStatus

    COREAUDIO_AVAILABLE = True
except OSError as e:
    logging.warning(f"Failed to load CoreAudio framework: {e}")
    COREAUDIO_AVAILABLE = False

# Load CoreFoundation for CFRunLoop
try:
    _cf = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )

    _cf.CFRunLoopGetCurrent.argtypes = []
    _cf.CFRunLoopGetCurrent.restype = c_void_p

    _cf.CFRunLoopRun.argtypes = []
    _cf.CFRunLoopRun.restype = None

    _cf.CFRunLoopStop.argtypes = [c_void_p]
    _cf.CFRunLoopStop.restype = None

    # kCFRunLoopDefaultMode
    _cf.kCFRunLoopDefaultMode = c_void_p.in_dll(_cf, "kCFRunLoopDefaultMode")

    COREFOUNDATION_AVAILABLE = True
except OSError as e:
    logging.warning(f"Failed to load CoreFoundation framework: {e}")
    COREFOUNDATION_AVAILABLE = False


def get_default_input_device_id():
    """Get the current default input device AudioObjectID from CoreAudio."""
    if not COREAUDIO_AVAILABLE:
        return None

    address = AudioObjectPropertyAddress(
        kAudioHardwarePropertyDefaultInputDevice,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMain
    )

    device_id = AudioObjectID()
    data_size = c_uint32(sizeof(AudioObjectID))

    status = _coreaudio.AudioObjectGetPropertyData(
        kAudioObjectSystemObject,
        byref(address),
        0,
        None,
        byref(data_size),
        byref(device_id)
    )

    if status != kAudioHardwareNoError:
        logging.error(f"Failed to get default input device: OSStatus {status}")
        return None

    return device_id.value


def refresh_sounddevice():
    """
    Refresh sounddevice's internal PortAudio device cache.

    PortAudio caches device info at initialization. This function
    terminates and re-initializes PortAudio to pick up device changes.
    """
    try:
        # Terminate and reinitialize PortAudio via sounddevice's internal API
        sd._terminate()
        sd._initialize()
        logging.info("Sounddevice/PortAudio device cache refreshed")
    except Exception as e:
        logging.error(f"Failed to refresh sounddevice: {e}")
        raise


class DeviceMonitor:
    """
    Monitors macOS audio device changes using CoreAudio property listeners.

    Usage:
        def on_device_change(old_id, new_id):
            print(f"Device changed from {old_id} to {new_id}")

        monitor = DeviceMonitor(on_device_change)
        monitor.start()
        # ... later ...
        monitor.stop()
    """

    def __init__(self, callback):
        """
        Initialize the device monitor.

        Args:
            callback: Function called when device changes.
                     Signature: callback(old_device_id, new_device_id)
        """
        self._user_callback = callback
        self._running = False
        self._thread = None
        self._runloop = None
        self._last_device_id = None

        # CRITICAL: Keep strong reference to prevent garbage collection
        # The ctypes callback must stay alive as long as the listener is registered
        self._callback_ref = None

        self._property_address = AudioObjectPropertyAddress(
            kAudioHardwarePropertyDefaultInputDevice,
            kAudioObjectPropertyScopeGlobal,
            kAudioObjectPropertyElementMain
        )

    def _property_listener(self, object_id, num_addresses, addresses, client_data):
        """CoreAudio property listener callback."""
        try:
            new_device_id = get_default_input_device_id()

            # Filter spurious callbacks - only notify on actual change
            if new_device_id is not None and new_device_id != self._last_device_id:
                old_id = self._last_device_id
                self._last_device_id = new_device_id
                logging.info(f"CoreAudio: Default input device changed from {old_id} to {new_device_id}")

                # Call user callback in a separate thread to avoid blocking CoreAudio
                if self._user_callback:
                    threading.Thread(
                        target=self._user_callback,
                        args=(old_id, new_device_id),
                        daemon=True
                    ).start()

        except Exception as e:
            logging.error(f"Error in device change listener: {e}")

        return kAudioHardwareNoError

    def _run_loop_thread(self):
        """Thread that runs the CFRunLoop to receive callbacks."""
        try:
            # Register the property listener
            self._callback_ref = AudioObjectPropertyListenerProc(self._property_listener)

            status = _coreaudio.AudioObjectAddPropertyListener(
                kAudioObjectSystemObject,
                byref(self._property_address),
                self._callback_ref,
                None
            )

            if status != kAudioHardwareNoError:
                logging.error(f"Failed to add property listener: OSStatus {status}")
                self._running = False
                return

            logging.info("CoreAudio property listener registered successfully")

            # Store runloop reference for stopping
            self._runloop = _cf.CFRunLoopGetCurrent()

            # Run the loop - this blocks until CFRunLoopStop is called
            _cf.CFRunLoopRun()

            logging.info("CFRunLoop stopped")

        except Exception as e:
            logging.error(f"Error in device monitor run loop: {e}")
        finally:
            self._running = False

    def start(self):
        """Start monitoring for device changes."""
        if not COREAUDIO_AVAILABLE or not COREFOUNDATION_AVAILABLE:
            logging.warning("CoreAudio not available, device monitoring disabled")
            return False

        if self._running:
            logging.warning("Device monitor already running")
            return True

        # Get initial device ID
        self._last_device_id = get_default_input_device_id()
        logging.info(f"Initial default input device ID: {self._last_device_id}")

        self._running = True
        self._thread = threading.Thread(target=self._run_loop_thread, daemon=True)
        self._thread.start()

        return True

    def stop(self):
        """Stop monitoring and clean up resources."""
        if not self._running:
            return

        logging.info("Stopping device monitor...")
        self._running = False

        # Remove the property listener
        if self._callback_ref is not None and COREAUDIO_AVAILABLE:
            try:
                status = _coreaudio.AudioObjectRemovePropertyListener(
                    kAudioObjectSystemObject,
                    byref(self._property_address),
                    self._callback_ref,
                    None
                )
                if status != kAudioHardwareNoError:
                    logging.warning(f"Failed to remove property listener: OSStatus {status}")
                else:
                    logging.info("Property listener removed successfully")
            except Exception as e:
                logging.warning(f"Error removing property listener: {e}")

        # Stop the run loop
        if self._runloop is not None and COREFOUNDATION_AVAILABLE:
            try:
                _cf.CFRunLoopStop(self._runloop)
            except Exception as e:
                logging.warning(f"Error stopping run loop: {e}")

        self._runloop = None
        self._callback_ref = None

    @property
    def is_running(self):
        """Check if the monitor is running."""
        return self._running

    @property
    def last_device_id(self):
        """Get the last known device ID."""
        return self._last_device_id


def get_device_name_by_sounddevice_index(index):
    """Get device name from sounddevice index."""
    try:
        return sd.query_devices(index)['name']
    except Exception:
        return f"Unknown device (index {index})"


def get_current_default_device_name():
    """Get the current default input device name after refreshing."""
    try:
        default_idx = sd.default.device[0]
        if default_idx is not None:
            return sd.query_devices(default_idx)['name']
    except Exception as e:
        logging.warning(f"Could not get default device name: {e}")
    return "Unknown"
