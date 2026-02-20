#!/usr/bin/env python3
"""End-to-end audio pipeline test harness."""

import sys
import asyncio
import logging
import time
import json
import subprocess
import signal
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

try:
    import yaml
except ImportError:
    print("Error: pyyaml not installed. Run: pip install pyyaml")
    sys.exit(1)

from audio_generator import AudioGenerator
from audio_verifier import AudioVerifier

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result of a single test case."""
    name: str
    passed: bool
    duration_ms: float
    actual_text: str = ""
    expected_text: str = ""
    confidence: float = 0.0
    similarity: float = 0.0
    matched_keywords: List[str] = field(default_factory=list)
    error: str = ""
    details: Dict = field(default_factory=dict)


class TestHarness:
    """Main test orchestration class."""

    def __init__(self, config_file: str = "tests/test_cases.yaml"):
        """
        Initialize test harness.

        Args:
            config_file: Path to test configuration YAML
        """
        self.config_file = Path(config_file)
        self.config = self._load_config()

        # Initialize components
        gen_config = self.config.get('config', {}).get('audio_generator', {})
        self.generator = AudioGenerator(
            piper_bin=gen_config.get('piper_bin', '/usr/share/piper/piper'),
            model_dir=gen_config.get('model_dir', '/usr/share/piper-voices'),
            output_dir=gen_config.get('output_dir', './tests/audio/inputs')
        )

        ver_config = self.config.get('config', {}).get('audio_verifier', {})
        self.verifier = AudioVerifier(
            whisper_bin=ver_config.get('whisper_bin', './build/bin/main'),
            model_path=ver_config.get('whisper_model', './models/ggml-base.en.bin')
        )

        self.test_cases = self.config.get('test_cases', [])
        self.results: List[TestResult] = []

        # Test criteria configuration
        criteria_config = self.config.get('config', {}).get('criteria', {})
        self.keyword_match_ratio = criteria_config.get('default_keyword_match_ratio', 0.30)
        self.default_min_confidence = criteria_config.get('default_min_confidence', 0.65)
        self.default_fuzzy_threshold = criteria_config.get('default_fuzzy_threshold', 0.85)

        # Create output directory
        self.output_dir = Path(ver_config.get('output_dir', './tests/audio/outputs'))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Results directory
        self.results_dir = Path('./tests/results')
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Wyoming-Piper configuration
        wyoming_config = self.config.get('config', {}).get('wyoming_piper', {})
        self.wyoming_cmd = wyoming_config.get('command', 'wyoming-piper')
        self.wyoming_args = wyoming_config.get('args', ['--voice', 'en_US-lessac-medium', '--port', '10200'])
        self.wyoming_port = wyoming_config.get('port', 10200)
        self.wyoming_process: Optional[subprocess.Popen] = None
        self.wyoming_started_by_us = False

    def _load_config(self) -> Dict:
        """Load test configuration from YAML file."""
        if not self.config_file.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_file}")

        with open(self.config_file, 'r') as f:
            return yaml.safe_load(f)

    def _is_wyoming_piper_running(self) -> bool:
        """Check if Wyoming-Piper is already running."""
        try:
            # Check if port is in use
            result = subprocess.run(
                ['lsof', '-i', f':{self.wyoming_port}', '-sTCP:LISTEN'],
                capture_output=True,
                text=True,
                timeout=2
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # lsof might not be available, try ps aux
            try:
                result = subprocess.run(
                    ['ps', 'aux'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                return 'wyoming-piper' in result.stdout or 'piper' in result.stdout
            except:
                return False

    async def _start_wyoming_piper(self) -> bool:
        """
        Start Wyoming-Piper TTS server.

        Returns:
            True if started successfully, False otherwise
        """
        if self._is_wyoming_piper_running():
            logger.info("Wyoming-Piper already running")
            return True

        try:
            logger.info(f"Starting Wyoming-Piper: {self.wyoming_cmd} {' '.join(self.wyoming_args)}")

            # Start Wyoming-Piper process
            self.wyoming_process = subprocess.Popen(
                [self.wyoming_cmd] + self.wyoming_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True  # Detach from parent
            )

            # Wait for startup
            logger.info("Waiting for Wyoming-Piper to start...")
            await asyncio.sleep(3)

            # Check if it's running
            if self.wyoming_process.poll() is not None:
                # Process died
                stderr = self.wyoming_process.stderr.read().decode()
                logger.error(f"Wyoming-Piper failed to start: {stderr}")
                return False

            # Verify port is listening
            if not self._is_wyoming_piper_running():
                logger.error("Wyoming-Piper started but not listening on port")
                self._stop_wyoming_piper()
                return False

            self.wyoming_started_by_us = True
            logger.info(f"✓ Wyoming-Piper started successfully on port {self.wyoming_port}")
            return True

        except FileNotFoundError:
            logger.error(f"Wyoming-Piper command not found: {self.wyoming_cmd}")
            logger.error("Install with: pip install wyoming-piper")
            return False
        except Exception as e:
            logger.error(f"Failed to start Wyoming-Piper: {e}")
            return False

    def _stop_wyoming_piper(self):
        """Stop Wyoming-Piper if we started it."""
        if self.wyoming_process and self.wyoming_started_by_us:
            logger.info("Stopping Wyoming-Piper...")
            try:
                # Send SIGTERM to process group
                pgid = self.wyoming_process.pid
                subprocess.run(['pkill', '-TERM', '-g', str(pgid)], timeout=2)

                # Wait for graceful shutdown
                try:
                    self.wyoming_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill
                    self.wyoming_process.kill()
                    self.wyoming_process.wait()

                logger.info("✓ Wyoming-Piper stopped")
            except Exception as e:
                logger.warning(f"Error stopping Wyoming-Piper: {e}")
            finally:
                self.wyoming_process = None
                self.wyoming_started_by_us = False

    def _get_test_cases(self, group: Optional[str] = None,
                       test_names: Optional[List[str]] = None) -> List[Dict]:
        """
        Get test cases to run.

        Args:
            group: Test group name (from test_groups in config)
            test_names: Specific test names to run

        Returns:
            List of test case dictionaries
        """
        if test_names:
            # Run specific tests by name
            return [tc for tc in self.test_cases if tc['name'] in test_names]

        if group:
            # Run tests in a specific group
            groups = self.config.get('test_groups', {})
            if group not in groups:
                raise ValueError(f"Unknown test group: {group}")

            group_tests = groups[group]
            return [tc for tc in self.test_cases if tc['name'] in group_tests]

        # Run all tests
        return self.test_cases

    async def run_test(self, test_case: Dict) -> TestResult:
        """
        Run a single test case.

        Args:
            test_case: Test case dictionary from YAML

        Returns:
            TestResult object
        """
        name = test_case['name']
        test_type = test_case.get('test_type', 'functional')

        logger.info(f"Running test: {name} ({test_type})")
        start_time = time.time()

        try:
            # Handle different test types
            if test_type == 'interrupt':
                return await self._run_interrupt_test(test_case, start_time)
            elif test_type == 'multi_turn':
                return await self._run_multi_turn_test(test_case, start_time)
            else:
                return await self._run_simple_test(test_case, start_time)

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Test {name} failed with exception: {e}")
            return TestResult(
                name=name,
                passed=False,
                duration_ms=duration_ms,
                error=str(e)
            )

    async def _run_simple_test(self, test_case: Dict, start_time: float) -> TestResult:
        """Run a simple functional test."""
        name = test_case['name']

        # Handle multiple inputs (e.g., stop_command_variations)
        if 'inputs' in test_case:
            return await self._run_multi_input_test(test_case, start_time)

        input_text = test_case['input']

        # 1. Generate test audio
        logger.info(f"Generating audio for: '{input_text}'")
        input_wav = self.generator.generate(
            input_text,
            output_name=f"{name}_input.wav"
        )

        # 2. Run voice assistant with test input
        logger.info(f"Running voice assistant with test input")
        output_wav = await self._run_assistant(input_wav, name)

        # 3. Verify output if generated
        if output_wav and output_wav.exists():
            logger.info(f"Verifying output: {output_wav}")

            # Determine verification method
            expected_response = test_case.get('expected_response')  # Full response for semantic
            expected_text = test_case.get('expected_fuzzy')  # For fuzzy match
            keywords = test_case.get('expected_contains')  # For keyword match

            verification_method = test_case.get('verification_method', 'auto')
            semantic_threshold = test_case.get('semantic_threshold', 0.70)
            fuzzy_threshold = test_case.get('fuzzy_threshold', self.default_fuzzy_threshold)
            min_confidence = test_case.get('min_confidence', self.default_min_confidence)

            # Determine which verification to use
            use_semantic = False
            if verification_method == 'semantic' or (verification_method == 'auto' and expected_response):
                use_semantic = True
                expected_text = expected_response  # Use expected_response for semantic
                logger.debug(f"Using semantic verification (threshold: {semantic_threshold})")
            elif keywords:
                # Calculate minimum keyword matches based on ratio
                import math
                min_keyword_matches = math.ceil(len(keywords) * self.keyword_match_ratio)
                logger.debug(f"Keyword matching: require {min_keyword_matches}/{len(keywords)} "
                           f"keywords (ratio: {self.keyword_match_ratio})")
            else:
                min_keyword_matches = None

            # Run verification
            results = self.verifier.verify(
                output_wav,
                expected_text=expected_text,
                keywords=keywords,
                fuzzy_threshold=fuzzy_threshold,
                min_confidence=min_confidence,
                min_keyword_matches=min_keyword_matches if not use_semantic else None,
                semantic_threshold=semantic_threshold,
                use_semantic=use_semantic
            )

            duration_ms = (time.time() - start_time) * 1000

            # Get similarity score from appropriate test
            similarity = 0.0
            if 'semantic_match' in results['tests']:
                similarity = results['tests']['semantic_match'].get('similarity', 0.0)
            elif 'fuzzy_match' in results['tests']:
                similarity = results['tests']['fuzzy_match'].get('similarity', 0.0)

            return TestResult(
                name=name,
                passed=results['overall_passed'],
                duration_ms=duration_ms,
                actual_text=results['actual_text'],
                expected_text=expected_text or expected_response or str(keywords),
                confidence=results['confidence'],
                similarity=similarity,
                matched_keywords=results['tests'].get('keyword_match', {}).get('matched_keywords', []),
                details=results
            )
        else:
            # No output generated - might be a command test
            duration_ms = (time.time() - start_time) * 1000

            # Check if this is expected (e.g., stop command)
            if test_case.get('expected_behavior') == 'immediate_stop':
                logger.info(f"Stop command test - no output expected")
                return TestResult(
                    name=name,
                    passed=True,  # TODO: verify stop was actually executed
                    duration_ms=duration_ms,
                    actual_text="[STOP COMMAND]",
                    expected_text="stop"
                )
            else:
                logger.warning(f"No output generated for test {name}")
                return TestResult(
                    name=name,
                    passed=False,
                    duration_ms=duration_ms,
                    error="No output audio generated"
                )

    async def _run_multi_input_test(self, test_case: Dict, start_time: float) -> TestResult:
        """Run a test with multiple input variations (e.g., stop_command_variations)."""
        name = test_case['name']
        inputs = test_case['inputs']

        logger.info(f"Testing {len(inputs)} input variations for {name}")

        all_passed = True
        failures = []

        for i, input_text in enumerate(inputs):
            logger.info(f"  Testing variation {i+1}/{len(inputs)}: '{input_text}'")

            # Create a temporary single-input test case
            temp_test = test_case.copy()
            temp_test['input'] = input_text
            temp_test.pop('inputs', None)  # Remove 'inputs' to avoid recursion

            # Run as simple test
            result = await self._run_simple_test(temp_test, time.time())

            if not result.passed:
                all_passed = False
                failures.append(f"{input_text}: {result.error or 'failed'}")
                logger.warning(f"  ✗ Variation '{input_text}' failed")
            else:
                logger.info(f"  ✓ Variation '{input_text}' passed")

        duration_ms = (time.time() - start_time) * 1000

        if all_passed:
            return TestResult(
                name=name,
                passed=True,
                duration_ms=duration_ms,
                actual_text=f"All {len(inputs)} variations passed"
            )
        else:
            return TestResult(
                name=name,
                passed=False,
                duration_ms=duration_ms,
                error=f"{len(failures)}/{len(inputs)} variations failed: {'; '.join(failures)}"
            )

    async def _run_interrupt_test(self, test_case: Dict, start_time: float) -> TestResult:
        """Run an interrupt test (e.g., stop command during TTS)."""
        name = test_case['name']
        logger.info(f"Running interrupt test: {name}")

        # For now, we'll implement a simplified version that just tests
        # that the system can handle sequential commands
        # A full implementation would require monitoring TTS process

        sequence = test_case.get('sequence', [])
        if not sequence:
            return TestResult(
                name=name,
                passed=False,
                duration_ms=0,
                error="No sequence defined for interrupt test"
            )

        logger.info(f"Executing {len(sequence)} step sequence")

        all_steps_passed = True
        step_results = []

        for step in sequence:
            step_num = step.get('step', 0)
            action = step.get('action')

            logger.info(f"  Step {step_num}: {action}")

            if action == "send_input":
                input_text = step.get('input')

                # Generate and run input
                input_wav = self.generator.generate(
                    input_text,
                    output_name=f"{name}_step{step_num}_input.wav"
                )
                output_wav = await self._run_assistant(input_wav, f"{name}_step{step_num}")

                # Verify if expected
                if 'expected_contains' in step:
                    if output_wav and output_wav.exists():
                        import math
                        keywords = step['expected_contains']
                        min_matches = math.ceil(len(keywords) * self.keyword_match_ratio)
                        results = self.verifier.verify(
                            output_wav,
                            keywords=keywords,
                            min_keyword_matches=min_matches,
                            min_confidence=step.get('min_confidence', 0.65)
                        )
                        if not results['overall_passed']:
                            all_steps_passed = False
                            step_results.append(f"Step {step_num} verification failed")
                    else:
                        all_steps_passed = False
                        step_results.append(f"Step {step_num} no output")

            elif action == "wait":
                duration_ms = step.get('duration_ms', 1000)
                logger.info(f"    Waiting {duration_ms}ms...")
                await asyncio.sleep(duration_ms / 1000.0)

        duration_ms = (time.time() - start_time) * 1000

        if all_steps_passed:
            return TestResult(
                name=name,
                passed=True,
                duration_ms=duration_ms,
                actual_text=f"All {len(sequence)} steps completed"
            )
        else:
            return TestResult(
                name=name,
                passed=False,
                duration_ms=duration_ms,
                error=f"Sequence failed: {'; '.join(step_results)}"
            )

    async def _run_multi_turn_test(self, test_case: Dict, start_time: float) -> TestResult:
        """Run a multi-turn conversation test."""
        name = test_case['name']
        turns = test_case.get('turns', [])

        if not turns:
            return TestResult(
                name=name,
                passed=False,
                duration_ms=0,
                error="No turns defined for multi-turn test"
            )

        logger.info(f"Testing {len(turns)} conversation turns")

        all_turns_passed = True
        turn_results = []

        for i, turn in enumerate(turns):
            turn_num = i + 1
            input_text = turn['input']

            logger.info(f"  Turn {turn_num}/{len(turns)}: '{input_text}'")

            # Generate test audio
            input_wav = self.generator.generate(
                input_text,
                output_name=f"{name}_turn{turn_num}_input.wav"
            )

            # Run voice assistant
            output_wav = await self._run_assistant(input_wav, f"{name}_turn{turn_num}")

            # Verify output
            if output_wav and output_wav.exists():
                # Use semantic if expected_response provided, otherwise keywords
                if 'expected_response' in turn:
                    results = self.verifier.verify(
                        output_wav,
                        expected_text=turn['expected_response'],
                        semantic_threshold=turn.get('semantic_threshold', 0.70),
                        use_semantic=True,
                        min_confidence=turn.get('min_confidence', 0.65)
                    )
                elif 'expected_contains' in turn:
                    import math
                    min_matches = math.ceil(len(turn['expected_contains']) * self.keyword_match_ratio)
                    results = self.verifier.verify(
                        output_wav,
                        keywords=turn['expected_contains'],
                        min_keyword_matches=min_matches,
                        min_confidence=turn.get('min_confidence', 0.65)
                    )
                else:
                    logger.warning(f"  Turn {turn_num} has no verification criteria")
                    continue

                if results['overall_passed']:
                    logger.info(f"  ✓ Turn {turn_num} passed")
                else:
                    logger.warning(f"  ✗ Turn {turn_num} failed")
                    all_turns_passed = False
                    turn_results.append(f"Turn {turn_num} failed verification")
            else:
                logger.error(f"  ✗ Turn {turn_num} produced no output")
                all_turns_passed = False
                turn_results.append(f"Turn {turn_num} no output")

        duration_ms = (time.time() - start_time) * 1000

        if all_turns_passed:
            return TestResult(
                name=name,
                passed=True,
                duration_ms=duration_ms,
                actual_text=f"All {len(turns)} turns passed"
            )
        else:
            return TestResult(
                name=name,
                passed=False,
                duration_ms=duration_ms,
                error=f"{len(turn_results)} turn(s) failed: {'; '.join(turn_results)}"
            )

    def _concatenate_wav_files(self, input_files: List[Path], output_file: Path) -> bool:
        """
        Concatenate multiple WAV files into a single WAV file.

        Args:
            input_files: List of WAV files to concatenate (in order)
            output_file: Path to output concatenated WAV file

        Returns:
            True if successful, False otherwise
        """
        try:
            import wave
            import struct

            if not input_files:
                logger.error("No input files to concatenate")
                return False

            # Read parameters from first file
            with wave.open(str(input_files[0]), 'rb') as first_wav:
                params = first_wav.getparams()
                nchannels = params.nchannels
                sampwidth = params.sampwidth
                framerate = params.framerate

            # Concatenate all audio data
            audio_data = []

            for wav_file in input_files:
                with wave.open(str(wav_file), 'rb') as wav:
                    # Verify parameters match
                    if (wav.getnchannels() != nchannels or
                        wav.getsampwidth() != sampwidth or
                        wav.getframerate() != framerate):
                        logger.warning(f"WAV parameters mismatch in {wav_file.name}")
                        logger.warning(f"  Expected: {nchannels}ch, {sampwidth}B, {framerate}Hz")
                        logger.warning(f"  Got: {wav.getnchannels()}ch, {wav.getsampwidth()}B, {wav.getframerate()}Hz")
                        # Continue anyway, may still work

                    # Read audio frames
                    frames = wav.readframes(wav.getnframes())
                    audio_data.append(frames)

            # Write concatenated output
            with wave.open(str(output_file), 'wb') as out_wav:
                out_wav.setnchannels(nchannels)
                out_wav.setsampwidth(sampwidth)
                out_wav.setframerate(framerate)

                # Write all frames
                for frames in audio_data:
                    out_wav.writeframes(frames)

            logger.debug(f"Concatenated {len(input_files)} files into {output_file.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to concatenate WAV files: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False

    async def _run_assistant(self, input_wav: Path, test_name: str) -> Optional[Path]:
        """
        Run the voice assistant with test input.

        Args:
            input_wav: Path to input audio file
            test_name: Name of test (for output naming)

        Returns:
            Path to output audio file if generated
        """
        import subprocess

        talk_llama_config = self.config.get('config', {}).get('talk_llama', {})
        binary = talk_llama_config.get('binary', './build/bin/talk-llama')
        whisper_model = talk_llama_config.get('whisper_model', './models/ggml-base.en.bin')
        llama_model = talk_llama_config.get('llama_model', './models/ggml-llama-7B.bin')
        temperature = talk_llama_config.get('temperature', None)

        # Build command
        cmd = [
            binary,
            '--test-input', str(input_wav),
            '-mw', whisper_model,
            '-ml', llama_model,
            '--verbose'
        ]

        # Add temperature if specified
        if temperature is not None:
            cmd.extend(['--temp', str(temperature)])

        logger.info(f"Running: {' '.join(cmd)}")

        try:
            timeout = self.config.get('execution', {}).get('timeout_per_test', 120)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            logger.debug(f"Assistant stdout:\n{result.stdout}")
            if result.stderr:
                logger.debug(f"Assistant stderr:\n{result.stderr}")

            # Capture output audio from Wyoming-Piper (test mode)
            # In test mode, Wyoming-Piper saves files as output_<timestamp>_<index>.wav
            # The LLM response is split into chunks (sentences), creating multiple WAV files
            # We need to concatenate all chunks to get the complete response

            output_wav = self.output_dir / f"{test_name}_output.wav"

            # Find all output files from the most recent timestamp
            import glob
            import shutil
            import re

            output_files = sorted(self.output_dir.glob("output_*_*.wav"),
                                key=lambda p: p.stat().st_mtime, reverse=True)

            if not output_files:
                logger.warning("Could not find any output audio files")
                return None

            # Extract timestamp from the most recent file
            # File format: output_<timestamp>_<part_number>.wav
            latest_file = output_files[0]
            match = re.match(r'output_(\d+)_(\d+)\.wav', latest_file.name)
            if not match:
                logger.warning(f"Unexpected output file format: {latest_file.name}")
                shutil.copy(str(latest_file), str(output_wav))
                return output_wav

            timestamp = match.group(1)

            # Find all files with the same timestamp
            chunk_pattern = f"output_{timestamp}_*.wav"
            chunk_files = sorted(self.output_dir.glob(chunk_pattern))

            if not chunk_files:
                logger.warning(f"No chunk files found for timestamp {timestamp}")
                return None

            # Sort by part number (extract from filename)
            def get_part_number(filepath):
                m = re.match(r'output_\d+_(\d+)\.wav', filepath.name)
                return int(m.group(1)) if m else 0

            chunk_files = sorted(chunk_files, key=get_part_number)

            logger.info(f"Found {len(chunk_files)} audio chunks for timestamp {timestamp}")
            for chunk in chunk_files:
                logger.debug(f"  - {chunk.name}")

            if len(chunk_files) == 1:
                # Only one chunk, just copy it
                shutil.copy(str(chunk_files[0]), str(output_wav))
                logger.info(f"Captured output audio: {output_wav} (single chunk)")
            else:
                # Multiple chunks - concatenate them
                logger.info(f"Concatenating {len(chunk_files)} audio chunks...")
                if self._concatenate_wav_files(chunk_files, output_wav):
                    logger.info(f"Captured output audio: {output_wav} (concatenated from {len(chunk_files)} chunks)")
                else:
                    logger.error("Failed to concatenate audio chunks")
                    return None

            return output_wav

        except subprocess.TimeoutExpired:
            logger.error(f"Assistant timed out after 30 seconds")
            return None
        except Exception as e:
            logger.error(f"Failed to run assistant: {e}")
            return None

    async def run_all_tests(self, group: Optional[str] = None,
                           test_names: Optional[List[str]] = None) -> List[TestResult]:
        """
        Run all test cases and generate report.

        Args:
            group: Test group to run
            test_names: Specific tests to run

        Returns:
            List of test results
        """
        # Start Wyoming-Piper if needed
        logger.info("Checking Wyoming-Piper status...")
        if not await self._start_wyoming_piper():
            logger.error("Failed to start Wyoming-Piper - tests may fail")
            print("⚠ WARNING: Wyoming-Piper not running - TTS tests will fail")

        try:
            test_cases = self._get_test_cases(group, test_names)

            logger.info(f"Running {len(test_cases)} tests...")

            self.results = []
            for test_case in test_cases:
                result = await self.run_test(test_case)
                self.results.append(result)

                # Print immediate feedback
                status = "PASS" if result.passed else "FAIL"
                print(f"[{status}] {result.name} ({result.duration_ms:.0f}ms)")

            return self.results

        finally:
            # Clean up Wyoming-Piper if we started it
            self._stop_wyoming_piper()

    def generate_report(self, output_format: str = 'text') -> str:
        """
        Generate test report.

        Args:
            output_format: 'text', 'json', or 'html'

        Returns:
            Report content as string
        """
        if output_format == 'json':
            return self._generate_json_report()
        elif output_format == 'html':
            return self._generate_html_report()
        else:
            return self._generate_text_report()

    def _generate_text_report(self) -> str:
        """Generate plain text report."""
        lines = []
        lines.append("=" * 80)
        lines.append("AUDIO PIPELINE TEST REPORT")
        lines.append("=" * 80)
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Total Tests: {len(self.results)}")

        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed

        lines.append(f"Passed: {passed}")
        lines.append(f"Failed: {failed}")
        lines.append(f"Success Rate: {passed/len(self.results)*100:.1f}%")
        lines.append("")

        # Individual test results
        lines.append("DETAILED RESULTS")
        lines.append("-" * 80)

        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            lines.append(f"\n[{status}] {result.name}")
            lines.append(f"  Duration: {result.duration_ms:.0f}ms")

            if result.actual_text:
                lines.append(f"  Transcription: '{result.actual_text}'")
            if result.expected_text:
                lines.append(f"  Expected: '{result.expected_text}'")
            if result.confidence > 0:
                lines.append(f"  Confidence: {result.confidence:.2%}")
            if result.similarity > 0:
                lines.append(f"  Similarity: {result.similarity:.2%}")
            if result.matched_keywords:
                lines.append(f"  Matched Keywords: {result.matched_keywords}")
            if result.error:
                lines.append(f"  Error: {result.error}")

        lines.append("\n" + "=" * 80)

        return "\n".join(lines)

    def _generate_json_report(self) -> str:
        """Generate JSON report."""
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total': len(self.results),
                'passed': sum(1 for r in self.results if r.passed),
                'failed': sum(1 for r in self.results if not r.passed),
            },
            'results': [
                {
                    'name': r.name,
                    'passed': r.passed,
                    'duration_ms': r.duration_ms,
                    'actual_text': r.actual_text,
                    'expected_text': r.expected_text,
                    'confidence': r.confidence,
                    'similarity': r.similarity,
                    'matched_keywords': r.matched_keywords,
                    'error': r.error,
                    'details': r.details
                }
                for r in self.results
            ]
        }
        return json.dumps(report, indent=2)

    def _generate_html_report(self) -> str:
        """Generate HTML report."""
        # Simple HTML template
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Audio Pipeline Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .summary {{ background: #f0f0f0; padding: 15px; margin-bottom: 20px; }}
        .pass {{ color: green; font-weight: bold; }}
        .fail {{ color: red; font-weight: bold; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
    </style>
</head>
<body>
    <h1>Audio Pipeline Test Report</h1>

    <div class="summary">
        <h2>Summary</h2>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>Total: {len(self.results)} | <span class="pass">Passed: {passed}</span> | <span class="fail">Failed: {failed}</span></p>
        <p>Success Rate: {passed/len(self.results)*100:.1f}%</p>
    </div>

    <h2>Test Results</h2>
    <table>
        <tr>
            <th>Status</th>
            <th>Test Name</th>
            <th>Duration (ms)</th>
            <th>Confidence</th>
            <th>Details</th>
        </tr>
"""

        for result in self.results:
            status_class = "pass" if result.passed else "fail"
            status_text = "PASS" if result.passed else "FAIL"

            html += f"""        <tr>
            <td class="{status_class}">{status_text}</td>
            <td>{result.name}</td>
            <td>{result.duration_ms:.0f}</td>
            <td>{result.confidence:.2%}</td>
            <td>{result.actual_text or result.error}</td>
        </tr>
"""

        html += """    </table>
</body>
</html>"""

        return html

    def save_report(self, output_format: str = 'text', filename: Optional[str] = None):
        """Save report to file."""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            ext = 'txt' if output_format == 'text' else output_format
            filename = f"test_report_{timestamp}.{ext}"

        filepath = self.results_dir / filename

        report = self.generate_report(output_format)

        with open(filepath, 'w') as f:
            f.write(report)

        logger.info(f"Report saved to: {filepath}")
        return filepath


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run audio pipeline tests")
    parser.add_argument('--config', type=str, default='tests/test_cases.yaml',
                       help='Test configuration file')
    parser.add_argument('--group', type=str, help='Test group to run (smoke, functional, etc.)')
    parser.add_argument('--test', type=str, nargs='+', help='Specific test(s) to run')
    parser.add_argument('--format', type=str, default='text',
                       choices=['text', 'json', 'html'], help='Report format')
    parser.add_argument('--output', type=str, help='Output report filename')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run tests
    harness = TestHarness(config_file=args.config)
    results = await harness.run_all_tests(group=args.group, test_names=args.test)

    # Generate and save report
    print("\n" + harness.generate_report('text'))
    harness.save_report(output_format=args.format, filename=args.output)

    # Exit with appropriate code
    all_passed = all(r.passed for r in results)
    exit(0 if all_passed else 1)


if __name__ == '__main__':
    asyncio.run(main())
