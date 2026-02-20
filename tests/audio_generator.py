#!/usr/bin/env python3
"""Generate test audio files using Piper TTS."""

import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AudioGenerator:
    """Generate test audio files using Piper TTS."""

    def __init__(self, piper_bin: str = "/usr/share/piper/piper",
                 model_dir: str = "/usr/share/piper-voices",
                 output_dir: str = "./tests/audio/inputs"):
        """
        Initialize the audio generator.

        Args:
            piper_bin: Path to Piper executable
            model_dir: Directory containing Piper voice models
            output_dir: Directory to save generated audio files
        """
        self.piper_bin = Path(piper_bin)
        self.model_dir = Path(model_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not self.piper_bin.exists():
            raise FileNotFoundError(f"Piper binary not found at {self.piper_bin}")

        logger.info(f"AudioGenerator initialized with Piper at {self.piper_bin}")

    def generate(self, text: str, voice: str = "en_US-lessac-medium",
                 output_name: Optional[str] = None) -> Path:
        """
        Generate WAV file from text using Piper.

        Args:
            text: Text to convert to speech
            voice: Voice model to use
            output_name: Output filename (without .wav extension)
                        If None, generates name from text hash

        Returns:
            Path to generated WAV file
        """
        if output_name is None:
            # Generate filename from text hash
            import hashlib
            text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            output_name = f"test_{text_hash}.wav"
        elif not output_name.endswith('.wav'):
            output_name = f"{output_name}.wav"

        output_path = self.output_dir / output_name

        # Check if file already exists (cache)
        if output_path.exists():
            logger.info(f"Using cached audio file: {output_path}")
            return output_path

        # Find model file
        model_path = self._find_model(voice)
        if not model_path:
            raise FileNotFoundError(f"Voice model '{voice}' not found in {self.model_dir}")

        logger.info(f"Generating audio: '{text}' -> {output_path}")

        try:
            # Run Piper with text input
            cmd = [
                str(self.piper_bin),
                "--model", str(model_path),
                "--output_file", str(output_path)
            ]

            result = subprocess.run(
                cmd,
                input=text.encode('utf-8'),
                capture_output=True,
                timeout=30
            )

            if result.returncode != 0:
                raise RuntimeError(f"Piper failed: {result.stderr.decode()}")

            if not output_path.exists():
                raise RuntimeError(f"Piper did not create output file: {output_path}")

            # Resample to 16kHz (Whisper requirement)
            self._resample_to_16khz(output_path)

            logger.info(f"Successfully generated: {output_path}")
            return output_path

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Piper timed out generating audio for: {text}")
        except Exception as e:
            logger.error(f"Failed to generate audio: {e}")
            raise

    def _find_model(self, voice: str) -> Optional[Path]:
        """Find the model file for a given voice."""
        # Try common model file patterns
        patterns = [
            f"{voice}.onnx",
            f"{voice}/{voice}.onnx",
            f"*/{voice}.onnx",
        ]

        for pattern in patterns:
            matches = list(self.model_dir.glob(pattern))
            if matches:
                return matches[0]

        return None

    def _resample_to_16khz(self, wav_file: Path):
        """
        Resample WAV file to 16kHz (Whisper requirement).

        Args:
            wav_file: Path to WAV file to resample (modified in place)
        """
        try:
            # Use ffmpeg or sox to resample
            temp_file = wav_file.with_suffix('.tmp.wav')

            # Try ffmpeg first
            result = subprocess.run(
                ['ffmpeg', '-i', str(wav_file), '-ar', '16000', '-ac', '1',
                 '-y', str(temp_file)],
                capture_output=True,
                timeout=10
            )

            if result.returncode == 0 and temp_file.exists():
                # Replace original with resampled
                temp_file.replace(wav_file)
                logger.debug(f"Resampled {wav_file} to 16kHz")
                return

            # Try sox as fallback
            result = subprocess.run(
                ['sox', str(wav_file), '-r', '16000', str(temp_file)],
                capture_output=True,
                timeout=10
            )

            if result.returncode == 0 and temp_file.exists():
                temp_file.replace(wav_file)
                logger.debug(f"Resampled {wav_file} to 16kHz using sox")
                return

            logger.warning(f"Could not resample {wav_file} - ffmpeg/sox not available")

        except Exception as e:
            logger.warning(f"Resampling failed: {e}")

    def generate_batch(self, test_cases: List[Dict]) -> Dict[str, Path]:
        """
        Generate multiple test audio files from test cases.

        Args:
            test_cases: List of test case dictionaries with keys:
                       - 'name': Test case name
                       - 'input': Text to generate
                       - 'voice': (optional) Voice to use

        Returns:
            Dictionary mapping test case names to generated audio file paths
        """
        results = {}

        for i, test_case in enumerate(test_cases):
            name = test_case.get('name', f"test_{i}")
            text = test_case['input']
            voice = test_case.get('voice', 'en_US-lessac-medium')

            # Sanitize name for filename
            safe_name = name.replace(' ', '_').replace('/', '_')
            output_name = f"{safe_name}.wav"

            try:
                audio_path = self.generate(text, voice=voice, output_name=output_name)
                results[name] = audio_path
                logger.info(f"Generated test case '{name}': {audio_path}")
            except Exception as e:
                logger.error(f"Failed to generate test case '{name}': {e}")
                results[name] = None

        return results

    def list_generated_files(self) -> List[Path]:
        """List all generated audio files."""
        return sorted(self.output_dir.glob("*.wav"))

    def clear_cache(self):
        """Delete all generated audio files."""
        for wav_file in self.list_generated_files():
            wav_file.unlink()
            logger.info(f"Deleted: {wav_file}")


def main():
    """Command-line interface for audio generation."""
    import argparse
    import yaml

    parser = argparse.ArgumentParser(description="Generate test audio files using Piper TTS")
    parser.add_argument('--config', type=str, help='Test cases YAML file')
    parser.add_argument('--text', type=str, help='Single text to generate')
    parser.add_argument('--voice', type=str, default='en_US-lessac-medium',
                       help='Voice model to use')
    parser.add_argument('--output', type=str, help='Output filename')
    parser.add_argument('--output-dir', type=str, default='./tests/audio/inputs',
                       help='Output directory')
    parser.add_argument('--piper-bin', type=str, default='/usr/share/piper/piper',
                       help='Path to Piper binary')
    parser.add_argument('--model-dir', type=str, default='/usr/share/piper-voices',
                       help='Path to Piper voice models')
    parser.add_argument('--list', action='store_true', help='List generated files')
    parser.add_argument('--clear', action='store_true', help='Clear cache')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    generator = AudioGenerator(
        piper_bin=args.piper_bin,
        model_dir=args.model_dir,
        output_dir=args.output_dir
    )

    if args.list:
        files = generator.list_generated_files()
        print(f"\nGenerated audio files ({len(files)}):")
        for f in files:
            print(f"  {f}")
        return

    if args.clear:
        generator.clear_cache()
        print("Cache cleared")
        return

    if args.text:
        # Generate single audio file
        output = generator.generate(args.text, voice=args.voice, output_name=args.output)
        print(f"Generated: {output}")

    elif args.config:
        # Generate batch from YAML config
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)

        test_cases = config.get('test_cases', [])
        results = generator.generate_batch(test_cases)

        print(f"\nGenerated {len(results)} test audio files:")
        for name, path in results.items():
            status = "OK" if path else "FAILED"
            print(f"  [{status}] {name}: {path}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
