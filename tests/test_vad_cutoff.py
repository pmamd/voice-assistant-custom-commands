#!/usr/bin/env python3
"""
Test that VAD doesn't cut off multi-word phrases mid-sentence.

Specifically tests the fix for early stop detection running multiple times
and causing partial transcriptions like:
  - "Navigate to"
  - "to Starbucks"
  - "box"
Instead of the full utterance: "Navigate to Starbucks"
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audio_generator import AudioGenerator


class VADCutoffTester:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.talk_llama_bin = project_root / "build/bin/voice-assistant"
        self.whisper_model = project_root / "external/whisper.cpp/models/for-tests-ggml-base.bin"

        self.generator = AudioGenerator(
            piper_bin=str(Path.home() / ".local/bin/piper"),
            model_dir=str(project_root / "piper-data"),
            output_dir=str(project_root / "tests/audio/inputs")
        )

    def test_navigate_to_starbucks(self):
        """Test that 'Navigate to Starbucks' is transcribed as one complete phrase."""
        print("\n" + "="*70)
        print("TEST: VAD Cutoff - Navigate to Starbucks")
        print("="*70)

        # Generate audio
        print("\n1. Generating test audio...")
        text = "Navigate to Starbucks"
        wav_file = self.generator.generate(text, output_name="navigate_to_starbucks")
        print(f"   Audio file: {wav_file}")

        if not wav_file.exists():
            print("   ✗ Failed to generate audio file")
            return False

        # Test with voice-assistant in test mode
        print("\n2. Running voice-assistant with audio injection...")

        cmd = [
            str(self.talk_llama_bin),
            "-mw", str(self.whisper_model),
            "--llama-url", "http://localhost:8080",
            "--xtts-url", "http://localhost:10200/",
            "--xtts-voice", "en_US-lessac-medium",
            "--temp", "0.5",
            "-vth", "1.2",
            "--vad-last-ms", "700",
            "-n", "300",
            "-p", "Driver",
            "-c", "-1",
            "--test-input", str(wav_file),
            "--print-energy"  # Enable debug output to see VAD behavior
        ]

        try:
            print(f"   Command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30
            )

            output = result.stdout
            print("\n3. Analyzing output...")
            print("-" * 70)
            print(output)
            print("-" * 70)

            # Check for success criteria
            success = True
            issues = []

            # Check 1: Should NOT see multiple partial transcriptions
            partial_phrases = [
                "Navigate to\n",  # Incomplete phrase
                "to Starbucks\n",  # Fragment starting mid-phrase
                "box\n"            # Mishearing of "bucks"
            ]

            for partial in partial_phrases:
                if partial in output:
                    success = False
                    issues.append(f"Found partial transcription: {partial.strip()!r}")

            # Check 2: SHOULD see the complete phrase
            complete_phrase = "Navigate to Starbucks"
            if complete_phrase not in output and "navigate to starbucks" not in output.lower():
                success = False
                issues.append(f"Complete phrase '{complete_phrase}' not found in output")

            # Check 3: Should NOT see multiple "Driver:" prompts in quick succession
            # (indicates multiple VAD triggers for the same utterance)
            driver_count = output.count("Driver:")
            if driver_count > 2:  # Allow 1 for start, maybe 1 retry, but not 5+
                success = False
                issues.append(f"Too many Driver prompts ({driver_count}), indicates multiple VAD triggers")

            # Check 4: Should NOT see multiple early stop checks for same utterance
            if output.count("[Early Stop Check:") > 1:
                success = False
                issues.append("Multiple early stop checks detected (should only run once per speech session)")

            print("\n4. Test Results:")
            print("-" * 70)

            if success:
                print("✓ PASS: Audio processed correctly as single complete phrase")
                print(f"  - No partial transcriptions detected")
                print(f"  - Complete phrase found")
                print(f"  - Single VAD trigger")
                return True
            else:
                print("✗ FAIL: VAD cutoff issues detected")
                for issue in issues:
                    print(f"  - {issue}")
                return False

        except subprocess.TimeoutExpired:
            print("✗ FAIL: Test timed out after 30s")
            return False
        except Exception as e:
            print(f"✗ FAIL: Exception during test: {e}")
            return False

    def test_multi_word_commands(self):
        """Test various multi-word phrases that fall in the 1200-1800ms early stop window."""
        print("\n" + "="*70)
        print("TEST: VAD Cutoff - Multiple Multi-Word Phrases")
        print("="*70)

        test_cases = [
            ("Make it warmer", "make_it_warmer"),
            ("Turn up the volume", "turn_up_volume"),
            ("What is the weather", "weather_query"),
            ("Set timer for five minutes", "set_timer"),
        ]

        results = []

        for text, filename in test_cases:
            print(f"\n  Testing: '{text}'")
            wav_file = self.generator.generate(text, output_name=filename)

            if not wav_file.exists():
                print(f"    ✗ Failed to generate audio")
                results.append((text, False))
                continue

            # Quick test - just check if whisper can transcribe it correctly
            cmd = [
                str(self.project_root / "build/bin/whisper-cli"),
                "-m", str(self.whisper_model),
                "-f", str(wav_file),
                "--language", "en"
            ]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                output = result.stdout + result.stderr

                # Check if the complete phrase is in the output
                if text.lower() in output.lower():
                    print(f"    ✓ Transcribed correctly")
                    results.append((text, True))
                else:
                    print(f"    ✗ Transcription issue")
                    print(f"      Expected: {text}")
                    print(f"      Got: {output[:200]}")
                    results.append((text, False))

            except Exception as e:
                print(f"    ✗ Error: {e}")
                results.append((text, False))

        # Summary
        print("\n" + "="*70)
        print("Summary:")
        passed = sum(1 for _, success in results if success)
        total = len(results)

        for text, success in results:
            status = "✓" if success else "✗"
            print(f"  {status} {text}")

        print(f"\nPassed: {passed}/{total}")
        return passed == total


def main():
    project_root = Path(__file__).parent.parent
    tester = VADCutoffTester(project_root)

    # Run tests
    test1_pass = tester.test_navigate_to_starbucks()
    test2_pass = tester.test_multi_word_commands()

    print("\n" + "="*70)
    print("FINAL RESULTS")
    print("="*70)
    print(f"  Navigate to Starbucks test: {'PASS' if test1_pass else 'FAIL'}")
    print(f"  Multi-word phrases test:    {'PASS' if test2_pass else 'FAIL'}")

    if test1_pass and test2_pass:
        print("\n✓ All tests passed")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
