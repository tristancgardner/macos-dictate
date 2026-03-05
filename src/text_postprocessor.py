import re
import subprocess
import os
import json
import time
import threading
from pathlib import Path

SIMPLE_MAPPINGS = {
    r'\bcolon\b': ':',
    r'\bColin\b': ':',
    r'\bslash\b': '/',
}

COMPLEX_MAPPINGS = {
    r'\bdot\s*files?\b': 'dotfiles',
    r'\bdot\b(?!\s*files?\b)': '.',
    r'\bnew ?line\b': '\n',
    r'\bspec\s*weave\b': 'specweave',
    r'\bspec\s*wave\b': 'specweave',
    r'\bspeck\s*weave\b': 'specweave',
}
# Load personal mappings from mappings.local.json (gitignored)
_LOCAL_MAPPINGS_PATH = Path(__file__).resolve().parent.parent / 'mappings.local.json'
if _LOCAL_MAPPINGS_PATH.exists():
    with open(_LOCAL_MAPPINGS_PATH, encoding='utf-8') as f:
        SIMPLE_MAPPINGS.update(json.load(f))

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
# DISABLED: Testing without greedy 'say' quoting — re-enable if needed
# GREEDY_QUOTE_TRIGGERS = [
#     r'to say',
#     r'\bsay',
# ]
#
# def apply_greedy_quotes(text):
#     """Wrap everything after greedy trigger phrases in single quotes."""
#     trigger_pattern = '|'.join(GREEDY_QUOTE_TRIGGERS)
#     pattern = rf'(?i)({trigger_pattern})\s+(.+)'
#
#     def replace_match(m):
#         trigger = m.group(1)
#         rest = m.group(2).strip().rstrip('.,;:!?')
#         trailing = m.group(2).strip()
#         trailing_punct = trailing[-1] if trailing and trailing[-1] in '.,;:!?' else ''
#         # Capitalize first letter of quoted content
#         if rest:
#             rest = rest[0].upper() + rest[1:]
#         result = f"{trigger} '{rest}'"
#         if trailing_punct:
#             result += trailing_punct
#         return result
#
#     return re.sub(pattern, replace_match, text)

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
    # Correct variations: simple first (order matters for complex pattern dependencies)
    text = correct_variations(text, SIMPLE_MAPPINGS)
    # Whisper outputs ".files" (literal period) instead of "dot files" — fix before complex mappings
    text = re.sub(r'\.files?\b', 'dotfiles', text, flags=re.IGNORECASE)
    text = correct_variations(text, COMPLEX_MAPPINGS)

    # Clean up around newlines from "new line" word mapping, then protect with placeholder
    _NL = '<<NL>>'
    text = re.sub(r'(?<=[.,])\s*\n\s*[.,]?\s*', _NL, text)      # period/comma already present before \n
    text = re.sub(r'(?<![.,])\s*\n\s*[.,]?\s*', f'.{_NL}', text)  # no period before \n, add one

    # Contextual dash/hyphen: only at sentence boundaries (followed by period from Whisper)
    text = re.sub(r'\b[Dd]ash\.\s*', '- ', text)
    text = re.sub(r'\b[Hh]yphen\.\s*', '- ', text)

    # Collapse redundant punctuation clusters (e.g. ", . ." or ". . ." from Whisper + word mapping)
    # Note: requires at least one actual dot — avoids converting normal ", " into ". "
    text = re.sub(r',[ .]*\.[ .]*', '. ', text)
    text = re.sub(r'\.[ .]+', '. ', text)

    # Collapse inline punctuation using placeholders to protect from punctuation spacing step
    _COMMA = '<<COMMA>>'
    text = re.sub(r'(\d),\s*(\d{3})\b', rf'\1{_COMMA}\2', text)  # protect $4,000 etc.
    _DOT = '<<DOT>>'
    text = re.sub(r'(\d+)\s+point\s+(\d+)', rf'\1{_DOT}\2', text, flags=re.IGNORECASE)
    text = re.sub(r'(\d)\.(\d)', rf'\1{_DOT}\2', text)  # protect digit.digit (e.g. 3.5)
    text = re.sub(r'(\w)\.([a-z])', rf'\1{_DOT}\2', text)  # protect word.lowercase (e.g. Next.js, public.master)
    text = re.sub(r'(\w)\s+/\s+(\w)', r'\1/\2', text)
    text = re.sub(r'(\w)\s+\.\s+(\w)', rf'\1{_DOT}\2', text)

    # Apply greedy quoting first (say -> quote everything remaining)
    # DISABLED: text = apply_greedy_quotes(text)

    # Apply contextual quoting (before punctuation cleanup)
    text = apply_contextual_quotes(text)

    # Single spaces after punctuation
    text = re.sub(r'\s*([.,?!:])\s*', r'\1 ', text)

    # Restore placeholders
    text = text.replace(_COMMA, ',')
    text = text.replace(_DOT, '.')
    text = text.replace(f' {_NL}', _NL)  # remove space punctuation step added before NL
    text = text.replace(_NL, '\n')

    # Remove trailing commas before a newline (keep periods)
    text = re.sub(r',\s*\n', r'.\n', text)

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
