import re
import subprocess
import os
import time
import threading

WORD_MAPPINGS = {
    r'super-?base': 'Supabase',
    r'super base': 'Supabase',
    r'supabase': 'Supabase',
    r'next\.js': 'Next.js',
    r'nextjs': 'Next.js',
    r'mtp': 'MCP',
    r'versal': 'Vercel',
    r'file ID': 'file_id',
    r'File ID': 'file_id',
    r'result json': 'result_json',
    r'dialog summary': 'dialog_summary',
    r'speaker map': 'speaker_map',
    r'dialogue': 'dialog',
    r'dialogue summary': 'dialog_summary',
    r'file name column': 'file_name column',
    r'OG ASR': 'og_asr',
    r' original ASR': 'og_asr',
    r'original asr': 'og_asr',
    r'O-G-A-S-R': 'og_asr',
    r'Cloud': 'Claude',
    r'CloudCode': 'Claude-Code',
    r'Cloud Code': 'Claude-Code',
    r'Club code': 'Claude-Code',
    r'Clawed code': 'Claude-Code',
    r'Soros': 'Suora',
    
}


def correct_variations(text, mappings):
    for pattern, replacement in mappings.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text

def cleanup_text(text):
    # Correct variations first
    text = correct_variations(text, WORD_MAPPINGS)

    # Single spaces after punctuation
    text = re.sub(r'\s*([.,?!])\s*', r'\1 ', text)

    # Remove extra punctuation before a newline
    text = re.sub(r'[.,]\s*\n', r'\n', text)

    # Standardize multiple newlines => double newline
    text = re.sub(r'\n+', '\n\n', text)

    # Trim each line
    text = "\n".join(line.strip() for line in text.splitlines())

    return text

def _deferred_clipboard_restore(old_clip, delay=1.0):
    """Restore clipboard content after a delay (runs in background thread)."""
    time.sleep(delay)
    restore_proc = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
    restore_proc.communicate(input=old_clip)

def send_text_to_active_app(text):
    # Step 1: Capture the current clipboard content
    try:
        old_clip = subprocess.check_output(['pbpaste'])
    except subprocess.CalledProcessError:
        old_clip = b''

    # Step 2: Copy the new text
    copy_proc = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
    copy_proc.communicate(input=text.encode('utf-8'))

    # Wait a bit for the system to register new clipboard content
    time.sleep(0.3)

    # Step 3: Paste via Cmd+V
    os.system('osascript -e \'tell application "System Events" to keystroke "v" using {command down}\'')

    # Step 4: Restore clipboard in background after delay (allows paste to complete)
    restore_thread = threading.Thread(
        target=_deferred_clipboard_restore,
        args=(old_clip,),
        daemon=True
    )
    restore_thread.start()
