#pragma once

#include <string>

namespace tool_system {

// Wyoming protocol client for sending commands to Wyoming-Piper
class WyomingClient {
public:
    WyomingClient(const std::string& base_url);

    // Send stop command to halt current TTS playback
    // Uses the existing send_tts_async infrastructure with "stop" text
    bool sendStop(const std::string& voice, const std::string& language);

    // Future extensions:
    // bool setVolume(int percent);
    // bool setVoice(const std::string& voice_name);

private:
    std::string base_url_;
};

// Helper function: Send stop command using existing TTS infrastructure
// This is a thin wrapper around send_tts_async("stop", ...)
void send_wyoming_stop_command(const std::string& voice,
                                 const std::string& language,
                                 const std::string& tts_url,
                                 bool debug = false);

} // namespace tool_system
