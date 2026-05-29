# Voice Assistant Test Harness

Comprehensive end-to-end testing framework for the voice assistant audio pipeline (Whisper STT → LLaMA → Piper TTS).

![Test Harness Architecture](./test-harness-architecture.svg)

## Overview

This test harness provides automated verification of the complete voice assistant pipeline:
1. **Audio Generation**: Synthetic speech input using Piper TTS
2. **Speech Recognition**: Whisper STT transcription
3. **Response Generation**: LLaMA language model inference
4. **Text-to-Speech**: Piper TTS via Wyoming protocol
5. **Output Verification**: Whisper STT verification with fuzzy matching

## Architecture

### Components

#### 1. Audio Generator (`audio_generator.py`)
Generates synthetic test audio files using Piper TTS.

**Features**:
- Batch generation from test cases
- Support for multiple voices
- Configurable output directory
- WAV format (22.05kHz, 16-bit, mono)

**Usage**:
```python
from audio_generator import AudioGenerator

generator = AudioGenerator(
    piper_bin="./piper/piper",
    model_dir="./piper-voices",
    output_dir="./tests/audio/inputs"
)

wav_file = generator.generate("Hello assistant", voice="en_US-lessac-medium")
```

#### 2. Audio Verifier (`audio_verifier.py`)
Verifies TTS output using Whisper STT transcription.

**Features**:
- Automatic audio resampling (22kHz → 16kHz for Whisper)
- Multiple verification methods:
  - Exact text matching
  - Fuzzy text matching (configurable threshold)
  - Keyword presence checking
- Confidence score extraction from Whisper
- Comprehensive result reporting

**Usage**:
```python
from audio_verifier import AudioVerifier

verifier = AudioVerifier(
    whisper_bin="./build/bin/main",
    model_path="./models/ggml-base.en.bin"
)

# Verify with fuzzy matching
passed, similarity, text, confidence = verifier.verify_fuzzy(
    wav_file="output.wav",
    expected_text="Hello! How can I help you?",
    threshold=0.85
)

# Verify keywords
passed, matched, text, confidence = verifier.verify_keywords(
    wav_file="output.wav",
    keywords=["hello", "help"]
)
```

#### 3. Test Orchestrator (`run_tests.py`)
Main test runner that coordinates all components.

**Features**:
- Async test execution
- Wyoming-Piper server management (auto-start/stop)
- Parallel test support
- Timeout handling
- Test retries on failure
- Comprehensive reporting (JSON + text)
- Test grouping (smoke, functional, command, quality, performance)

**Usage**:
```bash
# Run all tests (recommended - uses venv if available)
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --group all

# Run specific test group
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --group smoke

# Run with verbose output
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --group all -v

# Run single test
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --test simple_greeting

# NPU configuration (for AMD RDNA3 iGPU builds)
bash tests/run_tests_venv.sh --config tests/test_cases_npu.yaml --group all
```

#### 4. Test Wrapper (`run_tests_venv.sh`)
Wrapper script that activates Python venv if available for semantic similarity support.

**Usage**:
```bash
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --group all
```

**Features**:
- Auto-activates venv if present
- Falls back to system Python if venv not found
- Enables semantic similarity matching with sentence-transformers

#### 5. Test Configuration (`test_cases.yaml`)
Defines all test cases and configuration.

**Test Case Structure**:
```yaml
test_cases:
  - name: "test_name"
    description: "What this test does"
    input: "Text to speak"
    verification_method: "semantic"  # or "fuzzy"
    expected_response: "Expected LLM response"
    semantic_threshold: 0.55  # Similarity threshold for semantic matching
    min_confidence: 0.70      # Whisper confidence threshold
    test_type: "functional"
```

**Test Types**:
- `functional`: Basic speech-to-response pipeline
- `command`: Custom command routing (stop, pause, resume)
- `interrupt`: Multi-step tests (stop during TTS)
- `quality`: Transcription accuracy
- `performance`: Latency and throughput
- `multi_turn`: Conversation flows
- `vad_validation`: VAD split-utterance detection

## Setup

### Prerequisites

**System Requirements**:
- Python 3.9+
- ffmpeg (for audio resampling)
- Build server access (for model files)

**Python Dependencies**:
```bash
# Create virtualenv for semantic similarity support
python3 -m venv venv
source venv/bin/activate
pip install pyyaml sentence-transformers scikit-learn
```

**Models Required**:
- Whisper model: `./external/whisper.cpp/models/ggml-small.en.bin` (GPU) or `ggml-small.bin` (NPU with --language en)
- LLM: Mistral recommended via llama-server on port 8080
- Piper voice: Installed via `pipx install piper-tts==1.4.1` and downloaded to `./piper-data/`

### Directory Structure

```
tests/
├── README.md                          # This file
├── test-harness-architecture.svg      # Architecture diagram
├── audio_generator.py                 # Piper TTS generator
├── audio_verifier.py                  # Whisper STT verifier
├── run_tests.py                       # Main test orchestrator
├── test_cases.yaml                    # Test definitions
├── audio/
│   ├── inputs/                        # Generated test audio
│   └── outputs/                       # TTS output for verification
├── config/                            # Additional configuration
└── results/                           # Test results and reports
    ├── test_report.json
    └── test_report.txt
```

### Build Requirements

**voice-assistant** with test mode:
```bash
cmake -B build -DWHISPER_SDL2=ON
cmake --build build -j
```

Binary location: `./build/bin/voice-assistant`

**Wyoming-Piper** with test mode:
```bash
cd wyoming-piper
pip install -e .
```

## Test Mode Features

### voice-assistant Test Mode

The `voice-assistant` binary supports test mode for automated testing:

**Parameter**: `--test-input <wav_file>`

**Behavior**:
- Injects audio from file instead of microphone
- Skips warmup transcription (preserves audio buffer)
- Skips thread joins (prevents hanging)
- Exits cleanly after processing

**Example**:
```bash
./build/bin/voice-assistant \
    --test-input tests/audio/inputs/hello.wav \
    -mw ./external/whisper.cpp/models/ggml-small.en.bin \
    --llama-url http://localhost:8080 \
    --temp 0.0 \
    -n 500
```

### Wyoming-Piper Test Mode

The Wyoming-Piper TTS server supports test mode:

**Parameters**:
- `--test-mode`: Enable test mode (save audio instead of playing)
- `--test-output-dir <path>`: Where to save audio files

**Behavior**:
- Saves TTS output to files instead of playing via aplay
- Creates timestamped files: `output_<timestamp>_<counter>.wav`
- Maintains symlink `output.wav` → latest file
- Preserves audio for verification

**Example**:
```bash
wyoming-piper-custom \
    --piper ~/.local/bin/piper \
    --voice en_US-lessac-medium \
    --data-dir ./piper-data \
    --uri tcp://0.0.0.0:10200 \
    --test-mode \
    --test-output-dir ./tests/audio/outputs
```

## Running Tests

### Quick Start

```bash
# 1. Ensure llama-server is running
# (start-assistant.sh does this, or start manually on port 8080)

# 2. Run tests (auto-starts Wyoming-Piper in test mode)
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --group smoke

# 3. View results
ls -lt tests/results/*.txt | head -1 | awk '{print $NF}' | xargs cat
```

### Test Groups

Run specific test groups:

```bash
# Smoke tests (quick validation)
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --group smoke

# Functional tests (basic pipeline)
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --group functional

# Command tests (stop, exit commands)
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --group command

# Quality tests (transcription accuracy)
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --group quality

# VAD validation tests
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --group vad

# All tests
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --group all
```

### Individual Tests

```bash
# Run single test
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --test simple_greeting

# Run with verbose logging
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --test simple_greeting -v

# Run multiple specific tests
bash tests/run_tests_venv.sh --config tests/test_cases.yaml --test simple_greeting question_response
```

### Configuration Options

Edit `test_cases.yaml` to customize:

```yaml
config:
  # Audio generation
  audio_generator:
    piper_bin: "./piper/piper"
    model_dir: "./piper-voices"
    default_voice: "en_US-lessac-medium"
    output_dir: "./tests/audio/inputs"

  # System under test
  talk_llama:
    binary: "./build/bin/voice-assistant"
    whisper_model: "./external/whisper.cpp/models/ggml-small.en.bin"
    llama_url: "http://localhost:8080"
    temperature: 0.0  # Deterministic for repeatable tests
    max_tokens: 500   # Allow longer responses
    test_mode: true

  # Audio verification
  audio_verifier:
    whisper_bin: "./build/bin/whisper-cli"
    whisper_model: "./external/whisper.cpp/models/ggml-small.en.bin"
    output_dir: "./tests/audio/outputs"

  # Wyoming-Piper TTS server
  wyoming_piper:
    command: "~/.local/bin/wyoming-piper-custom"
    args:
      - "--piper"
      - "~/.local/bin/piper"
      - "--voice"
      - "en_US-lessac-medium"
      - "--data-dir"
      - "./piper-data"
      - "--uri"
      - "tcp://0.0.0.0:10200"
      - "--test-mode"
      - "--test-output-dir"
      - "./tests/audio/outputs"
    port: 10200
    auto_start: true

  # Test execution
  execution:
    timeout_per_test: 360  # seconds
    retry_on_failure: 1
    parallel_execution: false
    verbose: true

  # Pass/fail criteria
  criteria:
    default_min_confidence: 0.65
    default_fuzzy_threshold: 0.85
    default_keyword_match_ratio: 0.30  # 30% of keywords must match
```

## Test Cases

### Functional Tests

**simple_greeting**:
- Input: "Hello assistant"
- Expected: Contains ["hello", "hi", "greetings"]
- Verifies: Basic greeting recognition

**question_response**:
- Input: "What is two plus two"
- Expected: Contains ["four", "4"]
- Verifies: Question answering capability

### Command Tests

**stop_command_basic**:
- Input: "Stop"
- Expected: Immediate stop, no LLM processing
- Verifies: Command detection and routing

**stop_command_variations**:
- Inputs: ["Stop", "stop", "STOP"]
- Expected: All trigger stop behavior
- Verifies: Case-insensitive command handling

### Interrupt Tests

**stop_interrupt_long_response**:
- Multi-step test sequence:
  1. Request long response: "Tell me a story..."
  2. Wait for TTS to start (2 seconds)
  3. Send stop command: "Stop"
  4. Verify TTS interrupts within 500ms
  5. Verify system responsive: "Are you there"
- Verifies: Real-time interrupt handling

### Quality Tests

**clear_speech**:
- Input: "The quick brown fox jumps over the lazy dog"
- Expected: 90% fuzzy match
- Verifies: Transcription accuracy

**numbers**:
- Input: "Count from one to five"
- Expected: Contains ["one", "two", "three", "four", "five"]
- Verifies: Number recognition

### Performance Tests

**latency_test**:
- Input: "Hi"
- Max latency: 5000ms
- Verifies: End-to-end response time

## Verification Methods

### 1. Exact Match
Direct string comparison (case-insensitive):
```python
if actual.lower() == expected.lower():
    return PASS
```

### 2. Fuzzy Match
Uses difflib.SequenceMatcher for similarity:
```python
similarity = SequenceMatcher(None, expected.lower(), actual.lower()).ratio()
if similarity >= threshold:  # default: 0.85
    return PASS
```

### 3. Keyword Match
Checks for presence of keywords:
```python
matched = [kw for kw in keywords if kw.lower() in actual.lower()]
if len(matched) >= min_matches:
    return PASS
```

### 4. Semantic Similarity
Uses sentence-transformers (all-MiniLM-L6-v2) for meaning-based comparison:
```python
from sentence_transformers import SentenceTransformer
embeddings = model.encode([expected, actual])
similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
if similarity >= threshold:  # default: 0.70
    return PASS
```

**Note**: Requires venv with sentence-transformers installed. Falls back to fuzzy matching if not available.

### 5. Confidence Score
Uses Whisper token probabilities:
```python
avg_confidence = sum(token_probs) / len(tokens)
if avg_confidence >= min_confidence:  # default: 0.65
    return PASS
```

## Output and Reporting

### Console Output
```
Running tests...
[PASS] simple_greeting (1234ms)
  Transcription: "Good morning, how can I assist you?"
  Similarity: 87%
  Keywords: 2/3 matched

[FAIL] long_response (8179ms)
  Error: talk-llama crashed (exit code -6)

Summary: 1 passed, 1 failed (2 total)
```

### JSON Report
```json
{
  "timestamp": "2026-02-19T20:47:00",
  "total": 2,
  "passed": 1,
  "failed": 1,
  "duration_ms": 9413,
  "results": [
    {
      "name": "simple_greeting",
      "passed": true,
      "duration_ms": 1234,
      "actual_text": "Good morning, how can I assist you?",
      "confidence": 0.87,
      "similarity": 0.87,
      "matched_keywords": ["hello", "assist"]
    }
  ]
}
```

### Text Report
Detailed report saved to `tests/results/test_report.txt`:
```
================================================================
VOICE ASSISTANT TEST REPORT
================================================================
Date: 2026-02-19 20:47:00
Total: 2 | Passed: 1 | Failed: 1

[PASS] simple_greeting
  Duration: 1234ms
  Input: "Hello assistant"
  Output: "Good morning, how can I assist you?"
  Confidence: 87%
  Similarity: 87%
  Keywords: 2/3 matched [hello, assist]

[FAIL] long_response
  Duration: 8179ms
  Input: "Tell me a story about a robot"
  Error: talk-llama crashed (exit code -6)

================================================================
```

## Troubleshooting

### Common Issues

**Wyoming-Piper connection refused**:
```bash
# Check if server is running
netstat -tuln | grep 10200

# Start server manually
wyoming-piper --piper ./piper/piper --voice en_US-lessac-medium \
    --data-dir ./piper-voices --uri tcp://0.0.0.0:10200 \
    --test-mode --test-output-dir ./tests/audio/outputs
```

**Whisper transcription errors**:
```bash
# Check model path
ls -lh external/whisper.cpp/models/ggml-small.en.bin

# Test Whisper directly
./build/bin/whisper-cli -m external/whisper.cpp/models/ggml-small.en.bin -f test.wav
```

**Audio resampling failures**:
```bash
# Check ffmpeg installation
ffmpeg -version

# Install if missing
sudo apt-get install ffmpeg
```

**Test timeouts**:
- Increase timeout in `test_cases.yaml`:
  ```yaml
  config:
    execution:
      timeout_per_test: 600  # 10 minutes
  ```
- Check GPU availability (ROCm for AMD GPUs)
- Use smaller models for faster inference

**Empty transcriptions**:
- Verify audio file is not silent:
  ```bash
  ffplay tests/audio/outputs/output.wav
  ```
- Check Whisper model compatibility
- Ensure test mode is enabled in Wyoming-Piper

### Debug Mode

Enable verbose logging:
```bash
# Python logging
python3 tests/run_tests.py --verbose

# talk-llama debug output
./build/bin/voice-assistant --test-input test.wav -d

# Wyoming-Piper debug
wyoming-piper --debug ...
```

## Known Issues

1. **Long Response Crashes**: voice-assistant crashes when generating responses longer than ~100 tokens
   - **Status**: Application bug, not test harness issue
   - **Workaround**: Use shorter prompts or skip long_response test

2. **Sample Rate Mismatch**: Piper generates 22.05kHz, Whisper requires 16kHz
   - **Status**: Fixed via automatic resampling in audio_verifier.py
   - **Impact**: None (transparent to users)

3. **Test Flakiness**: LLM responses can vary slightly
   - **Status**: By design
   - **Mitigation**: Use fuzzy matching and keyword verification

## Performance Benchmarks

Typical test execution times on AMD Radeon PRO W6800 (ROCm):

| Test Type | Duration | Notes |
|-----------|----------|-------|
| simple_greeting | ~1-2s | Fast, minimal LLM tokens |
| question_response | ~2-3s | Short Q&A response |
| stop_command_basic | ~0.5s | Bypasses LLM |
| long_response | ~8s+ | May crash (known issue) |
| Full test suite | ~30-60s | Depends on test count |

## Contributing

### Adding New Tests

1. Add test case to `test_cases.yaml`:
```yaml
test_cases:
  - name: "my_new_test"
    description: "Test description"
    input: "Input text"
    expected_contains: ["keyword1", "keyword2"]
    min_confidence: 0.80
    test_type: "functional"
```

2. Add to appropriate test group:
```yaml
test_groups:
  functional:
    - "my_new_test"
```

3. Run and verify:
```bash
python3 tests/run_tests.py --test my_new_test
```

### Test Best Practices

- **Keep inputs short**: Reduces LLM crash risk
- **Use fuzzy matching**: LLM outputs vary
- **Set realistic thresholds**: 80-85% similarity is good
- **Test edge cases**: Empty strings, special characters
- **Document expected behavior**: Clear descriptions

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Voice Assistant Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          submodules: recursive

      - name: Install dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y libsdl2-dev ffmpeg
          pip install pyyaml

      - name: Build
        run: |
          cmake -B build -DWHISPER_SDL2=ON
          cmake --build build -j

      - name: Run smoke tests
        run: |
          python3 tests/run_tests.py --group smoke

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: tests/results/
```

## Architecture Details

### Test Flow Sequence

```
1. Test Orchestrator (run_tests.py)
   ↓
2. Load test_cases.yaml
   ↓
3. Start Wyoming-Piper server (if auto_start enabled)
   ↓
4. For each test case:
   a. Generate test audio (audio_generator.py + Piper TTS)
   b. Inject into voice-assistant (--test-input)
   c. Whisper STT → LLaMA → Wyoming-Piper TTS
   d. Wyoming-Piper saves output.wav (test mode)
   e. Verify output.wav (audio_verifier.py + Whisper STT)
   f. Compare with expected results
   g. Record pass/fail
   ↓
5. Generate report (JSON + text)
   ↓
6. Stop Wyoming-Piper server
   ↓
7. Exit with status code (0 = all passed, 1 = failures)
```

### Critical Fixes

**Warmup Transcription Bug**:
- **Problem**: Whisper was called twice (warmup + real), consuming test audio
- **Fix**: Skip warmup transcription in test mode
- **Location**: `src/talk-llama.cpp:1950`
- **Impact**: Essential for test mode to work

**Thread Blocking**:
- **Problem**: Thread joins waiting for keyboard input that never comes
- **Fix**: Skip thread joins in test mode
- **Location**: `src/talk-llama.cpp:3022-3029`
- **Impact**: Prevents test hangs

**Audio Resampling**:
- **Problem**: Piper outputs 22kHz, Whisper expects 16kHz
- **Fix**: Automatic ffmpeg resampling in verifier
- **Location**: `tests/audio_verifier.py:_ensure_16khz()`
- **Impact**: Transparent compatibility

## Credits

- **Test Harness Design**: Paul Mobbs (2026)
- **Implementation**: Claude Opus 4.6 (2026)
- **Whisper.cpp**: Georgi Gerganov
- **Piper TTS**: Rhasspy project
- **Wyoming Protocol**: Rhasspy project

## License

Part of the voice-assistant-custom-commands project.
