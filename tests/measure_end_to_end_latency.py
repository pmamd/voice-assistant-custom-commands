#!/usr/bin/env python3
"""
End-to-End Latency Measurement for Voice Assistant

Plays a test audio file and measures the complete pipeline:
1. Audio playback start
2. Whisper transcription time (from logs)
3. LLM generation time (from logs)
4. TTS synthesis + playback time
5. Total end-to-end latency

Usage:
    python3 tests/measure_end_to_end_latency.py [--npu]
"""

import subprocess
import time
import sys
import re
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TEST_AUDIO = PROJECT_ROOT / "tests/audio/inputs/make_it_warmer.wav"
BINARY = PROJECT_ROOT / "build/bin/talk-llama-custom"

# Get audio duration
def get_audio_duration(wav_file):
    """Get duration of WAV file in seconds"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(wav_file)],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())

def parse_latency_from_output(output):
    """Extract latency metrics from assistant output"""
    metrics = {}

    # Extract [LATENCY] lines
    for line in output.split('\n'):
        if '[LATENCY]' in line:
            if 'Whisper:' in line:
                match = re.search(r'Whisper: (\d+)ms', line)
                if match:
                    metrics['whisper_ms'] = int(match.group(1))
            elif 'LLM generation:' in line:
                match = re.search(r'LLM generation: (\d+)ms', line)
                if match:
                    metrics['llm_ms'] = int(match.group(1))
            elif 'TOTAL' in line:
                match = re.search(r'TOTAL.*: (\d+)ms', line)
                if match:
                    metrics['vad_to_llm_ms'] = int(match.group(1))

    return metrics

def run_end_to_end_test(use_npu=False):
    """Run end-to-end test and measure latencies"""

    print("=" * 60)
    print("END-TO-END LATENCY MEASUREMENT")
    print("=" * 60)
    print(f"Test audio: {TEST_AUDIO}")
    print(f"NPU: {'ENABLED' if use_npu else 'DISABLED'}")
    print()

    # Check test audio exists
    if not TEST_AUDIO.exists():
        print(f"ERROR: Test audio not found: {TEST_AUDIO}")
        return 1

    audio_duration = get_audio_duration(TEST_AUDIO)
    print(f"Audio duration: {audio_duration:.2f}s")
    print()

    # Build command
    model = "./whisper.cpp/models/ggml-base.bin" if use_npu else "./whisper.cpp/models/ggml-base.en.bin"
    whisper_args = ["--no-gpu"] if use_npu else []

    cmd = [
        str(BINARY),
        "--test-input", str(TEST_AUDIO),
        "--llama-url", "http://localhost:8080",
        "-mw", model,
        "--xtts-url", "http://localhost:10200/",
        "--xtts-voice", "en_US-lessac-medium",
        "--temp", "0.5",
        "-vth", "1.2",
        "-c", "-1",
        "--debug"
    ] + whisper_args

    # Set environment
    env = os.environ.copy()
    if use_npu:
        env['XLNX_VART_FIRMWARE'] = '/opt/xilinx/overlaybins/xclbins'
        env['HSA_OVERRIDE_GFX_VERSION'] = '11.0.3'

    print("Running assistant...")
    print()

    # Run and capture output
    start_time = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True,
                          cwd=PROJECT_ROOT, env=env, timeout=30)
    end_time = time.time()

    total_wall_time = (end_time - start_time) * 1000  # ms

    # Parse output
    output = result.stdout + result.stderr
    metrics = parse_latency_from_output(output)

    # Extract transcription
    transcription = None
    for line in output.split('\n'):
        if 'after transcribe, result:' in line:
            match = re.search(r"result: '([^']*)'", line)
            if match:
                transcription = match.group(1)

    # Print results
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print()
    print(f"Transcription: '{transcription}'")
    print()
    print("LATENCY BREAKDOWN:")
    print("-" * 60)
    print(f"  Whisper transcription:  {metrics.get('whisper_ms', 'N/A'):>6} ms")
    print(f"  LLM generation:         {metrics.get('llm_ms', 'N/A'):>6} ms")
    print(f"  VAD->LLM total:         {metrics.get('vad_to_llm_ms', 'N/A'):>6} ms")
    print("-" * 60)
    print(f"  Wall clock time:        {total_wall_time:>6.0f} ms")
    print()

    # Note about test mode
    print("NOTE: Running in --test-input mode which:")
    print("  - Bypasses real-time VAD (loads audio directly)")
    print("  - Exits immediately after LLM request (no TTS)")
    print("  - For full end-to-end, need to run live without --test-input")
    print()

    return 0

if __name__ == '__main__':
    use_npu = '--npu' in sys.argv
    sys.exit(run_end_to_end_test(use_npu))
