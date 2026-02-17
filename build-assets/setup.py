"""
py2app setup for Dictate.app

Usage (run from project root):
    python build-assets/setup.py py2app -A    # alias (development) mode
    python build-assets/setup.py py2app       # standalone mode (not yet tested)
"""
from setuptools import setup
import os

# Ensure paths resolve relative to project root, not build-assets/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)
import sys
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

APP = ['src/dictate.py']
DATA_FILES = ['.env.local']

OPTIONS = {
    'argv_emulation': False,  # Critical for PyObjC - must be False
    'iconfile': 'build-assets/Dictate.icns',
    'plist': {
        'CFBundleName': 'Dictate',
        'CFBundleDisplayName': 'Dictate',
        'CFBundleIdentifier': 'com.suorastudios.dictate',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': True,  # No dock icon
        'NSMicrophoneUsageDescription': 'Dictate needs microphone access to transcribe speech.',
        'NSAppSleepDisabled': True,  # Disable App Nap to prevent CPU throttling
        'NSSupportsAutomaticGraphicsSwitching': False,  # Force high-performance GPU/cores
    },
    'packages': [
        'whisper',
        'sounddevice',
        '_sounddevice_data',
        'numpy',
        'torch',
        'psutil',
    ],
    'includes': [
        'Quartz',
        'AppKit',
        'text_postprocessor',
        'device_monitor',
        'audio',
        'transcription',
        'watchdog',
        'keyboard',
        'process',
    ],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
