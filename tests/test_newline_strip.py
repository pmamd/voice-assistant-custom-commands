"""
Test: Newline stripping in LLM output

Verifies that multi-line LLM responses are delivered fully to TTS and not
cut short by the \\n antiprompt.

Regression test for: LLM responding "Here is an adventure story for you:"
then producing nothing further because the trailing \\n matched the antiprompt
and killed generation before story content could be produced.

Fix: \\n characters are replaced with spaces in clean_text before being
added to text_to_speak, so the \\n antiprompt never fires on LLM output.
"""

import subprocess
import sys
import time
import re
from pathlib import Path


def kill_aplay():
    """Kill any remaining aplay processes left over from TTS playback."""
    subprocess.run(['pkill', '-9', 'aplay'], capture_output=True)

PROJECT_ROOT = Path(__file__).parent.parent
BINARY = PROJECT_ROOT / "build/bin/talk-llama-custom"
WHISPER_MODEL = PROJECT_ROOT / "whisper.cpp/models/ggml-tiny.en.bin"
LLAMA_MODEL = PROJECT_ROOT / "models/llama-2-7b-chat.Q4_K_M.gguf"
STORY_AUDIO = PROJECT_ROOT / "tests/audio/inputs/story_request.wav"
WYOMING_URL = "http://localhost:10200/"


def run_binary_with_input(audio_file: Path, timeout: int = 60) -> str:
    """
    Run talk-llama-custom in test mode with the given audio file.
    Returns stdout output from the binary.
    """
    cmd = [
        str(BINARY),
        "-ml", str(LLAMA_MODEL),
        "-mw", str(WHISPER_MODEL),
        "--xtts-url", WYOMING_URL,
        "--xtts-voice", "en_US-lessac-medium",
        "--temp", "0.5",
        "-n", "300",
        "--allow-newline",
        "--test-input", str(audio_file),
    ]

    print(f"Running: {' '.join(cmd[:4])} ...")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"


def extract_llama_response(output: str) -> str:
    """Extract what the LLM said from binary stdout."""
    # Look for "LLaMA:" prefix in output
    lines = output.split('\n')
    response_lines = []
    in_response = False
    for line in lines:
        if 'LLaMA:' in line or 'llama:' in line.lower():
            in_response = True
            # Take everything after "LLaMA:"
            idx = line.lower().find('llama:')
            response_lines.append(line[idx + 6:].strip())
        elif in_response and line.strip() and not line.startswith('[') and not line.startswith('whisper'):
            response_lines.append(line.strip())
    return ' '.join(response_lines).strip()


def count_words(text: str) -> int:
    return len(text.split())


def test_story_response_not_truncated():
    """
    Asking 'tell me a story' should produce a response with substantially
    more than a few words. Before the fix, the \\n after "Here is an adventure
    story for you:" would fire the antiprompt and stop generation, resulting
    in zero story content.

    We require at least 20 words in the LLM response as evidence that
    generation continued past the intro sentence into actual story content.
    """
    print("\n" + "="*60)
    print("TEST: Story response not truncated by newline antiprompt")
    print("="*60)

    for required_file in [BINARY, WHISPER_MODEL, LLAMA_MODEL, STORY_AUDIO]:
        if not required_file.exists():
            print(f"SKIP: {required_file} not found")
            return True  # Not a failure, just skipped

    output = run_binary_with_input(STORY_AUDIO, timeout=120)

    if "[TIMEOUT]" in output:
        print("FAIL: Binary timed out")
        print(output[-500:])
        return False

    print("--- Binary output (last 800 chars) ---")
    print(output[-800:])
    print("--------------------------------------")

    response = extract_llama_response(output)
    word_count = count_words(response)

    print(f"\nExtracted LLM response ({word_count} words):")
    print(f"  '{response[:200]}{'...' if len(response) > 200 else ''}'")

    # Check the response doesn't stop immediately after an intro phrase
    truncation_patterns = [
        r"here is.*story.*for you\s*$",
        r"of course\s*$",
        r"great\s*$",
    ]
    response_lower = response.lower().strip()
    for pattern in truncation_patterns:
        if re.search(pattern, response_lower):
            print(f"\nFAIL: Response appears to end at intro phrase (pattern: {pattern})")
            print("      This suggests the newline antiprompt is still firing.")
            return False

    if word_count < 20:
        print(f"\nFAIL: Response only {word_count} words — expected >= 20")
        print("      Story content was likely cut off. Newline stripping may not be working.")
        return False

    print(f"\nPASS: Response has {word_count} words — story content generated successfully")
    kill_aplay()
    return True


def test_no_speech_stop_in_output():
    """
    The '[Speech/Stop!]' or '[Speech detected' message should NOT appear
    in the output when running from a test audio file (no real mic input).

    Regression test for the false-positive VAD that was triggering on TTS audio.
    """
    print("\n" + "="*60)
    print("TEST: No false VAD triggers in test mode")
    print("="*60)

    for required_file in [BINARY, WHISPER_MODEL, LLAMA_MODEL, STORY_AUDIO]:
        if not required_file.exists():
            print(f"SKIP: {required_file} not found")
            return True

    output = run_binary_with_input(STORY_AUDIO, timeout=120)

    if "[TIMEOUT]" in output:
        print("FAIL: Binary timed out")
        return False

    false_trigger_patterns = [
        "[Speech/Stop!]",
        "[Speech detected",
    ]

    for pattern in false_trigger_patterns:
        if pattern in output:
            print(f"FAIL: False VAD trigger found in output: '{pattern}'")
            print("      The VAD is firing in test mode, which it should not.")
            return False

    print("PASS: No false VAD triggers in output")
    kill_aplay()
    return True


if __name__ == "__main__":
    results = []
    try:
        results.append(test_story_response_not_truncated())
        results.append(test_no_speech_stop_in_output())
    finally:
        kill_aplay()  # always clean up, even on failure

    print("\n" + "="*60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} passed")
    print("="*60)

    sys.exit(0 if all(results) else 1)
