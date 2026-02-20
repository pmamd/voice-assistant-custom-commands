#!/bin/bash
# One-command deployment script

set -e

# Setup venv if needed
if [ ! -d "venv" ]; then
    echo "Setting up deployment environment..."
    ./setup_deployment.sh
fi

# Activate venv and deploy
source venv/bin/activate
python3 deploy_to_dev.py
