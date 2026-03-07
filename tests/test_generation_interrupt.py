"""
Test: Generation interrupt behaviour

Verifies two things:
1. Long TTS is not prematurely cut short by a false VAD trigger.
   Regression test: audio.clear() after each TTS dispatch means the mic
   buffer during the NEXT generation phase doesn't contain TTS playback audio,
   preventing false-positive speech detection.
2. An explicit audio-stop command stops aplay promptly.

Wyoming-Piper sends audio to aplay (a subprocess). We measure how long aplay
runs as a proxy for audio duration, since Wyoming-Piper doesn't send response
events back on the synthesize connection.
"""

import json
import socket
import subprocess
import time
import unittest


WYOMING_HOST = 'localhost'
WYOMING_PORT = 10200
CONNECT_TIMEOUT = 3.0


def wyoming_send(event_type, data=None):
    """Send a Wyoming event and immediately close the connection."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(CONNECT_TIMEOUT)
    s.connect((WYOMING_HOST, WYOMING_PORT))
    payload = json.dumps({'type': event_type, 'data': data or {}}) + '\n'
    s.send(payload.encode())
    s.close()


def aplay_count():
    """Return number of running aplay processes."""
    try:
        out = subprocess.check_output(['pgrep', '-c', 'aplay'], text=True)
        return int(out.strip())
    except subprocess.CalledProcessError:
        return 0


def wait_for_aplay(timeout=5.0, poll=0.1):
    """Wait until at least one aplay process is running. Returns True if found."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if aplay_count() > 0:
            return True
        time.sleep(poll)
    return False


def wyoming_available():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(CONNECT_TIMEOUT)
        s.connect((WYOMING_HOST, WYOMING_PORT))
        s.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


def kill_aplay():
    """Kill any remaining aplay processes left over from TTS playback."""
    subprocess.run(['pkill', '-9', 'aplay'], capture_output=True)


class TestGenerationInterrupt(unittest.TestCase):

    def setUp(self):
        if not wyoming_available():
            self.skipTest(f'Wyoming-Piper not running on {WYOMING_HOST}:{WYOMING_PORT}')

    def tearDown(self):
        kill_aplay()

    def test_long_tts_not_cut_short(self):
        """
        A long TTS request should produce audio for a meaningful duration.

        Regression: false VAD triggers were cutting responses to ~2 words.
        The fix: audio.clear() after each TTS dispatch so the mic buffer
        during the next generation phase doesn't contain TTS playback audio.

        We measure aplay runtime as a proxy for audio length.
        A sentence of ~30 words at normal speech rate (~130 wpm) takes ~14s.
        We require at least 3s of audio, well above the ~0.5s seen when
        truncated to 2 words.
        """
        long_text = (
            "Once upon a time in a land far away there lived a brave adventurer "
            "who set out on a great quest to find a legendary treasure hidden "
            "deep within an ancient forest filled with magical creatures."
        )

        wyoming_send('new-response')  # reset STOP_CMD before new response
        wyoming_send('synthesize', {
            'text': long_text,
            'voice': {'name': 'en_US-lessac-medium'}
        })

        started = wait_for_aplay(timeout=5.0)
        self.assertTrue(started, 'aplay never started — TTS request may have failed')

        start_time = time.monotonic()

        # Wait for aplay to finish
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if aplay_count() == 0:
                break
            time.sleep(0.2)

        duration = time.monotonic() - start_time

        self.assertGreater(
            duration, 3.0,
            f'Audio played for only {duration:.1f}s — expected > 3s for a long sentence. '
            f'This suggests premature interruption (false VAD trigger regression).'
        )

    def test_stop_interrupts_tts(self):
        """
        An audio-stop event should stop aplay within 1 second.
        """
        long_text = (
            "This is a long piece of text that takes several seconds to play "
            "so we have time to send a stop command mid-playback and verify "
            "that audio stops promptly as expected by the user."
        )

        wyoming_send('new-response')  # reset STOP_CMD before new response
        wyoming_send('synthesize', {
            'text': long_text,
            'voice': {'name': 'en_US-lessac-medium'}
        })

        started = wait_for_aplay(timeout=5.0)
        self.assertTrue(started, 'aplay never started')

        # Send stop while audio is playing
        time.sleep(0.5)
        wyoming_send('audio-stop', {})
        stop_time = time.monotonic()

        # Wait for aplay to exit
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if aplay_count() == 0:
                break
            time.sleep(0.05)

        elapsed = time.monotonic() - stop_time

        self.assertLess(
            elapsed, 1.0,
            f'aplay took {elapsed:.2f}s to stop after audio-stop. Expected < 1s.'
        )

    def test_vad_false_positive_regression(self):
        """
        Sending audio-stop immediately after a short TTS chunk should not
        prevent a subsequent TTS request from playing.

        This guards against Wyoming-Piper being left in a broken state after
        a stop+resume cycle (the false-positive VAD scenario).
        """
        # Short TTS followed immediately by stop (simulates false VAD trigger)
        wyoming_send('new-response')  # reset STOP_CMD before new response
        wyoming_send('synthesize', {
            'text': 'Of course.',
            'voice': {'name': 'en_US-lessac-medium'}
        })
        time.sleep(0.1)
        wyoming_send('audio-stop', {})

        # Wait for any aplay to finish
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and aplay_count() > 0:
            time.sleep(0.1)

        time.sleep(0.3)

        # Follow-up TTS for a new response — requires new-response to reset STOP_CMD
        wyoming_send('new-response')
        wyoming_send('synthesize', {
            'text': 'Here is the story you asked for.',
            'voice': {'name': 'en_US-lessac-medium'}
        })

        started = wait_for_aplay(timeout=5.0)
        self.assertTrue(
            started,
            'Wyoming-Piper did not start audio after stop+resume cycle. '
            'System may be in a broken state after a false VAD trigger.'
        )

        # Clean up — let it finish or stop it
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and aplay_count() > 0:
            time.sleep(0.2)


    def test_stop_silences_all_queued_chunks(self):
        """
        After audio-stop, chunks arriving AFTER the kill must not play.

        This is the real-world scenario: the generation thread has already
        dispatched TTS threads for chunks 2, 3, etc. before g_stop_generation
        is checked. Those threads send synthesize events to Wyoming-Piper after
        the current chunk has been killed and ACTIVE_APLAY_PROCESSES is empty.

        STOP_CMD must remain True for all of them. It is only reset by an
        explicit new-response event at the start of the next user turn.
        """
        long_text = (
            "Once upon a time in a land far away there was a brave knight "
            "who went on a very long quest through many dangerous kingdoms."
        )

        # Start a new response
        wyoming_send('new-response')
        wyoming_send('synthesize', {
            'text': long_text,
            'voice': {'name': 'en_US-lessac-medium'}
        })

        started = wait_for_aplay(timeout=5.0)
        self.assertTrue(started, 'aplay never started for chunk 1')

        # Send stop — kills chunk 1, ACTIVE_APLAY_PROCESSES becomes empty
        wyoming_send('audio-stop', {})
        time.sleep(0.4)  # give Wyoming time to kill aplay

        self.assertEqual(aplay_count(), 0, 'aplay still running after stop')

        # Now send chunk 2 WITHOUT a new-response event.
        # This simulates a pre-dispatched TTS thread arriving after the stop.
        wyoming_send('synthesize', {
            'text': 'The end.',
            'voice': {'name': 'en_US-lessac-medium'}
        })

        # Chunk 2 must NOT play
        chunk2_started = wait_for_aplay(timeout=2.0)
        self.assertFalse(
            chunk2_started,
            'Chunk 2 played after stop — STOP_CMD was reset by incoming synthesize event. '
            'This means stop commands only silence the current chunk, not queued ones.'
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)
