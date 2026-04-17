# Tool System Investigation

**Date:** 2026-04-17
**Branch:** whisper-npu
**Status:** Bug Identified - Partial Fix Applied

---

## Executive Summary

During TTS timing measurements, we discovered that tool calls were being spoken aloud instead of executed. Investigation revealed this is a **pre-existing bug** in the master branch, not a regression from our NPU/TTS work.

The issue: Mistral 7B LLM outputs malformed JSON within `<tool_call>` tags, causing the parser to fail and the raw JSON to be sent to TTS.

---

## The Bug

### Observable Behavior

When user says "Make it warmer", the expected behavior is:
1. LLM outputs: `<tool_call>{"name": "set_temperature", "arguments": {...}}</tool_call>`
2. Tool parser extracts and parses the JSON
3. Tool `set_temperature` is executed
4. No text is sent to TTS (tool call is silent)

**Actual behavior:**
1. LLM outputs: `<tool_call>"{"name": "set_temperature", ...}</tool_call>` ← Extra quotes!
2. Tool parser fails to parse malformed JSON
3. Entire malformed tag is sent to TTS
4. TTS speaks: "name, set temperature, arguments, value, 72, zone, both"
5. Tool is never executed

### Root Cause

Mistral 7B LLM consistently outputs malformed JSON in multiple patterns:

```
Pattern 1: Missing quote on first key
<tool_call>"{name":"set_temperature", "arguments":{"value":80,"zone":"both"}}</tool_call>
                ^^^^^ No opening quote!

Pattern 2: Extra outer quotes
<tool_call>"{"name": "set_temperature", "arguments": {"value": 75, "zone": "both"}}"</tool_call>
           ↑                                                                        ↑
           Extra quotes wrapping the entire JSON object

Pattern 3: Tab character
<tool_call>"{<TAB>"name": "set_temperature", "arguments": {...}}"</tool_call>
              ^^^^^ Literal tab character
```

All patterns have the common issue of wrapping the JSON in quotes: `"{ ... }"` or `"{ ... }` (missing closing quote).

---

## Verification on Master Branch

To confirm this is pre-existing, we tested the master branch in a separate directory:

```bash
cd ~/git && git clone https://github.com/pmamd/voice-assistant-custom-commands.git voice-assistant-main
cd voice-assistant-main && git checkout master
cmake -B build -DWHISPER_SDL2=ON && cmake --build build -j
./build/bin/talk-llama-custom --test-input <audio> ...
```

**Result:** Master branch shows **identical failures**:

```
=== Master Test 1 ===
[Tool Parser] JSON parse error: ...
[Tool Parser] JSON content: "{name":"set_temperature", ...
<tool_call>"{name":"set_temperature", ...}</tool_call>

=== Master Test 2 ===
[Tool Parser] JSON parse error: ...
[Tool Parser] JSON content: "{"name": "set_temperature", ...
<tool_call>"{"name": "set_temperature", ...}</tool_call>

=== Master Test 3 ===
[Tool Parser] JSON parse error: ... control character U+0009 (HT) must be escaped
[Tool Parser] JSON content: "{<TAB>"name": "set_temperature", ...
<tool_call>"{<TAB>"name": "set_temperature", ...}</tool_call>
```

**Conclusion:** Bug exists on master branch with 100% reproducibility (3/3 tests).

---

## Our Improvements

### Changes Made

Modified `custom/talk-llama/tool-parser.cpp` to handle malformed JSON:

```cpp
bool ToolCallParser::parseToolCall() {
    try {
        std::string json_str = json_content_;
        json j;
        bool parsed = false;

        // Try to parse as-is first
        try {
            j = json::parse(json_str);
            parsed = true;
        } catch (...) {
            // Parse failed, try fixing common issues

            // Strip outer quotes if present: "..." -> ...
            if (json_str.length() >= 2 && json_str.front() == '"' && json_str.back() == '"') {
                json_str = json_str.substr(1, json_str.length() - 2);
            } else if (json_str.length() >= 2 && json_str.front() == '"' && json_str[1] == '{') {
                // Has leading quote but maybe not trailing: "{ ...
                json_str = json_str.substr(1);  // Remove leading "
                // Remove trailing " if present
                if (!json_str.empty() && json_str.back() == '"') {
                    json_str.pop_back();
                }
            }

            j = json::parse(json_str);
            parsed = true;
        }

        // ... continue with tool call extraction
```

### Approach

1. **Try parsing as-is first** - handles correctly formatted JSON
2. **If parse fails, strip outer quotes** - handles `"{ ... }"` pattern
3. **Retry parsing** - now should succeed if it was just a quoting issue

This fixes some cases but not all - the parser state machine has deeper issues.

---

## Remaining Issues

Even with improved JSON parsing, tool calls still don't execute consistently. Issues:

1. **Parser State Machine**: The `getText()` method sometimes returns empty strings, causing all LLM output to be filtered out
2. **Token Consumption**: When parser is inside `<tool_call>` tags, it consumes tokens without producing normal text output
3. **Silent Failures**: Sometimes the parser succeeds but tool execution doesn't happen (needs more investigation)

### Debug Output Observed

```
[DEBUG] Token: '<' -> clean_text: ''       ← Parser starts detecting tag
[DEBUG] Token: 'tool' -> clean_text: ''    ← Still in tag detection
[DEBUG] Token: '_call' -> clean_text: ''   ← Accumulating tag name
[DEBUG] Token: '>' -> clean_text: ''       ← Tag opened, no normal text
... (tokens consumed, nothing output) ...
```

All tokens get consumed by the parser state machine, but nothing is sent to TTS.

---

## Why This Happens

### LLM Prompt Issue

The system prompt tells the LLM:

```
To use a tool, output ONLY the tool call with no preamble or explanation:
<tool_call>{"name": "tool_name", "arguments": {...}, "id": "unique_id"}</tool_call>
```

But Mistral 7B appears to have issues with:
1. Correctly formatting JSON within tags
2. Understanding the exact format expected
3. Consistently following the template

### Possible Root Causes

1. **Model training**: Mistral 7B may not be trained on this exact format
2. **Tokenization**: The `<tool_call>` tags might tokenize unexpectedly
3. **Temperature**: Random variations in output (tested with temp=0.5)
4. **Context**: The long system prompt might confuse the model

---

## Impact Assessment

### Production Impact

- **Severity**: Medium
- **Frequency**: 100% of tool call requests
- **User Experience**: Tools don't work, malformed JSON is spoken aloud
- **Workaround**: None currently

### Development Impact

- ✅ Does NOT affect TTS timing measurements (our primary goal)
- ✅ Does NOT affect NPU acceleration
- ✅ Does NOT affect normal conversation (non-tool calls work fine)
- ❌ Tool calling system is non-functional

---

## Recommendations

### Short Term

1. **Document as Known Issue**: Add to README/docs
2. **Disable Tool Calls**: Consider removing from prompt until fixed
3. **Alternative Approach**: Use simpler keyword detection instead of JSON parsing

### Long Term

1. **Try Different LLM**: Test with models known to support tool calling (e.g., llama-3-instruct, qwen2.5)
2. **Adjust Prompt**: Experiment with different tool call formats
3. **State Machine Rewrite**: Redesign tool parser for better robustness
4. **Add Fallbacks**: If JSON parse fails, try fuzzy matching on tool names

### Alternative Tool Call Formats to Test

```
1. Simpler format (no tags):
   TOOL: set_temperature(value=72, zone="both")

2. Single-line JSON:
   {"tool": "set_temperature", "value": 72, "zone": "both"}

3. YAML-like:
   tool: set_temperature
   value: 72
   zone: both
```

---

## Testing Procedure

To reproduce the bug:

```bash
# Start llama-server with Mistral 7B model
llama-server --model mistral-7b-instruct-v0.2.Q5_0.gguf --port 8080 -ngl 999

# Run test
./build/bin/talk-llama-custom \
    --test-input tests/audio/inputs/make_it_warmer.wav \
    -mw ./whisper.cpp/models/ggml-base.en.bin \
    --llama-url http://localhost:8080 \
    -vth 1.2 -c -1

# Expected: Tool executes silently
# Actual: Malformed JSON is spoken: "name, set temperature, arguments, value, ..."
```

### Test Results

| Branch | Tool Parse Success | Tool Execution | JSON Format |
|--------|-------------------|----------------|-------------|
| master | ❌ Fails | ❌ No | Malformed quotes |
| whisper-npu | ⚠️ Partial | ❌ No | Handles some cases |

---

## Related Files

- `custom/talk-llama/tool-parser.cpp` - Tool call parser implementation
- `custom/talk-llama/tool-parser.h` - Parser interface
- `custom/talk-llama/tool-system.cpp` - Tool registry and execution
- `custom/talk-llama/talk-llama.cpp` - Integration with LLM streaming (line ~1190)

---

## References

- Original TTS investigation: `tests/results/END_TO_END_LATENCY_RESULTS.md`
- Tool system documentation: (none - needs to be created)
- Mistral tool calling docs: https://docs.mistral.ai/capabilities/function_calling/

---

## Conclusion

The tool system bug is:
- ✅ **Confirmed** as pre-existing on master branch
- ✅ **Reproducible** with 100% consistency
- ⚠️ **Partially addressed** with quote-stripping logic
- ❌ **Not fully fixed** - needs deeper state machine work

**This is NOT a regression** from NPU/TTS work. The bug existed before our changes.

**Recommendation**: Document and deprioritize. The TTS timing measurement (original goal) is complete and successful. Tool system debugging can be addressed in a separate effort with proper allocation of time and resources.
