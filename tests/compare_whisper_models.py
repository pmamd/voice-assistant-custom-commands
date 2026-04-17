#!/usr/bin/env python3
"""
Compare Whisper model accuracy: tiny.en vs base.en

This test runs the same test audio through both models to quantify
the accuracy improvement from the model upgrade.
"""

import sys
import time
from pathlib import Path
from difflib import SequenceMatcher

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from audio_verifier import AudioVerifier


class WhisperModelComparer:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.whisper_bin = project_root / "build/bin/main"

        # Model paths
        self.tiny_model = project_root / "whisper.cpp/models/ggml-tiny.en.bin"
        self.base_model = project_root / "talk-llama-fast/whisper.cpp/models/ggml-base.en.bin"

        # Test audio directory
        self.test_audio_dir = project_root / "tests/audio/inputs"

    def compare_models(self, wav_file: Path, expected_text: str):
        """Compare transcription accuracy between tiny and base models."""

        if not wav_file.exists():
            print(f"✗ Audio file not found: {wav_file}")
            return None

        print(f"\nTesting: {wav_file.name}")
        print(f"Expected: '{expected_text}'")
        print("-" * 70)

        results = {}

        # Test with tiny.en
        if self.tiny_model.exists():
            print("\n[1/2] Testing with tiny.en model...")
            verifier_tiny = AudioVerifier(
                whisper_bin=str(self.whisper_bin),
                model_path=str(self.tiny_model),
                use_semantic=False
            )

            start_time = time.time()
            tiny_text, tiny_conf = verifier_tiny.transcribe(wav_file)
            tiny_duration = (time.time() - start_time) * 1000

            tiny_similarity = SequenceMatcher(
                None,
                expected_text.lower(),
                tiny_text.lower()
            ).ratio()

            results['tiny'] = {
                'text': tiny_text,
                'confidence': tiny_conf,
                'similarity': tiny_similarity,
                'duration_ms': tiny_duration
            }

            print(f"  Transcribed: '{tiny_text}'")
            print(f"  Confidence: {tiny_conf:.2%}")
            print(f"  Similarity: {tiny_similarity:.2%}")
            print(f"  Duration: {tiny_duration:.0f}ms")
        else:
            print(f"✗ tiny.en model not found: {self.tiny_model}")

        # Test with base.en
        if self.base_model.exists():
            print("\n[2/2] Testing with base.en model...")
            verifier_base = AudioVerifier(
                whisper_bin=str(self.whisper_bin),
                model_path=str(self.base_model),
                use_semantic=False
            )

            start_time = time.time()
            base_text, base_conf = verifier_base.transcribe(wav_file)
            base_duration = (time.time() - start_time) * 1000

            base_similarity = SequenceMatcher(
                None,
                expected_text.lower(),
                base_text.lower()
            ).ratio()

            results['base'] = {
                'text': base_text,
                'confidence': base_conf,
                'similarity': base_similarity,
                'duration_ms': base_duration
            }

            print(f"  Transcribed: '{base_text}'")
            print(f"  Confidence: {base_conf:.2%}")
            print(f"  Similarity: {base_similarity:.2%}")
            print(f"  Duration: {base_duration:.0f}ms")
        else:
            print(f"✗ base.en model not found: {self.base_model}")

        # Compare results
        if 'tiny' in results and 'base' in results:
            print("\n" + "=" * 70)
            print("COMPARISON")
            print("=" * 70)

            sim_diff = (results['base']['similarity'] - results['tiny']['similarity']) * 100
            dur_diff = results['base']['duration_ms'] - results['tiny']['duration_ms']

            print(f"Similarity improvement: {sim_diff:+.1f}%")
            print(f"Duration difference: {dur_diff:+.0f}ms")

            if results['base']['similarity'] > results['tiny']['similarity']:
                print(f"✓ base.en is MORE ACCURATE ({results['base']['similarity']:.1%} vs {results['tiny']['similarity']:.1%})")
            elif results['base']['similarity'] < results['tiny']['similarity']:
                print(f"✗ tiny.en is more accurate ({results['tiny']['similarity']:.1%} vs {results['base']['similarity']:.1%})")
            else:
                print("= Both models have equal accuracy")

        return results

    def run_comparison_suite(self):
        """Run comparison on all test audio files."""
        print("=" * 70)
        print("WHISPER MODEL COMPARISON: tiny.en vs base.en")
        print("=" * 70)

        # Test cases: (filename, expected_text)
        test_cases = [
            ("story_request.wav", "tell me a story"),
            ("long_response_test.wav", "tell me about the history of the roman empire"),
        ]

        all_results = []

        for filename, expected in test_cases:
            wav_file = self.test_audio_dir / filename

            if not wav_file.exists():
                print(f"\n⚠ Skipping {filename} (not found)")
                continue

            result = self.compare_models(wav_file, expected)

            if result:
                all_results.append({
                    'filename': filename,
                    'expected': expected,
                    'results': result
                })

        # Summary
        if all_results:
            print("\n" + "=" * 70)
            print("SUMMARY")
            print("=" * 70)

            tiny_total_sim = 0
            base_total_sim = 0
            tiny_total_dur = 0
            base_total_dur = 0
            count = 0

            for item in all_results:
                results = item['results']
                if 'tiny' in results and 'base' in results:
                    tiny_total_sim += results['tiny']['similarity']
                    base_total_sim += results['base']['similarity']
                    tiny_total_dur += results['tiny']['duration_ms']
                    base_total_dur += results['base']['duration_ms']
                    count += 1

                    # Show per-test result
                    sim_diff = (results['base']['similarity'] - results['tiny']['similarity']) * 100
                    winner = "base" if results['base']['similarity'] > results['tiny']['similarity'] else "tiny" if results['tiny']['similarity'] > results['base']['similarity'] else "tie"

                    print(f"\n{item['filename']}:")
                    print(f"  Expected: '{item['expected']}'")
                    print(f"  tiny.en:  '{results['tiny']['text']}' ({results['tiny']['similarity']:.1%})")
                    print(f"  base.en:  '{results['base']['text']}' ({results['base']['similarity']:.1%})")
                    print(f"  Winner: {winner} ({sim_diff:+.1f}% similarity)")

            if count > 0:
                avg_tiny_sim = tiny_total_sim / count
                avg_base_sim = base_total_sim / count
                avg_tiny_dur = tiny_total_dur / count
                avg_base_dur = base_total_dur / count

                print("\n" + "=" * 70)
                print("OVERALL AVERAGES")
                print("=" * 70)
                print(f"tiny.en:  {avg_tiny_sim:.1%} similarity, {avg_tiny_dur:.0f}ms avg")
                print(f"base.en:  {avg_base_sim:.1%} similarity, {avg_base_dur:.0f}ms avg")
                print(f"\nImprovement: {(avg_base_sim - avg_tiny_sim) * 100:+.1f}% similarity")
                print(f"Latency cost: {avg_base_dur - avg_tiny_dur:+.0f}ms avg")

                # Verdict
                print("\n" + "=" * 70)
                print("VERDICT")
                print("=" * 70)

                if avg_base_sim > avg_tiny_sim:
                    improvement = (avg_base_sim - avg_tiny_sim) * 100
                    print(f"✓ base.en provides {improvement:.1f}% better accuracy")
                    print(f"  Trade-off: +{avg_base_dur - avg_tiny_dur:.0f}ms latency")

                    if avg_base_dur < 1000:
                        print(f"  Conclusion: GOOD TRADE-OFF (latency still < 1s)")
                    elif avg_base_dur < 2000:
                        print(f"  Conclusion: ACCEPTABLE (latency < 2s)")
                    else:
                        print(f"  Conclusion: May be too slow for real-time use")
                else:
                    print("✗ No accuracy improvement detected")
                    print("  Consider staying with tiny.en for lower latency")
        else:
            print("\n⚠ No test files found to compare")
            print(f"  Test audio directory: {self.test_audio_dir}")
            print(f"\n  To generate test audio, run:")
            print(f"    python3 tests/test_tool_audio.py")

        return 0 if all_results else 1


def main():
    """Main entry point."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    print(f"Project root: {project_root}\n")

    comparer = WhisperModelComparer(project_root)
    return comparer.run_comparison_suite()


if __name__ == "__main__":
    sys.exit(main())
