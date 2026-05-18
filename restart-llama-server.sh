#!/bin/bash
# Script to restart llama-server with persistent KV cache slots

# Kill existing llama-server
pkill llama-server
sleep 2

# Create slot save directory
mkdir -p ./llama-cache

# Start llama-server with slot persistence
/home/amd/git/kitt2k/external/llama.cpp/build/bin/llama-server \
  -m /home/amd/git/kitt2k/models/mistral-7b-instruct-v0.2.Q5_0.gguf \
  -ngl 999 \
  --port 8080 \
  --host 0.0.0.0 \
  --slot-save-path ./llama-cache \
  --slots 4 \
  >> /tmp/llama-server.log 2>&1 &

echo "llama-server restarted with persistent slots at ./llama-cache"
echo "PID: $!"
