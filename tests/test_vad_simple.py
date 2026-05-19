#!/usr/bin/env python3
"""
Simple test for VAD cutoff using whisper-cli only.
Tests that multi-word phrases are transcribed completely without cutoff.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audio_generator import AudioGenerator


def test_phrase(project_root: Path, text: str, filename: str):
    """Generate audio and transcribe with whisper-cli."""
    generator = AudioGenerator(
        piper_bin=str(Path.home() / ".local/bin/piper"),
        model_dir=str(project_root / "piper-data"),
        output_dir=str(project_root / "tests/audio/inputs")
    )

    print(f"\nTesting: '{text}'")
    print("-" * 60)

    # Generate audio
    wav_file = generator.generate(text, output_name=filename)
    print(f"Audio: {wav_file}")

    if not wav_file.exists():
        print("✗ Failed to generate audio")
        return False

    # Transcribe with whisper-cli
    whisper_model = project_root / "external/whisper.cpp/models/for-tests-ggml-base.bin"
    cmd = [
        str(project_root / "build/bin/whisper-cli"),
        "-m", str(whisper_model),
        "-f", str(wav_file),
        "--language", "en",
        "-nt"  # No timestamps
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout + result.stderr

        # Extract transcription (remove debug output)
        lines = output.split('\n')
        transcription = ""
        for line in lines:
            # Look for the actual transcription line (starts with text, not metadata)
            if line.strip() and not any(x in line for x in [
                'whisper_', 'print_', 'load_', 'ggml', '[', 'main:', 'system_info'
            ]):
                transcription = line.strip()
                break

        print(f"Transcription: '{transcription}'")

        # Check if complete phrase is in transcription
        if text.lower() in transcription.lower():
            print("✓ PASS - Complete phrase transcribed")
            return True
        else:
            print(f"✗ FAIL - Expected '{text}', got '{transcription}'")
            return False

    except subprocess.TimeoutExpired:
        print("✗ FAIL - Transcription timed out")
        return False
    except Exception as e:
        print(f"✗ FAIL - Error: {e}")
        return False


def main():
    project_root = Path(__file__).parent.parent

    print("="*70)
    print("VAD Cutoff Test - Multi-Word Phrases")
    print("="*70)
    print("\nThis test verifies that multi-word phrases falling in the")
    print("1200-1800ms window are transcribed completely without cutoff.")

    test_cases = [
        ("Navigate to Starbucks", "navigate_to_starbucks"),
        ("Make it warmer", "make_it_warmer"),
        ("Turn up the volume", "turn_up_volume"),
        ("What is the weather", "weather_query"),
    ]

    results = []
    for text, filename in test_cases:
        success = test_phrase(project_root, text, filename)
        results.append((text, success))

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for text, success in results:
        status = "✓" if success else "✗"
        print(f"{status} {text}")

    print(f"\nResult: {passed}/{total} passed")

    if passed == total:
        print("\n✓ All tests PASSED")
        return 0
    else:
        print("\n✗ Some tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
