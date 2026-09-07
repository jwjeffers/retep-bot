#!/bin/bash
# Retep Bot - Server Setup Script
# Supports both Ubuntu/Debian (apt) and Oracle Linux/RHEL (dnf)
# Run after SSH'ing into your new VM:
#   bash setup_server.sh

set -e

echo "========================================="
echo "  Retep Bot - Server Setup"
echo "========================================="

# Detect package manager
if command -v apt &> /dev/null; then
    PKG_MGR="apt"
elif command -v dnf &> /dev/null; then
    PKG_MGR="dnf"
else
    echo "Error: No supported package manager found (apt or dnf)"
    exit 1
fi

# Update system
echo "[1/6] Updating system packages..."
if [ "$PKG_MGR" = "apt" ]; then
    sudo apt update && sudo apt upgrade -y
else
    sudo dnf update -y
fi

# Install Python 3 and pip
echo "[2/6] Installing Python..."
if [ "$PKG_MGR" = "apt" ]; then
    sudo apt install -y python3 python3-pip python3-venv git
else
    sudo dnf install -y python3 python3-pip git
fi

# Clone the repo
echo "[3/6] Cloning retep-bot from GitHub..."
cd ~
git clone https://github.com/jwjeffers/retep-bot.git
cd retep-bot

# Create virtual environment
echo "[4/6] Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file
echo "[5/6] Creating .env file..."
echo "Paste your Discord bot token below:"
read -p "DISCORD_TOKEN=" TOKEN
cat > .env << EOF
DISCORD_TOKEN=$TOKEN
MESSAGES_PER_DAY=1
EOF
echo ".env created!"

# Create systemd service
echo "[6/6] Setting up systemd service for auto-restart..."
sudo tee /etc/systemd/system/retep.service > /dev/null << EOF
[Unit]
Description=Retep Discord Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/retep-bot
ExecStart=$HOME/retep-bot/venv/bin/python3 bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable retep.service
sudo systemctl start retep.service

echo ""
echo "========================================="
echo "  Setup Complete!"
echo "========================================="
echo ""
echo "Retep is now running as a system service."
echo ""
echo "Useful commands:"
echo "  sudo systemctl status retep    # Check status"
echo "  sudo systemctl restart retep   # Restart bot"
echo "  sudo systemctl stop retep      # Stop bot"
echo "  journalctl -u retep -f         # View live logs"
echo ""
echo "To update the bot later:"
echo "  cd ~/retep-bot && git pull && sudo systemctl restart retep"
echo ""
