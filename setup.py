"""
py2app setup for Dictate.app

Usage:
    python setup.py py2app -A    # alias (development) mode
    python setup.py py2app       # standalone mode (not yet tested)
"""
from setuptools import setup

APP = ['dictate.py']
DATA_FILES = ['.env.local']

OPTIONS = {
    'argv_emulation': False,  # Critical for PyObjC - must be False
    'iconfile': 'Dictate.icns',
    'plist': {
        'CFBundleName': 'Dictate',
        'CFBundleDisplayName': 'Dictate',
        'CFBundleIdentifier': 'com.suorastudios.dictate',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': True,  # No dock icon
        'NSMicrophoneUsageDescription': 'Dictate needs microphone access to transcribe speech.',
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
    ],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
