#pragma once

#include <string>
#include <vector>
#include "../../whisper.cpp/examples/json.hpp"

using json = nlohmann::json;

namespace tool_system {

// Parsed tool call from Mistral output
struct ToolCall {
    std::string name;
    json arguments;
    std::string id;

    ToolCall() = default;
    ToolCall(const std::string& n, const json& args, const std::string& i)
        : name(n), arguments(args), id(i) {}
};

// Parser state for streaming tool call detection
enum class ParserState {
    NORMAL,           // Normal text generation
    IN_TAG_START,     // Detected '<', checking for 'tool_call'
    IN_TOOL_CALL,     // Inside <tool_call> tag, accumulating JSON
    IN_TAG_END,       // Detected '</', checking for '/tool_call>'
    COMPLETE          // Tool call complete, ready to extract
};

// Streaming parser for Mistral tool call format
// Detects: <tool_call>{"name": "...", "arguments": {...}, "id": "..."}</tool_call>
class ToolCallParser {
public:
    ToolCallParser();

    // Feed a new token from the generation stream
    // Returns true if a complete tool call was detected
    bool feedToken(const std::string& token);

    // Check if a complete tool call is available
    bool hasToolCall() const { return state_ == ParserState::COMPLETE; }

    // Get the parsed tool call (only valid if hasToolCall() == true)
    ToolCall getToolCall();

    // Get accumulated normal text (non-tool-tag text) and clear the buffer
    // This returns the text since the last call to getText()
    std::string getText() {
        std::string result = normal_text_;
        normal_text_ = "";
        return result;
    }

    // Reset parser state for next tool call
    void reset();

private:
    ParserState state_;
    std::string buffer_;           // Accumulates tokens for tag/JSON detection
    std::string json_content_;     // JSON content inside <tool_call>
    std::string normal_text_;      // Normal text output (excluding tool tags)
    ToolCall current_call_;

    // Helper: Try to parse JSON and extract tool call
    bool parseToolCall();

    // Helper: Check if buffer matches a string
    bool bufferMatches(const std::string& str) const;
};

} // namespace tool_system
