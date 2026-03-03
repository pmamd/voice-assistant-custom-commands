#!/usr/bin/env python3
"""Direct TTS test via Wyoming protocol to verify Piper output parsing fix."""

import asyncio
import sys
from wyoming.client import AsyncTcpClient
from wyoming.tts import Synthesize

async def test_tts():
    """Send a TTS request and check if it succeeds without FileNotFoundError."""
    print("Connecting to Wyoming-Piper on port 10200...")

    try:
        async with AsyncTcpClient("localhost", 10200) as client:
            print("✓ Connected")

            # Send describe to get info
            await client.write_event({"type": "describe"}.get("event", {}))

            # Send synthesize request
            print("Sending TTS request: 'This is a test of the Piper output parsing fix.'")
            synthesize = Synthesize(text="This is a test of the Piper output parsing fix.")
            await client.write_event(synthesize.event())

            # Read response events
            print("Waiting for response...")
            timeout_count = 0
            max_timeout = 30

            while timeout_count < max_timeout:
                try:
                    event = await asyncio.wait_for(client.read_event(), timeout=1.0)
                    if event:
                        print(f"Received event: {event.type if hasattr(event, 'type') else event}")
                        if hasattr(event, 'type') and 'audio' in event.type:
                            print("✓ Received audio chunks - TTS succeeded!")
                            return True
                except asyncio.TimeoutError:
                    timeout_count += 1
                    if timeout_count % 5 == 0:
                        print(f"  Still waiting... ({timeout_count}s)")
                except Exception as e:
                    print(f"Error reading event: {e}")
                    break

            print("⚠ Timeout waiting for audio response")
            return False

    except ConnectionRefusedError:
        print("✗ Connection refused - Wyoming-Piper not running?")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Wyoming-Piper TTS Direct Test")
    print("=" * 50)
    print()

    result = asyncio.run(test_tts())

    print()
    print("=" * 50)
    if result:
        print("✓ TEST PASSED - TTS request succeeded")
        print("Check /tmp/wyoming-piper.log for 'Audio file path:' entries")
        sys.exit(0)
    else:
        print("✗ TEST FAILED")
        print("Check /tmp/wyoming-piper.log for errors")
        sys.exit(1)
