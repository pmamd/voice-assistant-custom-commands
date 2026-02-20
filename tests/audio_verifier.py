#!/usr/bin/env python3
"""Verify audio output using Whisper STT."""

import subprocess
import json
import logging
import difflib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AudioVerifier:
    """Verify audio output using Whisper STT."""

    def __init__(self, whisper_bin: str = "./build/bin/main",
                 model_path: str = "./models/ggml-base.en.bin",
                 use_semantic: bool = True):
        """
        Initialize the audio verifier.

        Args:
            whisper_bin: Path to Whisper main executable
            model_path: Path to Whisper model file
            use_semantic: Enable semantic similarity verification (requires sentence-transformers)
        """
        self.whisper_bin = Path(whisper_bin)
        self.model_path = Path(model_path)

        if not self.whisper_bin.exists():
            raise FileNotFoundError(f"Whisper binary not found at {self.whisper_bin}")
        if not self.model_path.exists():
            raise FileNotFoundError(f"Whisper model not found at {self.model_path}")

        logger.info(f"AudioVerifier initialized with Whisper at {self.whisper_bin}")

        # Try to load semantic similarity model
        self.semantic_model = None
        if use_semantic:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading semantic similarity model (all-MiniLM-L6-v2)...")
                self.semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("✓ Semantic similarity enabled")
            except ImportError:
                logger.warning("sentence-transformers not available - using keyword matching only")
                logger.warning("Install with: pip install sentence-transformers")
            except Exception as e:
                logger.warning(f"Failed to load semantic model: {e}")
                logger.warning("Falling back to keyword matching")

    def _ensure_16khz(self, wav_file: Path) -> Path:
        """
        Ensure WAV file is 16kHz (required by Whisper).
        Returns path to 16kHz file (original or resampled).

        Args:
            wav_file: Path to WAV file

        Returns:
            Path to 16kHz WAV file
        """
        import wave

        # Check current sample rate
        with wave.open(str(wav_file), 'rb') as wf:
            sample_rate = wf.getframerate()

        if sample_rate == 16000:
            # Already 16kHz
            return wav_file

        # Resample to 16kHz using ffmpeg
        logger.info(f"Resampling {wav_file} from {sample_rate}Hz to 16000Hz")
        temp_file = wav_file.parent / f"{wav_file.stem}_16khz.wav"

        try:
            result = subprocess.run(
                ['ffmpeg', '-i', str(wav_file), '-ar', '16000', '-ac', '1',
                 '-y', str(temp_file)],
                capture_output=True,
                timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg resampling failed: {result.stderr.decode()}")

            return temp_file

        except FileNotFoundError:
            raise RuntimeError("ffmpeg not found - required for resampling audio")

    def transcribe(self, wav_file: Path, output_json: bool = True) -> Tuple[str, float]:
        """
        Transcribe audio file using Whisper.

        Args:
            wav_file: Path to WAV file to transcribe
            output_json: Whether to parse JSON output for confidence scores

        Returns:
            Tuple of (transcribed_text, average_confidence)
        """
        if not wav_file.exists():
            raise FileNotFoundError(f"Audio file not found: {wav_file}")

        logger.info(f"Transcribing: {wav_file}")

        # Prepare output paths
        output_dir = wav_file.parent
        output_prefix = wav_file.stem

        # Resample to 16kHz if needed (Whisper requires 16kHz)
        wav_to_transcribe = self._ensure_16khz(wav_file)

        try:
            # Run Whisper with JSON output
            cmd = [
                str(self.whisper_bin),
                "-m", str(self.model_path),
                "-f", str(wav_to_transcribe),
                "-nt"  # No timestamps in text output
            ]

            if output_json:
                cmd.extend(["-ojf", "-of", str(output_dir / output_prefix)])

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=60,
                text=True
            )

            if result.returncode != 0:
                logger.error(f"Whisper failed: {result.stderr}")
                raise RuntimeError(f"Whisper failed: {result.stderr}")

            # Parse output
            text = ""
            confidence = 0.0

            if output_json:
                json_file = output_dir / f"{output_prefix}.json"
                if json_file.exists():
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                        if 'transcription' in data and len(data['transcription']) > 0:
                            text = data['transcription'][0]['text'].strip()
                            # Calculate average token probability if available
                            tokens = data['transcription'][0].get('tokens', [])
                            if tokens:
                                probs = [t.get('p', 0.0) for t in tokens]
                                confidence = sum(probs) / len(probs) if probs else 0.0
                        elif 'text' in data:
                            text = data['text'].strip()

                    # Cleanup JSON file
                    json_file.unlink()
                else:
                    logger.warning(f"JSON file not created: {json_file}")
                    # Fall back to parsing stdout
                    text = result.stdout.strip()
            else:
                text = result.stdout.strip()

            logger.info(f"Transcribed: '{text}' (confidence: {confidence:.2f})")
            return text, confidence

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Whisper timed out transcribing: {wav_file}")
        except Exception as e:
            logger.error(f"Failed to transcribe: {e}")
            raise
        finally:
            # Clean up resampled file if we created one
            if wav_to_transcribe != wav_file and wav_to_transcribe.exists():
                wav_to_transcribe.unlink()

    def verify_exact(self, wav_file: Path, expected_text: str,
                    case_sensitive: bool = False) -> Tuple[bool, str, float]:
        """
        Verify transcription matches expected text exactly.

        Args:
            wav_file: Audio file to verify
            expected_text: Expected transcription
            case_sensitive: Whether to do case-sensitive comparison

        Returns:
            Tuple of (passed, actual_text, confidence)
        """
        actual_text, confidence = self.transcribe(wav_file)

        expected = expected_text if case_sensitive else expected_text.lower()
        actual = actual_text if case_sensitive else actual_text.lower()

        passed = expected == actual

        if not passed:
            logger.warning(f"Exact match failed. Expected: '{expected}', Got: '{actual}'")
        else:
            logger.info(f"Exact match passed: '{actual}'")

        return passed, actual_text, confidence

    def verify_fuzzy(self, wav_file: Path, expected_text: str,
                    threshold: float = 0.85) -> Tuple[bool, float, str, float]:
        """
        Verify transcription using fuzzy matching.

        Args:
            wav_file: Audio file to verify
            expected_text: Expected transcription
            threshold: Minimum similarity score (0.0-1.0)

        Returns:
            Tuple of (passed, similarity_score, actual_text, confidence)
        """
        actual_text, confidence = self.transcribe(wav_file)

        # Calculate similarity using difflib
        similarity = difflib.SequenceMatcher(
            None,
            expected_text.lower(),
            actual_text.lower()
        ).ratio()

        passed = similarity >= threshold

        if not passed:
            logger.warning(
                f"Fuzzy match failed. Expected: '{expected_text}', "
                f"Got: '{actual_text}', Similarity: {similarity:.2%} < {threshold:.2%}"
            )
        else:
            logger.info(
                f"Fuzzy match passed: '{actual_text}', "
                f"Similarity: {similarity:.2%}"
            )

        return passed, similarity, actual_text, confidence

    def verify_keywords(self, wav_file: Path, keywords: List[str],
                       min_matches: Optional[int] = None) -> Tuple[bool, List[str], str, float]:
        """
        Verify that transcription contains expected keywords.

        Args:
            wav_file: Audio file to verify
            keywords: List of keywords to check for
            min_matches: Minimum number of keywords that must match (default: all)

        Returns:
            Tuple of (passed, matched_keywords, actual_text, confidence)
        """
        actual_text, confidence = self.transcribe(wav_file)
        actual_lower = actual_text.lower()

        matched = [kw for kw in keywords if kw.lower() in actual_lower]

        if min_matches is None:
            min_matches = len(keywords)

        passed = len(matched) >= min_matches

        if not passed:
            logger.warning(
                f"Keyword match failed. Expected {min_matches}/{len(keywords)}, "
                f"Got {len(matched)}/{len(keywords)}: {matched}"
            )
        else:
            logger.info(f"Keyword match passed: {len(matched)}/{len(keywords)} keywords found")

        return passed, matched, actual_text, confidence

    def verify_semantic(self, wav_file: Path, expected_text: str,
                       threshold: float = 0.70) -> Tuple[bool, float, str, float]:
        """
        Verify transcription using semantic similarity.

        Args:
            wav_file: Audio file to verify
            expected_text: Expected text content
            threshold: Minimum semantic similarity score (0.0-1.0)

        Returns:
            Tuple of (passed, similarity, actual_text, confidence)
        """
        actual_text, confidence = self.transcribe(wav_file)

        if self.semantic_model is None:
            logger.warning("Semantic model not available, falling back to fuzzy match")
            return self.verify_fuzzy(wav_file, expected_text, threshold)

        try:
            from sklearn.metrics.pairwise import cosine_similarity

            # Encode both texts
            embeddings = self.semantic_model.encode([expected_text, actual_text])

            # Calculate cosine similarity
            similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]

            passed = similarity >= threshold

            if passed:
                logger.info(f"Semantic match passed: {similarity:.3f} >= {threshold:.3f}")
            else:
                logger.warning(f"Semantic match failed: {similarity:.3f} < {threshold:.3f}")
                logger.warning(f"  Expected: '{expected_text}'")
                logger.warning(f"  Actual:   '{actual_text}'")

            return passed, similarity, actual_text, confidence

        except Exception as e:
            logger.error(f"Semantic verification failed: {e}")
            logger.warning("Falling back to fuzzy match")
            return self.verify_fuzzy(wav_file, expected_text, threshold)

    def verify(self, wav_file: Path, expected_text: str = None,
              keywords: List[str] = None,
              fuzzy_threshold: float = 0.85,
              min_confidence: float = 0.0,
              min_keyword_matches: int = None,
              semantic_threshold: float = 0.70,
              use_semantic: bool = False) -> Dict:
        """
        Comprehensive verification with multiple strategies.

        Args:
            wav_file: Audio file to verify
            expected_text: Expected full text (for fuzzy/semantic matching)
            keywords: Keywords to check for
            fuzzy_threshold: Minimum similarity for fuzzy match
            min_confidence: Minimum confidence score
            min_keyword_matches: Minimum number of keywords that must match (default: all)
            semantic_threshold: Minimum semantic similarity score (0.0-1.0)
            use_semantic: Use semantic similarity instead of fuzzy match

        Returns:
            Dictionary with verification results
        """
        actual_text, confidence = self.transcribe(wav_file)

        results = {
            'wav_file': str(wav_file),
            'actual_text': actual_text,
            'confidence': confidence,
            'confidence_passed': confidence >= min_confidence,
            'tests': {}
        }

        # Semantic similarity (preferred if available and requested)
        if expected_text and use_semantic and self.semantic_model is not None:
            passed, similarity, _, _ = self.verify_semantic(
                wav_file, expected_text, semantic_threshold
            )
            results['tests']['semantic_match'] = {
                'passed': passed,
                'expected': expected_text,
                'similarity': similarity,
                'threshold': semantic_threshold
            }
        # Fuzzy text matching (fallback or when semantic not requested)
        elif expected_text:
            passed, similarity, _, _ = self.verify_fuzzy(
                wav_file, expected_text, fuzzy_threshold
            )
            results['tests']['fuzzy_match'] = {
                'passed': passed,
                'expected': expected_text,
                'similarity': similarity,
                'threshold': fuzzy_threshold
            }

        # Keyword matching
        if keywords:
            passed, matched, _, _ = self.verify_keywords(
                wav_file, keywords, min_matches=min_keyword_matches
            )
            results['tests']['keyword_match'] = {
                'passed': passed,
                'expected_keywords': keywords,
                'matched_keywords': matched,
                'match_count': f"{len(matched)}/{len(keywords)}",
                'min_required': min_keyword_matches if min_keyword_matches else len(keywords)
            }

        # Overall pass/fail
        all_passed = results['confidence_passed']
        for test_result in results['tests'].values():
            all_passed = all_passed and test_result['passed']

        results['overall_passed'] = all_passed

        return results


def main():
    """Command-line interface for audio verification."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify audio using Whisper STT")
    parser.add_argument('wav_file', type=str, help='WAV file to verify')
    parser.add_argument('--whisper-bin', type=str, default='./build/bin/main',
                       help='Path to Whisper main binary')
    parser.add_argument('--model', type=str, default='./models/ggml-base.en.bin',
                       help='Path to Whisper model')
    parser.add_argument('--expected', type=str, help='Expected transcription text')
    parser.add_argument('--keywords', type=str, nargs='+', help='Expected keywords')
    parser.add_argument('--fuzzy-threshold', type=float, default=0.85,
                       help='Fuzzy match threshold (0.0-1.0)')
    parser.add_argument('--min-confidence', type=float, default=0.0,
                       help='Minimum confidence threshold')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    verifier = AudioVerifier(
        whisper_bin=args.whisper_bin,
        model_path=args.model
    )

    wav_file = Path(args.wav_file)

    # Run verification
    results = verifier.verify(
        wav_file,
        expected_text=args.expected,
        keywords=args.keywords,
        fuzzy_threshold=args.fuzzy_threshold,
        min_confidence=args.min_confidence
    )

    # Print results
    print("\n" + "="*60)
    print("VERIFICATION RESULTS")
    print("="*60)
    print(f"File: {results['wav_file']}")
    print(f"Transcription: '{results['actual_text']}'")
    print(f"Confidence: {results['confidence']:.2%}")
    print()

    for test_name, test_result in results['tests'].items():
        status = "PASS" if test_result['passed'] else "FAIL"
        print(f"[{status}] {test_name}")
        for key, value in test_result.items():
            if key != 'passed':
                print(f"  {key}: {value}")
        print()

    overall = "PASSED" if results['overall_passed'] else "FAILED"
    print(f"Overall: {overall}")
    print("="*60)

    # Exit with appropriate code
    exit(0 if results['overall_passed'] else 1)


if __name__ == '__main__':
    main()
