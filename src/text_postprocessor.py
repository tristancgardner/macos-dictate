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
    r'Clawed': 'Claude',
    r'ClawedCode': 'Claude-Code',
    r'Soros': 'Suora',
    r'Sora Studios': 'Suora Studios',
    r'Sora': 'Suora',
    r'route':'root',
    r'\bcolon\b': ':',
    r'\bColin\b': ':',
}

# Trigger phrases that cause the following words to be wrapped in quotes
# Each entry: (trigger regex, whether to keep the trigger phrase in output)
QUOTE_TRIGGERS = [
    r'the words?',
    r'a file called',
    r'a folder called',
    r'a function called',
    r'a variable called',
    r'a method called',
    r'a class called',
    r'a table called',
    r'a column called',
    r'called',
]

# Words that signal the end of the quoted portion
STOP_WORDS = {
    'is', 'are', 'was', 'were', 'will', 'would', 'should', 'could', 'can',
    'has', 'have', 'had', 'do', 'does', 'did',
    'and', 'or', 'but', 'so', 'then', 'that', 'which', 'where', 'when',
    'to', 'in', 'on', 'at', 'for', 'from', 'with', 'into', 'about',
    'it', 'this', 'the', 'a', 'an',
}

# Trigger phrases that quote everything remaining (greedy, to end of text)
GREEDY_QUOTE_TRIGGERS = [
    r'to say',
    r'\bsay',
]

def apply_greedy_quotes(text):
    """Wrap everything after greedy trigger phrases in single quotes."""
    trigger_pattern = '|'.join(GREEDY_QUOTE_TRIGGERS)
    pattern = rf'(?i)({trigger_pattern})\s+(.+)'

    def replace_match(m):
        trigger = m.group(1)
        rest = m.group(2).strip().rstrip('.,;:!?')
        trailing = m.group(2).strip()
        trailing_punct = trailing[-1] if trailing and trailing[-1] in '.,;:!?' else ''
        # Capitalize first letter of quoted content
        if rest:
            rest = rest[0].upper() + rest[1:]
        result = f"{trigger} '{rest}'"
        if trailing_punct:
            result += trailing_punct
        return result

    return re.sub(pattern, replace_match, text)

def apply_contextual_quotes(text):
    """Wrap words following trigger phrases in single quotes."""
    trigger_pattern = '|'.join(QUOTE_TRIGGERS)
    # Match trigger phrase followed by one or more words
    pattern = rf'(?i)\b({trigger_pattern})\s+([^.,;:!?\n]+)'

    def replace_match(m):
        trigger = m.group(1)
        rest = m.group(2)
        # Split into words and find where to stop quoting
        words = rest.split()
        quoted = []
        remainder = []
        for i, word in enumerate(words):
            if word.lower().rstrip('.,;:!?') in STOP_WORDS and i > 0:
                remainder = words[i:]
                break
            quoted.append(word)
        else:
            remainder = []

        if not quoted:
            return m.group(0)

        quoted_str = ' '.join(quoted).rstrip('.,;:!?')
        trailing_punct = ''
        original_end = ' '.join(quoted).rstrip()
        if original_end and original_end[-1] in '.,;:!?':
            trailing_punct = original_end[-1]

        result = f"{trigger} '{quoted_str}'"
        if trailing_punct:
            result += trailing_punct
        if remainder:
            result += ' ' + ' '.join(remainder)
        return result

    return re.sub(pattern, replace_match, text)


def correct_variations(text, mappings):
    for pattern, replacement in mappings.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text

def cleanup_text(text):
    # Correct variations first
    text = correct_variations(text, WORD_MAPPINGS)

    # Apply greedy quoting first (say -> quote everything remaining)
    text = apply_greedy_quotes(text)

    # Apply contextual quoting (before punctuation cleanup)
    text = apply_contextual_quotes(text)

    # Single spaces after punctuation
    text = re.sub(r'\s*([.,?!:])\s*', r'\1 ', text)

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
