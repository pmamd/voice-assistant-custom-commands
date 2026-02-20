#!/bin/bash
# Setup deployment environment with paramiko

set -e

echo "=========================================="
echo "Setting up deployment environment"
echo "=========================================="

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate venv
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip -q

# Install paramiko and dependencies
echo "Installing paramiko and dependencies..."
pip install paramiko scp pyyaml -q

echo ""
echo "=========================================="
echo "✓ Setup complete!"
echo "=========================================="
echo ""
echo "To deploy to dev machine:"
echo "  source venv/bin/activate"
echo "  python3 deploy_to_dev.py"
echo ""
echo "Or just run:"
echo "  ./deploy.sh"
echo ""
