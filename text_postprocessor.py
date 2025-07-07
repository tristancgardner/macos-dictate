import re
import subprocess
import os
import time

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

def send_text_to_active_app(text):
    # Step 1: Capture the current clipboard content
    try:
        old_clip = subprocess.check_output(['pbpaste'])
    except subprocess.CalledProcessError:
        old_clip = b''

    # Step 2: Copy the new text
    try:
        copy_proc = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
        copy_proc.communicate(input=text.encode('utf-8'))

        # Wait a bit for the system to register new clipboard content
        time.sleep(0.3)

        # Step 3: Paste via Cmd+V
        os.system('osascript -e \'tell application "System Events" to keystroke "v" using {command down}\'')

        # Optional: wait for paste action to complete on slow systems
        time.sleep(0.2)

    finally:
        # Step 4: Restore old clipboard content
        restore_proc = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
        restore_proc.communicate(input=old_clip)
