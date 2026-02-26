"""Event handler for clients of the server."""
import argparse
import json
import logging
import math
import os
import shutil
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
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            _LOGGER.debug("Sent info")
            return True

        if not Synthesize.is_type(event.type):
            _LOGGER.warning("Unexpected event: %s", event)
            return True

        # Hack to make stop work
        synthesize = Synthesize.from_event(event)
        raw_text = synthesize.text
        if ("stop" in raw_text.lower()) and (len(raw_text) < 10):
            _LOGGER.debug("Saw STOP event - killing all active aplay processes")
            global STOP_CMD, ACTIVE_APLAY_PROCESSES
            STOP_CMD = True

            # Kill all currently playing audio
            for aplay_proc in ACTIVE_APLAY_PROCESSES[:]:  # Copy list to avoid modification during iteration
                try:
                    if aplay_proc.proc.returncode is None:  # Process still running
                        _LOGGER.debug(f"Terminating aplay process {aplay_proc.proc.pid}")
                        aplay_proc.proc.terminate()
                        ACTIVE_APLAY_PROCESSES.remove(aplay_proc)
                except Exception as e:
                    _LOGGER.warning(f"Error terminating aplay: {e}")

            return True

        try:
            return await self._handle_event(event)
        except Exception as err:
            await self.write_event(
                Error(text=str(err), code=err.__class__.__name__).event()
            )
            raise err

    async def _handle_event(self, event: Event) -> bool:
        # Clear at the start of a new synthesize event
        STOP_CMD = False

        # begin Debug
        _LOGGER.debug("Debug")
        #_LOGGER.debug(event)

        event_dict: Dict[str, Any] = event.to_dict()
        event_dict[wyoming.event._VERSION] = wyoming.event._VERSION_NUMBER

        data_dict = event_dict.pop(wyoming.event._DATA, None)
        data_bytes: Optional[bytes] = None
        if data_dict:
            data_bytes = json.dumps(data_dict, ensure_ascii=False).encode("utf-8")
            event_dict[wyoming.event._DATA_LENGTH] = len(data_bytes)

        if event.payload:
            event_dict[wyoming.event._PAYLOAD_LENGTH] = len(event.payload)

        json_line = json.dumps(event_dict, ensure_ascii=False)

        _LOGGER.debug(json_line.encode())
        _LOGGER.debug(wyoming.event._NEWLINE)
        if data_bytes:
            _LOGGER.debug(data_bytes)

        if event.payload:
            _LOGGER.debug(event.payload)

        # end Debug
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
            # Log queue depth before processing
            global ACTIVE_APLAY_PROCESSES
            queue_depth = len(ACTIVE_APLAY_PROCESSES)
            _LOGGER.info(f"📊 Queue depth BEFORE synthesis: {queue_depth} chunks currently playing")
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

            # Piper outputs "INFO:__main__:Wrote /path/to/file.wav" to stderr
            # Extract just the path
            output_line = (await piper_proc.proc.stderr.readline()).decode().strip()
            _LOGGER.debug("Piper output: %s", output_line)

            # Extract path from "INFO:__main__:Wrote /path/to/file.wav"
            if "Wrote " in output_line:
                output_path = output_line.split("Wrote ", 1)[1]
            else:
                output_path = output_line  # Fallback to full line

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
            async with self.process_manager.processes_lock:
                _LOGGER.debug("Running aplay on " + output_path)
                aplay_proc = await self.process_manager.get_aplay_process(output_path)

                # Track this process so stop command can kill it
                ACTIVE_APLAY_PROCESSES.append(aplay_proc)
                queue_depth_after = len(ACTIVE_APLAY_PROCESSES)
                _LOGGER.info(f"🎵 Queue depth AFTER adding to playback: {queue_depth_after} chunks now playing")

                try:
                    await aplay_proc.proc.wait()
                finally:
                    # Remove from active list when done
                    if aplay_proc in ACTIVE_APLAY_PROCESSES:
                        ACTIVE_APLAY_PROCESSES.remove(aplay_proc)
                        remaining = len(ACTIVE_APLAY_PROCESSES)
                        _LOGGER.info(f"✅ Playback finished. Queue depth now: {remaining} chunks remaining")

        _LOGGER.debug("Completed request")

        os.unlink(output_path)

        return True
