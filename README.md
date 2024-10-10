# macOS Dictation Tool

A macOS dictation tool that uses OpenAI's Whisper model for speech-to-text transcription. This tool allows you to dictate text using your microphone and have it transcribed and pasted into the active application on your Mac.

## Features

-   **Real-time dictation** using OpenAI's Whisper model.
-   **Customizable models**: Choose from different Whisper model sizes for varying accuracy and performance.
-   **Keyboard shortcut activation**: Start and stop dictation with a key press.
-   **Automatic pasting**: Transcribed text is automatically pasted into the active application.
-   **Easy startup**: Create a clickable application to start the dictation tool from your desktop.
-   **Run at startup**: Optionally configure the tool to run automatically when you log in.

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

---

## Prerequisites

-   **macOS**: This tool is designed to run on macOS systems.
-   **Python 3.10 or higher**: Ensure you have Python installed.
-   **Homebrew**: Recommended for installing dependencies.

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/macos-dictate.git
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

#### c. Install Python 3.10 or Higher (if not already installed)

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

Install the latest version of OpenAI Whisper directly from the GitHub repository:

```bash
pip install git+https://github.com/openai/whisper.git
```

### 5. Grant Permissions

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

### Start Dictation

-   Press the **F1** key to start recording.
-   You will receive a notification indicating that recording has started.

### Stop Dictation

-   Press the **F1** key again to stop recording.
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

-- Path to your virtual environment activation script
set venvPath to POSIX path of (choose file with prompt "Select your virtual environment's 'activate' script:")
set venvPathQuoted to quoted form of venvPath

-- Path to your Python script
set scriptPath to POSIX path of (choose file with prompt "Select your 'dictate.py' script:")
set scriptPathQuoted to quoted form of scriptPath

-- Build the command to run
set shellCommand to "source " & venvPathQuoted & " && python " & scriptPathQuoted & " --model " & modelSize

-- Run the command in Terminal
tell application "Terminal"
    activate
    do script shellCommand
end tell
```

**Instructions:**

-   When you run the application, it will prompt you to select your virtual environment's `activate` script and the `dictate.py` script the first time.
-   The paths will be stored in the script for future use.

#### c. Save the Script as an Application

-   Go to **File** > **Export**.
-   Set **File Format** to **Application**.
-   Name it `Start Dictation`.
-   Choose **Desktop** as the location.
-   Click **Save**.

### Option 2: Using Automator

#### a. Open Automator

-   Open **Automator** from your Applications folder.

#### b. Create a New Application

-   Choose **Application** as the document type.

#### c. Add a "Run Shell Script" Action

-   In the left sidebar, select **Actions**.
-   Search for **Run Shell Script**.
-   Drag **Run Shell Script** into the workflow area.

#### d. Configure the Shell Script

Replace the default script with the following:

```bash
#!/bin/bash

# Prompt for model size
modelSize=$(osascript -e 'choose from list {"tiny", "base", "small", "medium", "large"} with prompt "Select Whisper model size:" default items {"base"}')

if [ "$modelSize" = "false" ]; then
    osascript -e 'display alert "No model selected. Exiting."'
    exit 0
fi

# Activate virtual environment
source /path/to/your/venv/bin/activate

# Run your Python script
python /path/to/your/dictate.py --model "$modelSize"
```

**Replace `/path/to/your/venv/bin/activate`** and **`/path/to/your/dictate.py`** with the actual paths on your system.

#### e. Save the Automator Application

-   Go to **File** > **Save**.
-   Name it `Start Dictation`.
-   Choose **Desktop** as the location.
-   Click **Save**.

---

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

Refer to [macOS Virtual Keycodes](https://eastmanreference.com/complete-list-of-applescript-key-codes) for keycode values.

### Improve Transcription Accuracy

-   Use a larger model size (e.g., `small`, `medium`, `large`) when running the script.
-   Ensure you're in a quiet environment with minimal background noise.
-   Use a high-quality microphone.

---

## Troubleshooting

-   **Accessibility Permissions:** Ensure your Terminal application or Python interpreter has the necessary permissions under **System Preferences** > **Security & Privacy** > **Privacy**.

-   **Microphone Permissions:** Ensure your Terminal application or Python interpreter is allowed to access the microphone.

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

# Answer

**Note:** Please ensure all paths and configurations are accurate for your specific setup. If you have any questions or need further assistance, feel free to reach out!
