# Development Environment Setup Guide

This guide documents the development and deployment machines used for this project.

## Development Machines

### Dev Machine (Primary Development)
- **Hostname**: 192.168.86.74
- **Username**: paul
- **SSH Key**: Configured (passwordless)
- **Purpose**: Primary development and testing
- **Features**: All dependencies installed, ROCm support
- **Location**: `/home/paul/Projects/git/talk-llama-fast`

### Target Machine (Deployment Testing)
- **Hostname**: 192.168.86.22
- **Username**: amd
- **Password**: amd123
- **SSH Key**: Configured (passwordless SSH, but sudo requires password)
- **Purpose**: Clean deployment testing, target board
- **Location**: `/home/amd/voice-assistant-custom-commands`

## SSH Access

### Passwordless SSH
Both machines are configured for passwordless SSH access:

```bash
# Dev machine
ssh paul@192.168.86.74

# Target machine
ssh amd@192.168.86.22
```

### Sudo Access

**Dev machine (192.168.86.74)**: Passwordless sudo configured

**Target machine (192.168.86.22)**: Requires password
```bash
# Sudo password for user 'amd'
sudo -S apt-get install package  # Will prompt for: amd123
```

## Remote Development Workflow

### Quick SSH Commands

```bash
# Dev machine
ssh paul@192.168.86.74 "cd Projects/git/talk-llama-fast && git pull"

# Target machine  
ssh amd@192.168.86.22 "cd voice-assistant-custom-commands && git pull"
```

### Remote Build

```bash
# Build on dev machine
ssh paul@192.168.86.74 "cd Projects/git/talk-llama-fast && cmake --build build -j"

# Build on target machine
ssh amd@192.168.86.22 "cd voice-assistant-custom-commands && cmake --build build -j"
```

### Remote Testing

```bash
# Run tests on dev machine
ssh paul@192.168.86.74 "cd Projects/git/talk-llama-fast && ./start-assistant.sh"
```

## Machine Capabilities

### Dev Machine (192.168.86.74)
- **OS**: Ubuntu 22.04 or similar
- **GPU**: AMD GPU with ROCm support
- **Packages**: All development packages installed
- **Wyoming-Piper**: Installed as wyoming-piper-custom
- **Models**: Whisper and LLaMA models downloaded

### Target Machine (192.168.86.22)
- **OS**: Ubuntu-based (target board)
- **Packages**: Minimal (requires package installation for build)
- **Purpose**: Clean deployment testing

## File Synchronization

### Rsync for Large Files

```bash
# Sync from dev to target (excluding build artifacts)
rsync -avz --exclude build --exclude models --exclude '*.gguf' \
    paul@192.168.86.74:~/Projects/git/talk-llama-fast/ \
    amd@192.168.86.22:~/voice-assistant-custom-commands/
```

### Git for Source Code

Always prefer git pull/push over file copying to maintain version control:

```bash
# On any machine
cd <repo-directory>
git pull origin master
```

## Port Forwarding

If you need to access services running on remote machines:

```bash
# Forward Wyoming-Piper TTS from dev machine to local
ssh -L 8020:localhost:8020 paul@192.168.86.74

# Forward Wyoming-Piper TTS from target machine to local
ssh -L 8020:localhost:8020 amd@192.168.86.22
```

## Troubleshooting

### SSH Connection Issues

If SSH fails:
```bash
# Check if machine is reachable
ping 192.168.86.74
ping 192.168.86.22

# Check SSH service
ssh -v amd@192.168.86.22
```

### Sudo Password Issues

Target machine requires password for sudo. Use one of:

```bash
# Interactive (will prompt)
ssh amd@192.168.86.22
sudo apt-get install package

# Non-interactive (provide password)
echo 'amd123' | sudo -S apt-get install package
```

### Permission Issues

If you get permission denied:
```bash
# Check file permissions
ls -la <file>

# Fix if needed
chmod +x <file>
```

## Security Notes

- SSH keys are configured for convenience in development environment
- Target machine sudo password (amd123) is for development/testing only
- Production deployments should use proper secret management
- Consider passwordless sudo on dev machines for automation

## Adding New Machines

To add a new development or target machine:

1. Generate SSH key (if needed):
   ```bash
   ssh-keygen -t ed25519 -C "your-email@example.com"
   ```

2. Copy key to remote:
   ```bash
   ssh-copy-id user@hostname
   ```

3. Test passwordless access:
   ```bash
   ssh user@hostname "echo 'Success'"
   ```

4. Update this document with machine details
