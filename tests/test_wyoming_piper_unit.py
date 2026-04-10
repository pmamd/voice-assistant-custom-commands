import os
#!/usr/bin/env python3
"""
Unit test for Wyoming-Piper TTS output verification.

This test sends TTS requests directly to Wyoming-Piper and verifies
the output using Whisper STT to ensure proper audio synthesis.
"""

import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from audio_verifier import AudioVerifier


class WyomingPiperTester:
    def __init__(self, port=10200, output_dir="./tests/audio/outputs"):
        self.port = port
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize audio verifier
        self.verifier = AudioVerifier(
            whisper_bin="./build/bin/main",
            model_path="./whisper.cpp/models/ggml-base.en.bin"
        )

    def send_tts_request(self, text, voice="en_US-lessac-medium"):
        """Send TTS request to Wyoming-Piper via Wyoming protocol."""
        print(f"Sending TTS request: '{text}'")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect(('localhost', self.port))

            # Wyoming protocol message format
            request = json.dumps({
                'type': 'synthesize',
                'data': {
                    'text': text,
                    'voice': {'name': voice}
                }
            }) + '\n'

            sock.send(request.encode('utf-8'))
            print(f"Request sent: {request.strip()}")

            # Give time for processing
            time.sleep(3)

            sock.close()
            return True

        except Exception as e:
            print(f"Error sending request: {e}")
            return False

    def find_latest_output(self):
        """Find the most recently created WAV file in output directory."""
        wav_files = sorted(self.output_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime)
        if not wav_files:
            return None
        return wav_files[-1]

    def verify_output(self, wav_file, expected_text):
        """Verify TTS output matches expected text using Whisper."""
        print(f"\nVerifying output: {wav_file}")

        # Transcribe the audio
        result = self.verifier.transcribe(wav_file)

        # Handle tuple return (text, confidence)
        if isinstance(result, tuple):
            transcription, confidence = result
            print(f"Confidence: {confidence:.2%}")
        else:
            transcription = result
            confidence = 0.0

        if not transcription:
            print("ERROR: Failed to transcribe audio")
            return False, None

        print(f"Transcribed text: '{transcription}'")
        print(f"Expected text: '{expected_text}'")

        # Check if transcription matches expected
        transcription_lower = transcription.lower().strip()
        expected_lower = expected_text.lower().strip()

        # Exact match
        if transcription_lower == expected_lower:
            print("✓ PASS: Exact match")
            return True, transcription

        # Contains check
        if expected_lower in transcription_lower:
            print("✓ PASS: Expected text found in transcription")
            return True, transcription

        # Check for "json input" bug
        if "json" in transcription_lower:
            print("✗ FAIL: Output contains 'json input' - Wyoming-Piper bug detected!")
            return False, transcription

        # Fuzzy match
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, expected_lower, transcription_lower).ratio()
        print(f"Similarity: {similarity:.2%}")

        if similarity >= 0.70:
            print(f"✓ PASS: Similar enough ({similarity:.2%})")
            return True, transcription
        else:
            print(f"✗ FAIL: Not similar enough ({similarity:.2%})")
            return False, transcription

    async def run_test(self, text, expected=None):
        """Run a single TTS test."""
        if expected is None:
            expected = text

        print("=" * 70)
        print(f"TEST: '{text}'")
        print("=" * 70)

        # Clear old output file
        latest = self.find_latest_output()
        if latest:
            print(f"Clearing old output: {latest}")

        # Send TTS request
        if not self.send_tts_request(text):
            print("✗ FAIL: Could not send TTS request")
            return False

        # Wait for output file
        print("Waiting for audio output...")
        for i in range(10):
            time.sleep(1)
            new_file = self.find_latest_output()
            if new_file and (not latest or new_file != latest):
                print(f"Found output file: {new_file}")
                break
        else:
            print("✗ FAIL: No output file generated")
            return False

        # Verify output
        passed, transcription = self.verify_output(new_file, expected)

        return passed


async def main():
    """Run Wyoming-Piper unit tests."""
    tester = WyomingPiperTester()

    # Test cases
    tests = [
        ("Hello world", "hello world"),
        ("Testing one two three", "testing one two three"),
        ("The quick brown fox", "the quick brown fox"),
        ("Voice assistant initialized", "voice assistant initialized"),
    ]

    results = []
    for text, expected in tests:
        passed = await tester.run_test(text, expected)
        results.append((text, passed))
        print()

    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)

    for text, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {text}")

    print()
    print(f"Total: {passed_count}/{total_count} passed")

    if passed_count == total_count:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {total_count - passed_count} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))


# ---------------------------------------------------------------------------
# Binary-level LLM output tests (unittest-based)
# These run talk-llama-custom in test mode and inspect its output.
# Run with: python3 -m unittest tests/test_wyoming_piper_unit.py -v
# ---------------------------------------------------------------------------

import re
import subprocess
import unittest

_PROJECT_ROOT = Path(__file__).parent.parent
_BINARY = _PROJECT_ROOT / "build/bin/talk-llama-custom"
_WHISPER_MODEL = _PROJECT_ROOT / "whisper.cpp/models/ggml-base.en.bin"
_LLAMA_URL = os.environ.get("LLAMA_URL", "http://127.0.0.1:8083")
_STORY_AUDIO = _PROJECT_ROOT / "tests/audio/inputs/story_request.wav"
_WYOMING_URL = "http://localhost:10200/"


def _run_binary(audio_file, timeout=300):
    cmd = [
        str(_BINARY), "--llama-url", _LLAMA_URL, "-mw", str(_WHISPER_MODEL),
        "--xtts-url", _WYOMING_URL, "--xtts-voice", "en_US-lessac-medium",
        "--temp", "0.5", "-n", "300", "--allow-newline",
        "--test-input", str(audio_file),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"


def _extract_response(output):
    lines, resp, active = output.split('\n'), [], False
    for line in lines:
        if 'LLaMA:' in line or 'llama:' in line.lower():
            active = True
            idx = line.lower().find('llama:')
            resp.append(line[idx + 6:].strip())
        elif active and line.strip() and not line.startswith('[') and not line.startswith('whisper'):
            resp.append(line.strip())
    return ' '.join(resp).strip()


class TestLLMOutputQuality(unittest.TestCase):
    """
    Tests that verify the binary produces correct LLM output.

    Covers regressions from the newline-stripping fix:
    - Multi-line responses must not be silenced by the \\n antiprompt
    - VAD must not fire during test mode (no real mic)
    """

    def setUp(self):
        for f in [_BINARY, _WHISPER_MODEL, _STORY_AUDIO]:
            if not f.exists():
                self.skipTest(f'Required file not found: {f}')

    def tearDown(self):
        subprocess.run(['pkill', '-9', 'aplay'], capture_output=True)

    def test_story_response_not_truncated(self):
        """
        'Tell me a story' must produce substantially more than an intro phrase.

        Regression: the \\n after "Here is an adventure story for you:" was
        firing the antiprompt and stopping generation before story content
        could be produced. Fixed by --allow-newline and replacing \\n with
        spaces in clean_text before TTS dispatch.
        """
        output = _run_binary(_STORY_AUDIO)
        self.assertNotIn('[TIMEOUT]', output, 'Binary timed out')

        response = _extract_response(output)
        word_count = len(response.split())

        truncation_patterns = [
            r"here is.*story.*for you\s*$",
            r"of course\s*$",
            r"great\s*$",
        ]
        for pattern in truncation_patterns:
            self.assertFalse(
                re.search(pattern, response.lower().strip()),
                f'Response ends at intro phrase — newline antiprompt may still be firing. '
                f'Response: "{response[:200]}"')

        self.assertGreaterEqual(word_count, 20,
            f'Response only {word_count} words — story content was cut off. '
            f'Response: "{response[:200]}"')

    def test_no_false_vad_in_test_mode(self):
        """
        [Speech/Stop!] must not appear when running with injected test audio.

        Regression: the per-token VAD check was triggering on TTS audio
        bleed-through, causing responses to be cut to ~2 words.
        """
        output = _run_binary(_STORY_AUDIO)
        self.assertNotIn('[TIMEOUT]', output, 'Binary timed out')

        for pattern in ['[Speech/Stop!]', '[Speech detected']:
            self.assertNotIn(pattern, output,
                f'False VAD trigger in test mode: "{pattern}" found in output. '
                f'VAD is firing when it should not.')
