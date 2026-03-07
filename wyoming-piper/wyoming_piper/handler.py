"""Event handler for clients of the server."""
import argparse
import json
import logging
import math
import os
import shutil
import signal
import wave
import time
from pathlib import Path
from typing import Any, Dict, Optional

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.error import Error
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler
from wyoming.tts import Synthesize

from .process import PiperProcessManager

# To add direct call of aplay
import wyoming
import asyncio

_LOGGER = logging.getLogger(__name__)

# Variable to flag if the stop command word has been received
STOP_CMD = False
# List to track all active aplay processes
ACTIVE_APLAY_PROCESSES = []

class PiperEventHandler(AsyncEventHandler):
    def __init__(
        self,
        wyoming_info: Info,
        cli_args: argparse.Namespace,
        process_manager: PiperProcessManager,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.cli_args = cli_args
        self.wyoming_info_event = wyoming_info.event()
        self.process_manager = process_manager
        self.test_output_counter = 0  # Counter for test output files

    async def handle_event(self, event: Event) -> bool:
        global STOP_CMD, ACTIVE_APLAY_PROCESSES

        # Handle service discovery
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            _LOGGER.debug("Sent info")
            return True

        # Handle new-response event: talk-llama signals start of a new user response.
        # This is the only place STOP_CMD is reset to False.
        if event.type == "new-response":
            _LOGGER.debug("Received new-response event - resetting STOP_CMD")
            STOP_CMD = False
            return True

        # Handle AudioStop event (standard Wyoming protocol)
        if AudioStop.is_type(event.type):
            _LOGGER.debug("Received AudioStop event - killing all active aplay processes")
            STOP_CMD = True

            # Kill all currently playing audio immediately
            for aplay_proc in ACTIVE_APLAY_PROCESSES[:]:
                try:
                    if aplay_proc.proc.returncode is None:
                        _LOGGER.debug(f"Killing aplay process {aplay_proc.proc.pid}")
                        aplay_proc.proc.kill()  # Use kill() instead of terminate() for immediate stop
                        ACTIVE_APLAY_PROCESSES.remove(aplay_proc)
                except Exception as e:
                    _LOGGER.warning(f"Error killing aplay: {e}")

            # Acknowledge the stop
            await self.write_event(AudioStop().event())
            return True

        # Handle custom audio-pause event
        if event.type == "audio-pause":
            _LOGGER.debug("Received audio-pause event - pausing all active aplay processes")

            for aplay_proc in ACTIVE_APLAY_PROCESSES[:]:
                try:
                    if aplay_proc.proc.returncode is None and not aplay_proc.paused:
                        _LOGGER.debug(f"Pausing aplay process {aplay_proc.proc.pid}")
                        aplay_proc.proc.send_signal(signal.SIGSTOP)
                        aplay_proc.paused = True
                except Exception as e:
                    _LOGGER.warning(f"Error pausing aplay: {e}")

            return True

        # Handle custom audio-resume event
        if event.type == "audio-resume":
            _LOGGER.debug("Received audio-resume event - resuming all paused aplay processes")

            for aplay_proc in ACTIVE_APLAY_PROCESSES[:]:
                try:
                    if aplay_proc.proc.returncode is None and hasattr(aplay_proc, 'paused') and aplay_proc.paused:
                        _LOGGER.debug(f"Resuming aplay process {aplay_proc.proc.pid}")
                        aplay_proc.proc.send_signal(signal.SIGCONT)
                        aplay_proc.paused = False
                except Exception as e:
                    _LOGGER.warning(f"Error resuming aplay: {e}")

            return True

        # Handle TTS synthesis
        if not Synthesize.is_type(event.type):
            _LOGGER.warning("Unexpected event: %s", event)
            return True

        # Process synthesize event normally (removed hardcoded stop detection)
        try:
            return await self._handle_event(event)
        except Exception as err:
            await self.write_event(
                Error(text=str(err), code=err.__class__.__name__).event()
            )
            raise err

    async def _handle_event(self, event: Event) -> bool:
        global STOP_CMD, ACTIVE_APLAY_PROCESSES
        # STOP_CMD is intentionally NOT reset here.
        # It is only reset when talk-llama sends an explicit "new-response" event
        # at the start of each generation, before any TTS chunks are dispatched.
        # This ensures that stop commands silence ALL queued chunks, not just
        # the one currently playing.

        synthesize = Synthesize.from_event(event)
        _LOGGER.debug(synthesize)

        raw_text = synthesize.text

        # Join multiple lines
        text = " ".join(raw_text.strip().splitlines())

        if self.cli_args.auto_punctuation and text:
            # Add automatic punctuation (important for some voices)
            has_punctuation = False
            for punc_char in self.cli_args.auto_punctuation:
                if text[-1] == punc_char:
                    has_punctuation = True
                    break

            if not has_punctuation:
                text = text + self.cli_args.auto_punctuation[0]

        async with self.process_manager.processes_lock:
            _LOGGER.debug("synthesize: raw_text=%s, text='%s'", raw_text, text)
            voice_name: Optional[str] = None
            voice_speaker: Optional[str] = None
            if synthesize.voice is not None:
                voice_name = synthesize.voice.name
                voice_speaker = synthesize.voice.speaker

            piper_proc = await self.process_manager.get_process(voice_name=voice_name)

            assert piper_proc.proc.stdin is not None
            assert piper_proc.proc.stderr is not None

            # Send plain text to stdin (piper-tts 1.4.1 doesn't support --json-input)
            # Speaker is passed as command-line arg in process.py
            _LOGGER.debug("Sending text to Piper: %s", text)
            piper_proc.proc.stdin.write((text + "\n").encode("utf-8"))
            await piper_proc.proc.stdin.drain()

            # Piper outputs multiple log lines to stderr, ending with "Wrote /path/to/file.wav"
            # Read lines until we find the one with the file path
            output_path = None
            max_lines = 20  # Safety limit to prevent infinite loop
            for _ in range(max_lines):
                output_line = (await piper_proc.proc.stderr.readline()).decode().strip()
                _LOGGER.debug("Piper output: %s", output_line)

                # Extract path from "INFO:__main__:Wrote /path/to/file.wav" or "Wrote /path/to/file.wav"
                if "Wrote " in output_line:
                    output_path = output_line.split("Wrote ", 1)[1]
                    break

            if not output_path:
                raise RuntimeError("Failed to get output file path from Piper")

            _LOGGER.debug("Audio file path: %s", output_path)

        # Check if test mode is enabled
        test_mode = hasattr(self.cli_args, 'test_mode') and self.cli_args.test_mode
        test_output_dir = getattr(self.cli_args, 'test_output_dir', None)

        if test_mode and test_output_dir:
            # Test mode: copy file to test output directory instead of playing
            test_output_dir_path = Path(test_output_dir)
            test_output_dir_path.mkdir(parents=True, exist_ok=True)

            # Generate output filename with timestamp and counter
            timestamp = int(time.time())
            self.test_output_counter += 1
            test_output_path = test_output_dir_path / f"output_{timestamp}_{self.test_output_counter}.wav"

            shutil.copy(output_path, test_output_path)
            _LOGGER.info(f"Test mode: saved audio to {test_output_path}")

            # Also create a symlink to the latest output for easy access
            latest_link = test_output_dir_path / "output.wav"
            if latest_link.exists() or latest_link.is_symlink():
                latest_link.unlink()
            latest_link.symlink_to(test_output_path.name)

        else:
            # Normal mode: run aplay
            # Check if stop was requested before starting playback
            if STOP_CMD:
                _LOGGER.debug("Skipping aplay - stop command received")
            else:
                async with self.process_manager.processes_lock:
                    # Re-check STOP_CMD inside the lock.
                    # A chunk may have passed the check above while STOP_CMD was
                    # still False, then waited for the lock while the previous chunk
                    # was killed. Without this re-check it would start playing anyway.
                    if STOP_CMD:
                        _LOGGER.debug("Skipping aplay - stop command received (inside lock)")
                        return True
                    _LOGGER.debug("Running aplay on " + output_path)
                    aplay_proc = await self.process_manager.get_aplay_process(output_path)

                    # Track this process so stop command can kill it
                    # Initialize paused state for pause/resume functionality
                    aplay_proc.paused = False
                    ACTIVE_APLAY_PROCESSES.append(aplay_proc)

                    try:
                        await aplay_proc.proc.wait()
                    finally:
                        # Remove from active list when done
                        if aplay_proc in ACTIVE_APLAY_PROCESSES:
                            ACTIVE_APLAY_PROCESSES.remove(aplay_proc)

        _LOGGER.debug("Completed request")

        os.unlink(output_path)

        return True
