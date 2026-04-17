#!/usr/bin/env python3
"""
True End-to-End Latency Test

Measures complete pipeline including TTS synthesis by:
1. Starting Wyoming-Piper in test mode (saves WAV instead of playing)
2. Running talk-llama-custom with test input
3. Waiting for TTS output WAV files to be written
4. Measuring wall time from start to TTS completion

Usage:
    python3 tests/end_to_end_latency.py [--npu]
"""

import subprocess
import time
import sys
import re
import os
from pathlib import Path
import shutil

PROJECT_ROOT = Path(__file__).parent.parent
TEST_AUDIO = PROJECT_ROOT / "tests/audio/inputs/make_it_warmer.wav"
BINARY = PROJECT_ROOT / "build/bin/talk-llama-custom"
TTS_OUTPUT_DIR = PROJECT_ROOT / "tests/audio/outputs/e2e_test"
WYOMING_LOG = "/tmp/wyoming-piper-e2e.log"

def kill_wyoming_piper():
    """Kill any running Wyoming-Piper processes"""
    try:
        subprocess.run(["pkill", "-9", "-f", "wyoming.piper"],
                      capture_output=True, timeout=2)
        time.sleep(1)
    except:
        pass

def start_wyoming_piper_test_mode():
    """Start Wyoming-Piper in test mode (saves WAV files instead of playing)"""
    print("Starting Wyoming-Piper in test mode...")

    # Clean output directory
    if TTS_OUTPUT_DIR.exists():
        shutil.rmtree(TTS_OUTPUT_DIR)
    TTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        os.path.expanduser("~/.local/bin/wyoming-piper-custom"),
        "--piper", os.path.expanduser("~/.local/bin/piper"),
        "--voice", "en_US-lessac-medium",
        "--data-dir", str(PROJECT_ROOT / "piper-data"),
        "--uri", "tcp://0.0.0.0:10200",
        "--test-mode",
        "--test-output-dir", str(TTS_OUTPUT_DIR)
    ]

    with open(WYOMING_LOG, 'w') as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)

    # Wait for startup
    time.sleep(3)

    # Verify it's running
    if proc.poll() is not None:
        print(f"ERROR: Wyoming-Piper failed to start. Check {WYOMING_LOG}")
        with open(WYOMING_LOG) as f:
            print(f.read())
        return None

    # Check port is listening
    try:
        result = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=2)
        if ":10200" not in result.stdout:
            print("ERROR: Port 10200 not listening")
            proc.kill()
            return None
    except:
        pass

    print(f"✓ Wyoming-Piper started in test mode (PID: {proc.pid})")
    print(f"  Output directory: {TTS_OUTPUT_DIR}")
    print(f"  Log file: {WYOMING_LOG}")
    return proc

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

def count_tts_output_files():
    """Count WAV files in TTS output directory"""
    if not TTS_OUTPUT_DIR.exists():
        return 0
    return len(list(TTS_OUTPUT_DIR.glob("*.wav")))

def run_end_to_end_test(use_npu=False):
    """Run true end-to-end test with Wyoming-Piper test mode"""

    print("=" * 70)
    print("TRUE END-TO-END LATENCY TEST")
    print("=" * 70)
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

    # Kill any existing Wyoming-Piper
    kill_wyoming_piper()

    # Start Wyoming-Piper in test mode
    wyoming_proc = start_wyoming_piper_test_mode()
    if not wyoming_proc:
        return 1

    try:
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
            "-c", "-1"
        ] + whisper_args

        # Set environment
        env = os.environ.copy()
        if use_npu:
            env['XLNX_VART_FIRMWARE'] = '/opt/xilinx/overlaybins/xclbins'
            env['HSA_OVERRIDE_GFX_VERSION'] = '11.0.3'

        print("Running assistant...")
        print()

        # Start timing
        start_time = time.time()
        initial_files = count_tts_output_files()

        # Run assistant (will exit after LLM generation in test mode)
        result = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=PROJECT_ROOT, env=env, timeout=60)

        # Wait for TTS output files to be written
        # Wyoming-Piper writes files after synthesis completes
        max_wait = 30  # seconds
        files_written = False
        for i in range(max_wait * 10):  # Check every 100ms
            current_files = count_tts_output_files()
            if current_files > initial_files:
                # Wait a bit more to ensure all files are written
                time.sleep(0.5)
                files_written = True
                break
            time.sleep(0.1)

        end_time = time.time()
        total_ms = (end_time - start_time) * 1000

        # Parse internal latency metrics
        output = result.stdout + result.stderr
        metrics = parse_latency_from_output(output)

        # Extract transcription
        transcription = None
        for line in output.split('\n'):
            if 'after transcribe, result:' in line:
                match = re.search(r"result: '([^']*)'", line)
                if match:
                    transcription = match.group(1)

        # Count TTS output files
        final_file_count = count_tts_output_files()
        tts_files = list(TTS_OUTPUT_DIR.glob("*.wav"))

        # Calculate TTS synthesis time (end-to-end minus whisper and LLM)
        tts_synthesis_ms = total_ms - metrics.get('vad_to_llm_ms', 0)

        # Print results
        print("=" * 70)
        print("RESULTS")
        print("=" * 70)
        print()
        print(f"Transcription: '{transcription}'")
        print()
        print("LATENCY BREAKDOWN:")
        print("-" * 70)
        print(f"  Whisper transcription:  {metrics.get('whisper_ms', 'N/A'):>6} ms")
        print(f"  LLM generation:         {metrics.get('llm_ms', 'N/A'):>6} ms")
        print(f"  VAD->LLM total:         {metrics.get('vad_to_llm_ms', 'N/A'):>6} ms")
        print(f"  TTS synthesis:          {tts_synthesis_ms:>6.0f} ms  (wall time - VAD->LLM)")
        print("-" * 70)
        print(f"  TOTAL END-TO-END:       {total_ms:>6.0f} ms")
        print()

        print("TTS OUTPUT FILES:")
        print(f"  Files written: {final_file_count}")
        if tts_files:
            for f in sorted(tts_files):
                size_kb = f.stat().st_size / 1024
                print(f"    - {f.name} ({size_kb:.1f} KB)")
        print()

        if not files_written:
            print("⚠ WARNING: No TTS files were written during test")
            print(f"   Check Wyoming log: {WYOMING_LOG}")

        return 0

    finally:
        # Cleanup
        print("Stopping Wyoming-Piper...")
        wyoming_proc.terminate()
        try:
            wyoming_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            wyoming_proc.kill()
        print("✓ Cleanup complete")

if __name__ == '__main__':
    use_npu = '--npu' in sys.argv
    sys.exit(run_end_to_end_test(use_npu))
