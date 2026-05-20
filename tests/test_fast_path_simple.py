#!/usr/bin/env python3
"""
Simple fast-path tool test.
Generates "stop" audio and feeds it to voice-assistant with --test-input.
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audio_generator import AudioGenerator

def test_stop_fast_path():
    """Test that 'stop' command triggers fast path tool."""
    project_root = Path(__file__).parent.parent

    print("=" * 60)
    print("FAST PATH TOOL TEST - STOP COMMAND")
    print("=" * 60)
    print()

    # Initialize audio generator
    generator = AudioGenerator(
        piper_bin="/home/paul/.local/bin/piper",
        model_dir=str(project_root / "piper-data"),
        output_dir=str(project_root / "tests/audio/inputs")
    )

    # Generate stop command audio
    print("1. Generating 'stop' audio...")
    stop_audio = generator.generate("stop", output_name="stop_command")
    print(f"   Audio file: {stop_audio}")
    print()

    # Run voice-assistant with test input
    print("2. Running voice-assistant with --test-input...")
    talk_llama_bin = project_root / "build/bin/voice-assistant"
    whisper_model = project_root / "external/whisper.cpp/models/ggml-base.en.bin"

    cmd = [
        str(talk_llama_bin),
        "--llama-url", "http://127.0.0.1:8080",
        "-mw", str(whisper_model),
        "--xtts-url", "http://localhost:10200/",
        "--xtts-voice", "en_US-lessac-medium",
        "--temp", "0.5",
        "-n", "300",
        "--allow-newline",
        "-p", "Driver",
        "-c", "-1",
        "--test-input", str(stop_audio)
    ]

    print(f"   Command: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=project_root
        )

        output = result.stdout + result.stderr

        print("3. Checking output...")
        print()

        # Check for fast path execution
        if "[Fast Path Tool: stop_speaking]" in output:
            print("   ✓ SUCCESS: Fast path tool was triggered!")
            print()

            # Show the relevant section
            for line in output.split('\n'):
                if "Fast Path" in line or "Driver:" in line or "transcribed" in line.lower():
                    print(f"   {line}")

            print()
            print("=" * 60)
            print("TEST PASSED - Fast path tool execution confirmed")
            print("=" * 60)
            return 0
        else:
            print("   ✗ FAILED: Fast path tool was NOT triggered")
            print()
            print("   Output (last 50 lines):")
            for line in output.split('\n')[-50:]:
                print(f"   {line}")

            print()
            print("=" * 60)
            print("TEST FAILED - No fast path execution detected")
            print("=" * 60)
            return 1

    except subprocess.TimeoutExpired:
        print("   ✗ TIMEOUT: voice-assistant did not complete within 30s")
        return 1
    except Exception as e:
        print(f"   ✗ ERROR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(test_stop_fast_path())
