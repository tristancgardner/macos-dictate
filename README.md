# Whisper Dictation for MacOS

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)

A powerful and reliable alternative to macOS's built-in dictation feature, using OpenAI's Whisper model for speech-to-text transcription. This tool allows you to dictate text using your microphone and have it transcribed and pasted into any active application on your Mac, solving the long-standing issues of inconsistent performance in native macOS dictation.

![macOS Dictation Tool Header](./header_image.webp)

## Features

### Core Features

-   **Real-time Dictation**: Instant speech-to-text conversion using OpenAI's Whisper model
-   **Automatic Pasting**: Transcribed text instantly appears in your active application
-   **Background Operation**: Runs silently in the background until activated
-   **Microphone Flexibility**: Seamlessly switch between different audio input sources

### Customization

-   **Multiple Model Options**: Choose from various Whisper models:
    -   `tiny` (~75MB RAM) - Fastest, basic accuracy
    -   `base` (~150MB RAM) - Good balance of speed and accuracy
    -   `small` (~500MB RAM) - Better accuracy, moderate resource usage
    -   `medium` (~1.5GB RAM) - High accuracy, higher resource usage
    -   `large` (~3GB RAM) - Highest accuracy, significant resource usage
-   **Configurable Shortcuts**: Customize keyboard triggers to your preference
-   **Startup Options**: Configure automatic startup on login

### System Integration

-   **Desktop Application**: Create a clickable app for easy access
-   **System Tray Integration**: Quick access to controls and settings
-   **Permissions Management**: Automated handling of system permissions

## System Requirements

-   **Operating System**: macOS 10.15 or higher
-   **RAM**:
    -   Minimum: 4GB (for tiny/base models)
    -   Recommended: 8GB+ (for small/medium models)
    -   High-Performance: 16GB+ (for large model)
-   **Storage**:
    -   500MB minimum
    -   2GB+ recommended for multiple models
-   **Processor**:
    -   Intel: Core i5 or higher recommended
    -   Apple Silicon: All models supported

## Quick Start Guide

1. **Installation** (5-10 minutes):

```bash
git clone https://github.com/tristancgardner/macos-dictate.git
cd macos-dictate
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. **Basic Usage**:

```bash
# Start with default (base) model
python dictate.py

# Or specify a model size
python dictate.py --model small
```

3. **Operation**:

-   Press `F1` to start recording
-   Speak clearly into your microphone
-   Press `F1` again to stop and paste the text

---

## Table of Contents

-   [Prerequisites](#prerequisites)
-   [Installation](#installation)
    -   [1. Clone the Repository](#1-clone-the-repository)
    -   [2. Install Dependencies](#2-install-dependencies)
    -   [3. Create and Activate a Virtual Environment](#3-create-and-activate-a-virtual-environment)
    -   [4. Install Python Packages](#4-install-python-packages)
    -   [5. Grant Permissions](#5-grant-permissions)
-   [Usage](#usage)
    -   [Running the Script](#running-the-script)
    -   [Start Dictation](#start-dictation)
    -   [Stop Dictation](#stop-dictation)
-   [Creating a Clickable Application](#creating-a-clickable-application)
    -   [Option 1: Using AppleScript](#option-1-using-applescript)
    -   [Option 2: Using Automator](#option-2-using-automator)
-   [Running the Tool at Startup](#running-the-tool-at-startup)
-   [Configuration](#configuration)
    -   [Change the Trigger Key](#change-the-trigger-key)
    -   [Improve Transcription Accuracy](#improve-transcription-accuracy)
-   [Troubleshooting](#troubleshooting)
-   [Contributing](#contributing)
-   [License](#license)
-   [Acknowledgments](#acknowledgments)
-   [Planned Future Features](#planned-future-features)
-   [Issues and Feature Requests](#issues-and-feature-requests)

---

## Prerequisites

-   **macOS**: This tool is designed to run on macOS systems.
-   **Python 3.10 or higher**: Ensure you have Python installed.
-   **Homebrew**: Recommended for installing dependencies.

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/tristancgardner/macos-dictate.git
cd macos-dictate
```

### 2. Install Dependencies

#### a. Install Homebrew (if not already installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### b. Install Required Libraries

```bash
brew update
brew install portaudio
```

#### c. Install ffmpeg

```bash
brew install ffmpeg
```

This is required for Whisper to process audio files.

#### d. Install Python 3.10 or Higher (if not already installed)

Download and install Python from the official website:

-   [Python Releases for macOS](https://www.python.org/downloads/macos/)

Verify the installation:

```bash
python3 --version
```

Ensure it shows Python 3.10 or higher.

### 3. Create and Activate a Virtual Environment

Create a virtual environment using the built-in `venv` module:

```bash
python3 -m venv venv
```

Activate the virtual environment:

```bash
source venv/bin/activate
```

### 4. Install Python Packages

#### a. Upgrade `pip`

```bash
pip install --upgrade pip
```

#### b. Install Dependencies

Install necessary Python packages, including `torch`, `sounddevice`, `numpy`, `pyobjc`, and other required libraries.

```bash
pip install torch sounddevice numpy pyobjc
```

#### c. Install Whisper from GitHub

Install the latest version of OpenAI Whisper directly from the GitHub repository to utilize most recent ASR updates (as opposed to using `pip install openai-whisper`):

```bash
pip install git+https://github.com/openai/whisper.git
```

### 5. Grant Permissions

_You can skip this step and enable permissions once you run the application later on._

#### a. Accessibility Permissions

-   Go to **System Preferences** > **Security & Privacy** > **Privacy** > **Accessibility**.
-   Click the lock to make changes and enter your password.
-   Add your Terminal application (e.g., iTerm, Terminal) or Python interpreter to the list and ensure it's checked.

#### b. Microphone Permissions

-   Go to **System Preferences** > **Security & Privacy** > **Privacy** > **Microphone**.
-   Add your Terminal application or Python interpreter to the list and ensure it's checked.

---

## Usage

### Running the Script

Ensure your virtual environment is activated:

```bash
source venv/bin/activate
```

Run the script with your desired model size:

```bash
python dictate.py --model base
```

Replace `base` with the desired Whisper model size (`tiny`, `base`, `small`, `medium`, `large`).
The base model is enabled by default if you don't use the `--model` tag.

The base model uses about 400 to 500 megabytes of system RAM. The small model increases that by 400 to 500 mb. Use `Activity Monitor` to monitor RAM & CPU usage to find a model that has no system impact while left running persistenly.

### Start Dictation

-   Press the **F1** key (default trigger key) to start recording (press **fn** + **F1** if you haven't set function keys to override mac controls (the symbols on the function keys like brightness, volume, etc.)).
-   You will receive a notification indicating that recording has started.

### Change Trigger Key

You can customize the trigger key for starting and stopping dictation. For instructions on how to change the trigger key, refer to the [Change the Trigger Key](#change-the-trigger-key) section in the Configuration part of this document.

### Stop Dictation

-   Press the **F1** key (default trigger key) again to stop recording.
-   You will receive a notification indicating that recording has stopped.
-   The transcribed text will be automatically pasted into the active application.

---

## Creating a Clickable Application

You can create an application that you can double-click to start the dictation tool without opening Terminal manually.

### Option 1: Using AppleScript

#### a. Open Script Editor

-   Open **Script Editor** by searching for it in Spotlight (press `Cmd + Space` and type "Script Editor").

#### b. Write the AppleScript

Paste the following script into the editor:
(New as of 241206)

```applescript
-- Prompt the user to choose a Whisper model size
set modelSizes to {"tiny", "base", "small", "medium", "large"}
set defaultModel to "base"
set chosenModel to choose from list modelSizes with prompt "Select Whisper model size:" default items defaultModel

if chosenModel is false then
	display alert "No model selected. Exiting."
	return
end if

set modelSize to item 1 of chosenModel

-- Direct path to the Python interpreter in your virtual environment
set pythonPath to "/Users/tristangardner/.pyenv/versions/3.12.7/envs/venv/bin/python"

-- Path to your Python script
set scriptPath to "/Users/tristangardner/Documents/Programming/01_Apps/macos-dictate/dictate.py"

-- Build the command to use zsh to ensure proper environment loading
set shellCommand to "zsh -l -c " & quoted form of (pythonPath & " " & scriptPath & " --model " & modelSize)

-- Run the Python script in the background without opening Terminal
do shell script shellCommand & " >/dev/null 2>&1 &"
```

#### c. Save the Script as an Application

-   Go to **File** > **Export**.
-   Set **File Format** to **Application**.
-   Name it `Dictate`.
-   Choose **Applications** as the location.
-   Click **Save**.

**Instructions:**

## Running the Tool at Startup

You can configure the dictation tool to run automatically when you log in.

**Note:** Be cautious when setting scripts to run at startup. Ensure that the script does not require user interaction at startup, or it may hinder the login process.

### Steps:

1. **Create a Launch Agent**

    Create a property list file (`.plist`) in the `~/Library/LaunchAgents` directory.

2. **Create the `.plist` File**

    Open Terminal and run:

    ```bash
    touch ~/Library/LaunchAgents/com.yourusername.macos-dictate.plist
    ```

3. **Edit the `.plist` File**

    Open the file in a text editor:

    ```bash
    open -e ~/Library/LaunchAgents/com.yourusername.macos-dictate.plist
    ```

    Paste the following content:

    ```xml
    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>Label</key>
        <string>com.yourusername.macos-dictate</string>
        <key>ProgramArguments</key>
        <array>
            <string>/bin/bash</string>
            <string>-c</string>
            <string>source /path/to/your/venv/bin/activate && python /path/to/your/dictate.py --model base</string>
        </array>
        <key>RunAtLoad</key>
        <true/>
        <key>KeepAlive</key>
        <true/>
        <key>StandardOutPath</key>
        <string>/tmp/macos-dictate.log</string>
        <key>StandardErrorPath</key>
        <string>/tmp/macos-dictate.error.log</string>
    </dict>
    </plist>
    ```

    **Replace `/path/to/your/venv/bin/activate`** and **`/path/to/your/dictate.py`** with the actual paths.

4. **Load the Launch Agent**

    ```bash
    launchctl load ~/Library/LaunchAgents/com.yourusername.macos-dictate.plist
    ```

**Important Notes:**

-   **User Interaction:** Since the script may require user interaction (e.g., pressing the trigger key), ensure it doesn't block the startup process.
-   **Logging:** Output and errors are logged to `/tmp/macos-dictate.log` and `/tmp/macos-dictate.error.log` respectively.
-   **Unloading the Launch Agent:** To stop the script from running at startup:

    ```bash
    launchctl unload ~/Library/LaunchAgents/com.yourusername.macos-dictate.plist
    ```

---

## Configuration

### Change the Trigger Key

To change the key that starts and stops dictation, modify the `keycode` in the `dictate.py` script:

```python
# For example, to use F5 (keycode 96)
if keycode == 96:
    toggle_recording()
    return None  # Suppress the event to prevent system beep
```

Remember to save the file after making changes.

Refer to [macOS Virtual Keycodes](https://eastmanreference.com/complete-list-of-applescript-key-codes) for keycode values.

### Improve Transcription Accuracy

-   Use a larger model size (e.g., `small`, `medium`, `large`) when running the script.
-   Ensure you're in a quiet environment with minimal background noise.
-   Use a high-quality microphone.

---

## Troubleshooting

**Accessibility and Microphone Permissions**
The app will automatically request Accessibility and Microphone permissions on its first run. If permissions are not requested or the app fails to start:

-   Go to **System Settings** > **Privacy & Security** > **Accessibility** and **Microphone**.
-   Add the application manually if necessary by clicking the **"+"** button and selecting it.

-   **PortAudio Errors:** If you encounter errors related to `PortAudio` or `sounddevice`, ensure that `portaudio` is installed via Homebrew and reinstall `sounddevice`:

    ```bash
    brew install portaudio
    pip uninstall sounddevice
    pip install sounddevice
    ```

-   **No Text Pasted:** Ensure the active application accepts paste commands and is not blocking automated inputs.

-   **Script Not Running at Startup:** Check the contents of your `.plist` file for correctness and verify that the paths are accurate.

-   **Application Not Opening:** If the application created via AppleScript or Automator doesn't open, ensure that the script paths are correct and that you have execution permissions.

---

## Planned Future Features

We're constantly working to improve the macOS Dictation Tool. Here are some features we're planning to implement in future updates:

-   [x] Fixed added space at beginning of every transcription
-   [x] App now runs in the background with different permissions, terminal does not open
-   [x] PID process cleanup logic added to prevent memory leaks
-   [x] Allows changing input mic source without breaking the audio input source and requiring to restart the script/app - this solves an issue with MacOS's built-in dictation feature for over a decade
-   [ ] **Add back the indicator for recording and recording stopped**
-   [ ] (delayed) Responsive cursor updates for certain keywords like "New Line" or "New Paragraph"
    -   Tested, not good enough yet for production
-   [ ] Custom voice commands for text formatting (e.g., "Bold this", "Italicize that")
-   [ ] Real-time transcription display with on-the-fly editing
-   [ ] Better UI/UX for dictation settings including always-on-top indicator and top-bar icon
-   [ ] Extended punctuation auto-correction and smart capitalization abilities
-   [ ] Multi-language support with language detection
-   [ ] User-defined custom vocabulary and acronym expansion
-   [ ] Voice-activated undo and redo functionality
-   [ ] Master log of all dictations saved to file for any use: training on your own speech patterns, etc.
-   [ ] Customizable noise cancellation and audio filtering options

We're excited about these upcoming improvements and welcome any suggestions for additional features!

---

## Issues and Feature Requests

We welcome feedback, bug reports, and feature requests! If you encounter any problems or have ideas for improvements, please use our GitHub issue tracker:

-   For bug reports: [Submit an issue](https://github.com/tristancgardner/macos-dictate/issues/new?template=bug_report.md)
-   For feature requests: [Submit a feature request](https://github.com/tristancgardner/macos-dictate/issues/new?template=feature_request.md)

When submitting an issue, please provide as much detail as possible, including:

-   Steps to reproduce the problem
-   Expected behavior
-   Actual behavior
-   Your operating system version
-   Your Python version
-   Any relevant error messages or screenshots

Your contributions help make this tool better for everyone. Thank you for your support!

---

## Contributing

Contributions are welcome! Please fork the repository and create a pull request with your changes.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

-   [OpenAI Whisper](https://github.com/openai/whisper)
-   [PyObjC](https://pypi.org/project/pyobjc/)
-   [PortAudio](http://www.portaudio.com/)
-   [Homebrew](https://brew.sh/)
-   Community contributions and support.

---
