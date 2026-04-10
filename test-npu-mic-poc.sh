#!/bin/bash
# Quick NPU mic POC - run from local machine

echo "Testing NPU Whisper with microphone on .22..."
echo ""

ssh amd@192.168.86.22 'bash -s' << 'ENDSSH'
source /opt/xilinx/xrt/setup.sh
source /home/amd/RyzenAI-Full/bin/activate
cd ~/RyzenAI-SW/Demos/ASR/Whisper

echo "🎤 Speak a short phrase (will transcribe after 5 seconds of silence)..."
echo ""

timeout 30 python run_whisper.py \
  --model-type whisper-small \
  --device npu \
  --input mic \
  --duration 0 2>&1
ENDSSH

echo ""
echo "Done! Check the transcription above."
