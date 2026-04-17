#include "tool-parser.h"
#include <algorithm>
#include <cstdio>

namespace tool_system {

ToolCallParser::ToolCallParser()
    : state_(ParserState::NORMAL) {
}

bool ToolCallParser::bufferMatches(const std::string& str) const {
    return buffer_ == str;
}

bool ToolCallParser::feedToken(const std::string& token) {
    for (char c : token) {
        buffer_ += c;

        switch (state_) {
            case ParserState::NORMAL:
                // Look for start of tag: '<'
                if (c == '<') {
                    state_ = ParserState::IN_TAG_START;
                    buffer_ = "<";
                } else {
                    normal_text_ += c;
                }
                break;

            case ParserState::IN_TAG_START:
                // Check if we're starting <tool_call>
                if (buffer_ == "<tool_call>") {
                    state_ = ParserState::IN_TOOL_CALL;
                    json_content_ = "";
                    buffer_ = "";
                } else if (buffer_.length() >= 11) {
                    // Not a tool_call tag, treat as normal text
                    normal_text_ += buffer_;
                    buffer_ = "";
                    state_ = ParserState::NORMAL;
                } else if (c != 't' && c != 'o' && c != 'l' && c != '_' && c != 'c' && c != 'a' && c != '>') {
                    // Invalid character for <tool_call>, back to normal
                    normal_text_ += buffer_;
                    buffer_ = "";
                    state_ = ParserState::NORMAL;
                }
                break;

            case ParserState::IN_TOOL_CALL:
                // Accumulate JSON content until we see '</'
                if (c == '<' && buffer_.length() >= 2 && buffer_[buffer_.length() - 2] != '\\') {
                    // Start of potential end tag
                    json_content_ = buffer_.substr(0, buffer_.length() - 1);
                    buffer_ = "<";
                    state_ = ParserState::IN_TAG_END;
                } else {
                    // Continue accumulating JSON
                }
                break;

            case ParserState::IN_TAG_END:
                // Check if we're closing </tool_call>
                if (buffer_ == "</tool_call>") {
                    // Complete tool call detected!
                    if (parseToolCall()) {
                        state_ = ParserState::COMPLETE;
                        buffer_ = "";
                        return true;
                    } else {
                        // Parse failed, treat as normal text
                        fprintf(stderr, "[Tool Parser] Failed to parse tool call JSON\n");
                        normal_text_ += "<tool_call>" + json_content_ + "</tool_call>";
                        buffer_ = "";
                        json_content_ = "";
                        state_ = ParserState::NORMAL;
                    }
                } else if (buffer_.length() >= 12) {
                    // Not a closing tag, treat as JSON content
                    json_content_ += buffer_;
                    buffer_ = "";
                    state_ = ParserState::IN_TOOL_CALL;
                } else if (c != '/' && c != 't' && c != 'o' && c != 'l' && c != '_' && c != 'c' && c != 'a' && c != '>') {
                    // Invalid character, back to accumulating JSON
                    json_content_ += buffer_;
                    buffer_ = "";
                    state_ = ParserState::IN_TOOL_CALL;
                }
                break;

            case ParserState::COMPLETE:
                // After completion, stay in COMPLETE until reset
                // Don't process more tokens
                break;
        }
    }

    return false;
}

bool ToolCallParser::parseToolCall() {
    try {
        // LLMs sometimes output malformed JSON in multiple ways:
        // 1. "{"name": ...}"  - entire JSON wrapped in quotes
        // 2. "{name": ...}    - missing quote on first key after stripping leading "{
        // 3. "{"name": ...}   - opening quote but no closing quote

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

        if (!parsed) {
            return false;
        }

        if (!j.contains("name") || !j["name"].is_string()) {
            fprintf(stderr, "[Tool Parser] Missing 'name' field in tool call\n");
            return false;
        }

        current_call_.name = j["name"].get<std::string>();
        current_call_.id = j.value("id", "0");

        if (j.contains("arguments")) {
            current_call_.arguments = j["arguments"];
        } else {
            current_call_.arguments = json::object();
        }

        fprintf(stdout, "[Tool Parser] Parsed tool call: %s (id: %s)\n",
                current_call_.name.c_str(), current_call_.id.c_str());

        return true;

    } catch (const json::exception& e) {
        fprintf(stderr, "[Tool Parser] JSON parse error: %s\n", e.what());
        fprintf(stderr, "[Tool Parser] JSON content: %s\n", json_content_.c_str());
        return false;
    }
}

ToolCall ToolCallParser::getToolCall() {
    return current_call_;
}

void ToolCallParser::reset() {
    state_ = ParserState::NORMAL;
    buffer_ = "";
    json_content_ = "";
    normal_text_ = "";
    current_call_ = ToolCall();
}

} // namespace tool_system
