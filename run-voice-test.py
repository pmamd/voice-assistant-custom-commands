#!/usr/bin/env python3
"""Run voice assistant test on target machine using paramiko."""

import paramiko
import time
import sys

def run_command(client, command, wait_time=0):
    """Run a command and return output."""
    stdin, stdout, stderr = client.exec_command(command)
    if wait_time:
        time.sleep(wait_time)
    output = stdout.read().decode('utf-8')
    error = stderr.read().decode('utf-8')
    exit_code = stdout.channel.recv_exit_status()
    return output, error, exit_code

def main():
    # Connect to target machine
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print("Connecting to 192.168.86.22...")
    client.connect('192.168.86.22', username='amd', password='amd123')
    print("✓ Connected\n")

    try:
        # 1. Clean up any existing processes
        print("1. Cleaning up existing processes...")
        run_command(client, "pkill -9 -f 'wyoming|talk-llama'")
        time.sleep(2)

        # 2. Remove old log
        run_command(client, "rm -f /tmp/wyoming-piper.log")

        # 3. Start voice assistant with TTS test
        print("2. Starting voice assistant (will run TTS test automatically)...")
        cmd = """
cd ~/voice-assistant-custom-commands
export PATH="$HOME/.local/bin:$PATH"
export MIC_DEVICE=0
timeout 30 ./start-assistant.sh > /tmp/assistant-output.log 2>&1
"""
        print("   Waiting 30 seconds for startup + TTS test...")
        output, error, exit_code = run_command(client, cmd, wait_time=0)

        # Wait for completion
        time.sleep(35)

        # 4. Show assistant output
        print("\n=== Voice Assistant Output (last 30 lines) ===")
        output, _, _ = run_command(client, "tail -30 /tmp/assistant-output.log")
        print(output)

        # 5. Show Wyoming-Piper log
        print("\n=== Wyoming-Piper Log (last 50 lines) ===")
        output, _, _ = run_command(client, "tail -50 /tmp/wyoming-piper.log")
        print(output)

        # 6. Check for FileNotFoundError
        print("\n=== Checking for errors ===")
        output, _, _ = run_command(client, "grep -i 'FileNotFoundError' /tmp/wyoming-piper.log")
        if output:
            print("✗ Found FileNotFoundError (BUG NOT FIXED):")
            print(output)
            print("\n=== Full Wyoming-Piper Log ===")
            output, _, _ = run_command(client, "cat /tmp/wyoming-piper.log")
            print(output)
            sys.exit(1)
        else:
            print("✓ No FileNotFoundError found")

        # 7. Check for task exceptions
        output, _, _ = run_command(client, "grep -i 'ERROR.*Task exception' /tmp/wyoming-piper.log")
        if output:
            print("✗ Found task exceptions:")
            print(output)
        else:
            print("✓ No task exceptions found")

        # 8. Check for successful TTS processing
        output, _, _ = run_command(client, "grep -i 'Audio file path:' /tmp/wyoming-piper.log")
        if output:
            print("✓ TTS processing succeeded:")
            print(output)
            print("\n✓✓✓ PIPER OUTPUT PARSING FIX VERIFIED ✓✓✓")
        else:
            print("⚠ No 'Audio file path:' entries found")
            print("  (TTS test may not have been triggered - check assistant output above)")

        # 9. Cleanup
        print("\n3. Cleaning up...")
        run_command(client, "pkill -9 -f 'wyoming|talk-llama'")

        print("\n" + "="*50)
        print("TEST COMPLETE")
        print("="*50)

    finally:
        client.close()

if __name__ == "__main__":
    main()
