# Tool System Test Suite

Additional test cases specifically for the Mistral tool calling implementation.

## Test Categories

### 1. Fast Path Tool Tests
Tests for keyword-based tool execution (< 100ms latency)

**Commands tested:**
- `stop` and variations (quiet, silence, shut up)
- `pause` and variations (hold on, wait, hold up)
- `resume` and variations (continue, go ahead, go on)

**What's verified:**
- ✅ Keyword matching works correctly
- ✅ Tool executes within 100ms
- ✅ Wyoming event sent (audio-stop, audio-pause, audio-resume)
- ✅ No LLM processing required

**Example test:**
```yaml
- name: "tool_stop_fast_path"
  input: "Stop"
  expected_behavior: "fast_path_tool_execution"
  tool_name: "stop_speaking"
  verify_wyoming_event: "audio-stop"
  max_execution_time_ms: 100
```

### 2. Pause/Resume Sequence Tests
Tests for pause and resume functionality during active TTS

**Scenarios:**
- Pause during long response
- Verify TTS stays paused
- Resume and continue playback
- System responsive after pause/resume

**Example test:**
```yaml
- name: "tool_pause_resume_sequence"
  sequence:
    - Send long prompt
    - Wait for TTS to start
    - Send "pause" → verify paused
    - Wait 3 seconds → verify still paused
    - Send "resume" → verify resumed
```

### 3. LLM-Driven Tool Tests
Tests for natural language tool calling via Mistral

**Tools tested:**
- `set_temperature` - "Make it warmer", "Set temp to 72"
- `set_fan_speed` - "Turn fan to high"
- `enable_defrost` - "Turn on front defrost"
- `navigate_to` - "Navigate home", "Go to 123 Main St"
- `find_nearby` - "Find nearby gas stations"
- `get_eta` - "What's my ETA"
- `check_tire_pressure` - "Check tire pressure"
- `get_fuel_range` - "How much fuel do I have"
- `check_vehicle_status` - "Check vehicle status"

**What's verified:**
- ✅ LLM generates `<tool_call>` tag
- ✅ Tool call has correct format
- ✅ Arguments extracted properly
- ✅ Tool executes successfully
- ✅ Response includes tool results

**Example test:**
```yaml
- name: "tool_set_temperature_basic"
  input: "Make it warmer"
  expected_behavior: "llm_tool_call"
  tool_name: "set_temperature"
  expected_tool_args: ["value"]
  expected_response_contains: ["temperature", "set"]
```

### 4. Tool Call Parser Tests
Unit tests for Mistral `<tool_call>` format parser

**What's tested:**
- Valid tool call parsing
- Tool calls mixed with normal text
- Incremental token-by-token parsing
- Text separation (tool tags vs normal text)

**Example test:**
```yaml
- name: "tool_call_parser_with_text"
  input_tokens: [
    "Sure, I'll help",
    "<tool_call>",
    '{"name":"set_temperature","arguments":{"value":72}}',
    "</tool_call>",
    "Temperature is set."
  ]
  expected_normal_text: "Sure, I'll help Temperature is set."
  expected_tool_call: {name: "set_temperature"}
```

### 5. Error Handling Tests
Tests for invalid inputs and edge cases

**Scenarios:**
- Invalid argument values (temp too high/low)
- Missing required arguments
- Malformed tool calls
- LLM recovery from errors

**Example test:**
```yaml
- name: "tool_invalid_arguments"
  input: "Set temperature to 200 degrees"
  tool_name: "set_temperature"
  expected_tool_execution: "failure"
  expected_response_contains: ["error", "valid", "range"]
```

### 6. Regression Tests
Ensure normal operation isn't affected by tool system

**What's verified:**
- Normal conversation doesn't trigger tools
- "stop" in middle of sentence doesn't trigger fast path
- Regular questions answered normally
- No performance degradation

**Example test:**
```yaml
- name: "tool_no_false_positives"
  input: "Hello, how are you today?"
  expected_behavior: "normal_response"
  verify_no_tool_call: true
```

## Test Groups

### Smoke Tests (tool_smoke)
Quick verification that basic tool functionality works:
- stop_fast_path
- pause_fast_path
- resume_fast_path
- set_temperature_basic
- navigate_to_home

**Runtime:** ~2-3 minutes

### Fast Path Tests (tool_fast_path)
All keyword-based tool tests:
- Stop variations (5 tests)
- Pause variations (4 tests)
- Resume variations (4 tests)

**Runtime:** ~1-2 minutes

### Automotive Tests (tool_automotive)
All LLM-driven automotive tool tests:
- Temperature control (2 tests)
- Fan speed (1 test)
- Defrost (1 test)
- Navigation (2 tests)
- Find nearby (1 test)
- Vehicle status (4 tests)

**Runtime:** ~10-15 minutes (LLM inference)

### All Tool Tests (tool_all)
Complete tool system test suite:
- 31 total tests
- All categories covered

**Runtime:** ~20-30 minutes

## Running Tests

### Run specific test group:
```bash
# Fast path tests only (quick)
python3 tests/run_tests.py --config tests/test_cases_tool_system.yaml --group tool_fast_path

# Automotive tools only
python3 tests/run_tests.py --config tests/test_cases_tool_system.yaml --group tool_automotive

# Smoke tests (fastest validation)
python3 tests/run_tests.py --config tests/test_cases_tool_system.yaml --group tool_smoke

# All tool tests
python3 tests/run_tests.py --config tests/test_cases_tool_system.yaml --group tool_all
```

### Run single test:
```bash
python3 tests/run_tests.py --config tests/test_cases_tool_system.yaml --test tool_stop_fast_path
```

### Run with verbose output:
```bash
python3 tests/run_tests.py --config tests/test_cases_tool_system.yaml --group tool_smoke --verbose
```

## Integration with Existing Tests

The tool system tests complement the existing test suite:

**Existing tests** (`test_cases.yaml`):
- Basic STT → LLM → TTS pipeline
- Old hardcoded "stop" command
- General conversation quality

**New tool tests** (`test_cases_tool_system.yaml`):
- New tool-based stop/pause/resume
- Automotive tool calling
- Mistral tool call format
- Fast path vs LLM-driven execution

**Combined testing:**
```bash
# Run both test suites
python3 tests/run_tests.py --config tests/test_cases.yaml --group smoke
python3 tests/run_tests.py --config tests/test_cases_tool_system.yaml --group tool_smoke
```

## Expected Results

### Fast Path Tests
- **Latency:** < 100ms from keyword to tool execution
- **Success Rate:** 100% (deterministic keyword matching)
- **Wyoming Events:** All events sent successfully

### LLM-Driven Tests
- **Latency:** 2-5 seconds (includes LLM inference)
- **Success Rate:** 80-95% (LLM variance in phrasing)
- **Tool Format:** Valid `<tool_call>` JSON

### Parser Tests
- **Success Rate:** 100% (deterministic parsing)
- **Text Separation:** Clean text with no tool tags

### Regression Tests
- **False Positives:** 0% (no unintended tool triggers)
- **Normal Operation:** Unchanged from baseline

## Test Metrics

Key metrics to monitor:

1. **Fast Path Latency:** Should be < 100ms
2. **Tool Call Success Rate:** Should be > 90%
3. **Wyoming Event Delivery:** Should be 100%
4. **Parser Accuracy:** Should be 100%
5. **False Positive Rate:** Should be 0%

## Debugging Failed Tests

### Fast Path Test Fails
1. Check keyword matching in tool-system.cpp
2. Verify tools.json has correct keywords
3. Check fast_path flag is true

### LLM Tool Test Fails
1. Check if LLM generated tool call at all
2. Verify tool call format (Mistral `<tool_call>` syntax)
3. Check if arguments match schema
4. Verify tools injected into system prompt

### Parser Test Fails
1. Check parser state machine
2. Verify incremental token processing
3. Check text separation logic

### Wyoming Event Test Fails
1. Check Wyoming-Piper is running
2. Verify Wyoming client connection
3. Check event format (JSON)
4. Review Wyoming-Piper logs

## Contributing New Tests

When adding new tools or functionality:

1. Add test case to `test_cases_tool_system.yaml`
2. Choose appropriate test_type:
   - `tool_fast_path` - for keyword-based tools
   - `tool_llm_driven` - for natural language tools
   - `tool_parser_unit` - for parser-specific tests
3. Define expected behavior and verification criteria
4. Add to relevant test group
5. Run test to verify it passes
6. Update this README with new test info

## Test Coverage

Current coverage:

- ✅ All 12 tools (3 voice control + 9 automotive)
- ✅ Fast path keyword matching
- ✅ LLM-driven tool calling
- ✅ Tool call parser (Mistral format)
- ✅ Wyoming event sending
- ✅ Error handling
- ✅ Regression tests

Missing coverage (future work):

- ⏳ Multi-tool conversations (tool chaining)
- ⏳ Concurrent tool execution
- ⏳ Tool timeout handling
- ⏳ Network failure scenarios
- ⏳ Performance benchmarks
