#pragma once

#include <string>
#include <memory>

namespace tool_system {

// Wyoming protocol client for sending control events to Wyoming-Piper
// Implements the Wyoming protocol: JSON events over TCP
class WyomingClient {
public:
    WyomingClient(const std::string& host, int port);
    ~WyomingClient();

    // Send AudioStop event (standard Wyoming protocol)
    // Terminates current TTS playback
    bool sendAudioStop();

    // Send audio-pause event (custom event)
    // Pauses current TTS playback (can be resumed)
    bool sendAudioPause();

    // Send audio-resume event (custom event)
    // Resumes paused TTS playback
    bool sendAudioResume();

    // Check if client is connected
    bool isConnected() const;

private:
    // Send a Wyoming protocol event
    // Format: {"type": "event_type", "data": {...}}\n
    bool sendEvent(const std::string& event_type, const std::string& data_json = "{}");

    // Connect to Wyoming server
    bool connect();

    // Close connection
    void disconnect();

    std::string host_;
    int port_;
    int socket_fd_;
    bool connected_;
};

// Parse Wyoming TTS URL to extract host and port
// Example: "http://localhost:10200/" -> ("localhost", 10200)
bool parseWyomingUrl(const std::string& url, std::string& host, int& port);

} // namespace tool_system
