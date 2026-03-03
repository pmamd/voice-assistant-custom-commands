#!/usr/bin/env python3
"""Run TTS test on target machine using paramiko."""

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

        # 3. Start Wyoming-Piper in background
        print("2. Starting Wyoming-Piper in debug mode...")
        cmd = """
cd ~/voice-assistant-custom-commands
export PATH="$HOME/.local/bin:$PATH"
nohup wyoming-piper-custom \
    --piper /opt/piper/piper \
    --voice en_US-lessac-medium \
    --data-dir ./piper-data \
    --uri tcp://0.0.0.0:10200 \
    --debug > /tmp/wyoming-piper.log 2>&1 &
echo $!
"""
        output, error, _ = run_command(client, cmd)
        wyoming_pid = output.strip()
        print(f"   Wyoming-Piper PID: {wyoming_pid}")

        # 4. Wait for startup
        print("3. Waiting 15 seconds for Wyoming-Piper to start...")
        time.sleep(15)

        # 5. Check if Wyoming-Piper is still running
        output, _, _ = run_command(client, f"kill -0 {wyoming_pid} 2>&1 && echo 'RUNNING' || echo 'DEAD'")
        if 'DEAD' in output:
            print("   ✗ Wyoming-Piper died during startup!\n")
            output, _, _ = run_command(client, "cat /tmp/wyoming-piper.log")
            print("=== Wyoming-Piper Log ===")
            print(output)
            sys.exit(1)
        print("   ✓ Wyoming-Piper is running\n")

        # 6. Run TTS test
        print("4. Running TTS test...")
        output, error, exit_code = run_command(client,
            "cd ~/voice-assistant-custom-commands && python3 test-tts-direct.py",
            wait_time=5)

        print(output)
        if error:
            print("STDERR:", error)

        # 7. Show Wyoming-Piper log
        print("\n=== Wyoming-Piper Log (last 50 lines) ===")
        output, _, _ = run_command(client, "tail -50 /tmp/wyoming-piper.log")
        print(output)

        # 8. Check for FileNotFoundError
        print("\n=== Checking for errors ===")
        output, _, _ = run_command(client, "grep -i 'FileNotFoundError' /tmp/wyoming-piper.log")
        if output:
            print("✗ Found FileNotFoundError:")
            print(output)
            sys.exit(1)
        else:
            print("✓ No FileNotFoundError found")

        # 9. Check for successful TTS processing
        output, _, _ = run_command(client, "grep -i 'Audio file path:' /tmp/wyoming-piper.log")
        if output:
            print("✓ TTS processing succeeded:")
            print(output)
        else:
            print("⚠ No 'Audio file path:' entries found - TTS may not have been triggered")

        # 10. Cleanup
        print("\n5. Cleaning up...")
        run_command(client, f"kill {wyoming_pid} 2>/dev/null")

        print("\n" + "="*50)
        print("TEST COMPLETE")
        print("="*50)

    finally:
        client.close()

if __name__ == "__main__":
    main()
