// Unit test for ToolCallParser
// Tests parsing of LLM output with various malformed JSON patterns

#include "../custom/talk-llama/tool-parser.h"
#include <iostream>
#include <cassert>

using namespace tool_system;

void test_valid_json() {
    std::cout << "TEST: Valid JSON parsing\n";
    ToolCallParser parser;

    // Simulate streaming: <tool_call>{"name":"test","arguments":{},"id":"1"}</tool_call>
    std::string tokens[] = {"<", "tool", "_call", ">", "{", "\"name\":", "\"test\"", ",", "\"arguments\":{}", ",", "\"id\":\"1\"", "}", "</", "tool", "_call", ">"};

    bool found = false;
    for (const auto& token : tokens) {
        if (parser.feedToken(token)) {
            found = true;
            break;
        }
    }

    if (found && parser.hasToolCall()) {
        ToolCall call = parser.getToolCall();
        assert(call.name == "test");
        std::cout << "  ✓ PASS: Parsed valid JSON\n";
    } else {
        std::cout << "  ✗ FAIL: Failed to parse valid JSON\n";
    }
    std::cout << std::endl;
}

void test_malformed_with_quotes() {
    std::cout << "TEST: Malformed JSON with outer quotes\n";
    ToolCallParser parser;

    // Simulate: <tool_call>"{"name":"set_temperature","arguments":{"value":72}}</tool_call>
    // This is what Mistral actually outputs
    parser.feedToken("<");
    parser.feedToken("tool");
    parser.feedToken("_call");
    parser.feedToken(">");
    parser.feedToken("\"{\"name");
    parser.feedToken("\":");
    parser.feedToken("\"set");
    parser.feedToken("_temperature");
    parser.feedToken("\",\"arguments\":{\"value\":72}}");
    parser.feedToken("</");
    parser.feedToken("tool");
    parser.feedToken("_call");
    bool found = parser.feedToken(">");

    if (found && parser.hasToolCall()) {
        ToolCall call = parser.getToolCall();
        if (call.name == "set_temperature") {
            std::cout << "  ✓ PASS: Parsed malformed JSON with quotes\n";
        } else {
            std::cout << "  ✗ FAIL: Wrong tool name: " << call.name << "\n";
        }
    } else {
        std::cout << "  ✗ FAIL: Failed to parse malformed JSON\n";
    }
    std::cout << std::endl;
}

void test_simulated_llm_stream() {
    std::cout << "TEST: Simulated LLM token stream\n";
    ToolCallParser parser;

    // Simulate realistic token-by-token streaming from LLM
    // Output: <tool_call>"{"name": "set_temperature", "arguments": {"value": 75}}</tool_call>
    std::string stream[] = {
        " <", "tool", "_call", ">\"", "{\"", "name", "\":", " \"", "set", "_t", "emperature", "\",",
        " \"", "arguments", "\":", " {", "\"", "value", "\":", " ", "75", "}}", "</", "tool", "_call", ">"
    };

    bool found = false;
    std::string accumulated_text;

    for (const auto& token : stream) {
        if (parser.feedToken(token)) {
            found = true;
            break;
        }
        // Also get any normal text that's not part of tool tags
        accumulated_text += parser.getText();
    }

    if (found && parser.hasToolCall()) {
        ToolCall call = parser.getToolCall();
        std::cout << "  ✓ PASS: Parsed tool call from realistic stream\n";
        std::cout << "    Tool name: " << call.name << "\n";
        std::cout << "    Arguments: " << call.arguments.dump() << "\n";
    } else {
        std::cout << "  ✗ FAIL: Failed to parse realistic stream\n";
    }

    if (!accumulated_text.empty()) {
        std::cout << "  NOTE: Normal text extracted: \"" << accumulated_text << "\"\n";
    }

    std::cout << std::endl;
}

int main() {
    std::cout << "===========================================\n";
    std::cout << "Tool Call Parser Unit Tests\n";
    std::cout << "===========================================\n\n";

    test_valid_json();
    test_malformed_with_quotes();
    test_simulated_llm_stream();

    std::cout << "===========================================\n";
    std::cout << "Tests complete\n";
    std::cout << "===========================================\n";

    return 0;
}
