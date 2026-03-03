#!/usr/bin/env python3
"""Compare dev machine and target machine setup."""

import paramiko

def get_client(hostname, username, password):
    """Connect and return SSH client."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname, username=username, password=password)
    return client

def run_command(client, command):
    """Run command and return output."""
    stdin, stdout, stderr = client.exec_command(command)
    return stdout.read().decode('utf-8').strip()

def main():
    # Connect to both machines
    print("Connecting to machines...")
    dev = get_client("192.168.86.74", "paul", "amdisthebest")
    target = get_client("192.168.86.22", "amd", "amd123")
    print("✓ Connected to both\n")

    print("="*60)
    print("COMPARING DEV MACHINE vs TARGET MACHINE")
    print("="*60)
    print()

    # Check Python version
    print("Python version:")
    dev_py = run_command(dev, "python3 --version")
    target_py = run_command(target, "python3 --version")
    print(f"  Dev:    {dev_py}")
    print(f"  Target: {target_py}")
    print()

    # Check Piper version
    print("Piper binary:")
    dev_piper = run_command(dev, "/opt/piper/piper --version 2>&1 || echo 'Not found'")
    target_piper = run_command(target, "/opt/piper/piper --version 2>&1 || echo 'Not found'")
    print(f"  Dev:    {dev_piper}")
    print(f"  Target: {target_piper}")
    print()

    # Check wyoming-piper-custom version
    print("wyoming-piper-custom version:")
    dev_wp = run_command(dev, "export PATH=\"$HOME/.local/bin:$PATH\" && wyoming-piper-custom --version 2>&1 || echo 'Not found'")
    target_wp = run_command(target, "export PATH=\"$HOME/.local/bin:$PATH\" && wyoming-piper-custom --version 2>&1 || echo 'Not found'")
    print(f"  Dev:    {dev_wp}")
    print(f"  Target: {target_wp}")
    print()

    # Check if wyoming-piper-custom is editable install
    print("wyoming-piper-custom install type:")
    dev_editable = run_command(dev, "ls ~/.local/share/pipx/venvs/wyoming-piper-custom/lib/python*/site-packages/__editable__* 2>/dev/null && echo 'EDITABLE' || echo 'REGULAR'")
    target_editable = run_command(target, "ls ~/.local/share/pipx/venvs/wyoming-piper-custom/lib/python*/site-packages/__editable__* 2>/dev/null && echo 'EDITABLE' || echo 'REGULAR'")
    print(f"  Dev:    {dev_editable}")
    print(f"  Target: {target_editable}")
    print()

    # Check if Piper output parsing fix is present
    print("Piper output parsing fix (multi-line stderr):")
    dev_fix = run_command(dev, "grep -c 'Piper outputs multiple log lines' ~/Projects/git/talk-llama-fast/wyoming-piper/wyoming_piper/handler.py 2>/dev/null || echo '0'")
    target_fix = run_command(target, "grep -c 'Piper outputs multiple log lines' ~/voice-assistant-custom-commands/wyoming-piper/wyoming_piper/handler.py 2>/dev/null || echo '0'")
    print(f"  Dev:    {'✓ Present' if int(dev_fix) > 0 else '✗ Missing'}")
    print(f"  Target: {'✓ Present' if int(target_fix) > 0 else '✗ Missing'}")
    print()

    # Check talk-llama binary
    print("talk-llama-custom binary:")
    dev_tl = run_command(dev, "ls -lh ~/Projects/git/talk-llama-fast/build/bin/talk-llama-custom 2>/dev/null | awk '{print $5, $9}' || echo 'Not found'")
    target_tl = run_command(target, "ls -lh ~/voice-assistant-custom-commands/build/bin/talk-llama-custom 2>/dev/null | awk '{print $5, $9}' || echo 'Not found'")
    print(f"  Dev:    {dev_tl}")
    print(f"  Target: {target_tl}")
    print()

    # Check start-assistant.sh for TTS test
    print("TTS test in start-assistant.sh:")
    dev_tts = run_command(dev, "grep -A 5 'Testing Wyoming-Piper TTS' ~/Projects/git/talk-llama-fast/start-assistant.sh 2>/dev/null | head -3")
    target_tts = run_command(target, "grep -A 5 'Testing Wyoming-Piper TTS' ~/voice-assistant-custom-commands/start-assistant.sh 2>/dev/null | head -3")
    print(f"  Dev:    {'✓ Present' if dev_tts else '✗ Missing'}")
    print(f"  Target: {'✓ Present' if target_tts else '✗ Missing'}")
    if dev_tts:
        print(f"\nDev TTS test:")
        print(dev_tts)
    print()

    # Show start-assistant.sh differences
    print("="*60)
    print("CHECKING start-assistant.sh on dev machine for TTS test:")
    print("="*60)
    dev_startup = run_command(dev, "grep -B 2 -A 10 'Ready\\|TTS\\|Wyoming.*ready' ~/Projects/git/talk-llama-fast/start-assistant.sh 2>/dev/null | tail -20")
    print(dev_startup)
    print()

    dev.close()
    target.close()

if __name__ == "__main__":
    main()
