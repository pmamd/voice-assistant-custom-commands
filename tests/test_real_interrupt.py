#!/usr/bin/env python3
"""
Real end-to-end interrupt test.
Tests stop command during actual LLM generation and TTS playback.
"""

import asyncio
import subprocess
import time
import signal
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from audio_generator import AudioGenerator

class RealInterruptTester:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.talk_llama_bin = project_root / "build/bin/talk-llama-custom"
        self.whisper_model = project_root / "whisper.cpp/models/ggml-tiny.en.bin"
        self.llama_model = project_root / "models/llama-2-7b-chat.Q4_K_M.gguf"
        
        self.generator = AudioGenerator(
            piper_bin="/home/paul/.local/bin/piper",
            model_dir=str(project_root / "external/piper-voices"),
            output_dir=str(project_root / "tests/audio/inputs")
        )
    
    async def test_stop_during_long_response(self):
        """Test stop command during actual LLM generation."""
        print("\n" + "="*60)
        print("REAL INTERRUPT TEST")
        print("="*60)
        
        # Generate audio files
        print("\n1. Generating test audio files...")
        
        # Use a prompt that WILL generate a long response
        # Ask for enumeration which forces the model to generate many tokens
        long_prompt = "Count from one to one hundred and say something about each number"
        long_audio = self.generator.generate(long_prompt, "long_request")
        print(f"   Long request audio: {long_audio}")
        
        stop_audio = self.generator.generate("stop", "stop_request")
        print(f"   Stop audio: {stop_audio}")
        
        # Start talk-llama in background
        print("\n2. Starting talk-llama process...")
        
        # Use a FIFO for continuous input
        fifo_path = "/tmp/talk_llama_input.fifo"
        if os.path.exists(fifo_path):
            os.remove(fifo_path)
        os.mkfifo(fifo_path)
        
        try:
            # Start talk-llama reading from FIFO
            proc = subprocess.Popen(
                [
                    str(self.talk_llama_bin),
                    "-ml", str(self.llama_model),
                    "-mw", str(self.whisper_model),
                    "--xtts-url", "http://localhost:10200/",
                    "--xtts-voice", "en_US-lessac-medium",
                    "--temp", "0.7",
                    "-c", "-1",  # Use default capture device
                    "--test-input", fifo_path  # Read from FIFO
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            print("   talk-llama started (PID: {})".format(proc.pid))
            
            # Wait for initialization
            print("\n3. Waiting for talk-llama initialization...")
            await asyncio.sleep(10)
            
            # Feed the long request
            print("\n4. Feeding long request audio...")
            test_start = time.time()
            
            # Open FIFO and write audio
            with open(fifo_path, 'wb') as fifo:
                with open(long_audio, 'rb') as audio:
                    fifo.write(audio.read())
            
            print("   Audio sent, LLM should start generating...")
            
            # Monitor output to detect when speech starts
            print("\n5. Monitoring for LLM response...")
            response_started = False
            response_lines = []
            
            # Read output for a few seconds to see response start
            for _ in range(30):  # Monitor for 3 seconds
                try:
                    line = proc.stdout.readline()
                    if line:
                        response_lines.append(line.strip())
                        if "Georgi:" in line or any(word in line.lower() for word in ["one", "two", "three", "count"]):
                            response_started = True
                            print(f"   Response started: {line.strip()[:80]}...")
                            break
                except:
                    pass
                await asyncio.sleep(0.1)
            
            if not response_started:
                print("   WARNING: Couldn't detect response start")
                print(f"   Last 10 lines: {response_lines[-10:]}")
            
            # Wait a bit for TTS to start playing
            print("\n6. Waiting for TTS playback to start...")
            await asyncio.sleep(2)
            
            # Send stop command
            print("\n7. Sending STOP command...")
            stop_time = time.time()
            
            with open(fifo_path, 'wb') as fifo:
                with open(stop_audio, 'rb') as audio:
                    fifo.write(audio.read())
            
            print("   Stop audio sent at {:.2f}s".format(stop_time - test_start))
            
            # Monitor for stop confirmation
            print("\n8. Monitoring for stop execution...")
            stop_confirmed = False
            
            for _ in range(20):  # Monitor for 2 seconds
                try:
                    line = proc.stdout.readline()
                    if line:
                        response_lines.append(line.strip())
                        if "Fast Path Tool: stop_speaking" in line or "Tool] stop_speaking" in line:
                            stop_confirmed = True
                            stop_confirmed_time = time.time()
                            print(f"   Stop confirmed at {stop_confirmed_time - test_start:.2f}s: {line.strip()}")
                            break
                except:
                    pass
                await asyncio.sleep(0.1)
            
            # Wait a bit to see if generation continues
            await asyncio.sleep(1)
            
            final_time = time.time()
            total_duration = final_time - test_start
            
            # Kill talk-llama
            print("\n9. Stopping talk-llama...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except:
                proc.kill()
            
            # Analysis
            print("\n" + "="*60)
            print("TEST RESULTS")
            print("="*60)
            
            print(f"\nTiming:")
            print(f"  Total test duration: {total_duration:.2f}s")
            print(f"  Stop sent at: {stop_time - test_start:.2f}s")
            if stop_confirmed:
                print(f"  Stop confirmed at: {stop_confirmed_time - test_start:.2f}s")
            
            print(f"\nResponse Detection:")
            print(f"  Response started: {response_started}")
            print(f"  Stop confirmed: {stop_confirmed}")
            
            print(f"\nOutput lines captured: {len(response_lines)}")
            print(f"\nLast 20 lines:")
            for line in response_lines[-20:]:
                print(f"  {line[:100]}")
            
            # Success criteria:
            # 1. Response should have started
            # 2. Stop should have been confirmed
            # 3. Total duration should be much less than time to count to 100
            #    (Counting to 100 would take 2+ minutes, we should stop in <10s)
            
            if response_started and stop_confirmed and total_duration < 15:
                print("\n✓ TEST PASSED")
                print(f"  Stopped response in {total_duration:.2f}s (would have been 120+ seconds)")
                return True
            else:
                print("\n✗ TEST FAILED")
                if not response_started:
                    print("  Response didn't start")
                if not stop_confirmed:
                    print("  Stop wasn't confirmed")
                if total_duration >= 15:
                    print(f"  Took too long: {total_duration:.2f}s")
                return False
            
        finally:
            # Cleanup
            if os.path.exists(fifo_path):
                os.remove(fifo_path)

async def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    print(f"Project root: {project_root}")

    tester = RealInterruptTester(project_root)
    success = await tester.test_stop_during_long_response()

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))


# ---------------------------------------------------------------------------
# Wyoming-protocol level interrupt tests (unittest-based)
# These test Wyoming-Piper's stop mechanics directly without the binary.
# Run with: python3 -m unittest tests/test_real_interrupt.py -v
# ---------------------------------------------------------------------------

import json
import socket
import unittest

_WYOMING_HOST = 'localhost'
_WYOMING_PORT = 10200
_CONNECT_TIMEOUT = 3.0


def _wyoming_send(event_type, data=None):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(_CONNECT_TIMEOUT)
    s.connect((_WYOMING_HOST, _WYOMING_PORT))
    s.send((json.dumps({'type': event_type, 'data': data or {}}) + '\n').encode())
    s.close()


def _aplay_count():
    try:
        out = subprocess.check_output(['pgrep', '-c', 'aplay'], text=True)
        return int(out.strip())
    except subprocess.CalledProcessError:
        return 0


def _wait_for_aplay(timeout=5.0, poll=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _aplay_count() > 0:
            return True
        time.sleep(poll)
    return False


def _wyoming_available():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(_CONNECT_TIMEOUT)
        s.connect((_WYOMING_HOST, _WYOMING_PORT))
        s.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


class TestWyomingStopMechanics(unittest.TestCase):
    """
    Tests for Wyoming-Piper's stop command handling.

    Covers regressions from the background-generation threading refactor:
    - STOP_CMD must remain set for all queued chunks, not just the current one
    - Chunks that passed the STOP_CMD check while it was False must be blocked
      by the re-check inside the aplay lock
    - STOP_CMD is only reset by an explicit new-response event
    """

    def setUp(self):
        if not _wyoming_available():
            self.skipTest(f'Wyoming-Piper not running on {_WYOMING_HOST}:{_WYOMING_PORT}')

    def tearDown(self):
        subprocess.run(['pkill', '-9', 'aplay'], capture_output=True)

    def test_long_tts_plays_to_completion(self):
        """A long TTS request should produce audio for a meaningful duration."""
        long_text = (
            "Once upon a time in a land far away there lived a brave adventurer "
            "who set out on a great quest to find a legendary treasure hidden "
            "deep within an ancient forest filled with magical creatures."
        )
        _wyoming_send('new-response')
        _wyoming_send('synthesize', {'text': long_text, 'voice': {'name': 'en_US-lessac-medium'}})

        started = _wait_for_aplay(timeout=5.0)
        self.assertTrue(started, 'aplay never started')

        start_time = time.monotonic()
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if _aplay_count() == 0:
                break
            time.sleep(0.2)

        duration = time.monotonic() - start_time
        self.assertGreater(duration, 3.0,
            f'Audio played for only {duration:.1f}s — expected > 3s. '
            f'Suggests premature interruption.')

    def test_audio_stop_kills_playback_quickly(self):
        """An audio-stop event should stop aplay within 1 second."""
        long_text = (
            "This is a long piece of text that takes several seconds to play "
            "so we have time to send a stop command mid-playback."
        )
        _wyoming_send('new-response')
        _wyoming_send('synthesize', {'text': long_text, 'voice': {'name': 'en_US-lessac-medium'}})

        self.assertTrue(_wait_for_aplay(timeout=5.0), 'aplay never started')
        time.sleep(0.5)
        _wyoming_send('audio-stop', {})
        stop_time = time.monotonic()

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if _aplay_count() == 0:
                break
            time.sleep(0.05)

        elapsed = time.monotonic() - stop_time
        self.assertLess(elapsed, 1.0,
            f'aplay took {elapsed:.2f}s to stop after audio-stop. Expected < 1s.')

    def test_stop_silences_all_queued_chunks(self):
        """
        Chunks arriving after audio-stop must not play.

        Regression: Wyoming-Piper was resetting STOP_CMD on every synthesize
        event, so pre-dispatched chunks would reset the flag and play anyway.
        The fix: re-check STOP_CMD inside the aplay lock.
        """
        long_text = (
            "Once upon a time in a land far away there was a brave knight "
            "who went on a very long quest through many dangerous kingdoms."
        )
        _wyoming_send('new-response')
        _wyoming_send('synthesize', {'text': long_text, 'voice': {'name': 'en_US-lessac-medium'}})

        self.assertTrue(_wait_for_aplay(timeout=5.0), 'aplay never started for chunk 1')

        _wyoming_send('audio-stop', {})
        time.sleep(0.4)
        self.assertEqual(_aplay_count(), 0, 'aplay still running after stop')

        # Simulate a pre-dispatched chunk arriving after the stop (no new-response)
        _wyoming_send('synthesize', {'text': 'The end.', 'voice': {'name': 'en_US-lessac-medium'}})
        self.assertFalse(_wait_for_aplay(timeout=2.0),
            'Queued chunk played after stop — STOP_CMD was reset by synthesize event.')

    def test_new_response_allows_playback_after_stop(self):
        """
        A new-response event must re-enable playback after a stop.
        Wyoming-Piper should accept the next user turn's TTS normally.
        """
        _wyoming_send('new-response')
        _wyoming_send('synthesize', {'text': 'Of course.', 'voice': {'name': 'en_US-lessac-medium'}})
        time.sleep(0.1)
        _wyoming_send('audio-stop', {})

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and _aplay_count() > 0:
            time.sleep(0.1)
        time.sleep(0.3)

        # New user turn — new-response must reset stop state
        _wyoming_send('new-response')
        _wyoming_send('synthesize', {'text': 'Here is the story you asked for.',
                                      'voice': {'name': 'en_US-lessac-medium'}})
        self.assertTrue(_wait_for_aplay(timeout=5.0),
            'Wyoming-Piper did not start audio after new-response. '
            'Stop state was not cleared.')
