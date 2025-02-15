#!/bin/bash

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

# Set installation directory
INSTALL_DIR="/opt/gigachat-bot"
SERVICE_NAME="gigachat-bot"
USER="$1"

if [ -z "$USER" ]; then
    echo "Please provide a user to run the service"
    echo "Usage: $0 <username>"
    exit 1
fi

# Create installation directory
echo "Creating installation directory..."
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

# Copy files
echo "Copying files..."
cp -r src/ $INSTALL_DIR/
cp requirements.txt $INSTALL_DIR/
cp secrets.yaml $INSTALL_DIR/

# Set permissions
echo "Setting permissions..."
chown -R $USER:$USER $INSTALL_DIR
chmod -R 750 $INSTALL_DIR

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install -r requirements.txt

# Setup systemd service
echo "Setting up systemd service..."
cp gigachat-bot.service /etc/systemd/system/${SERVICE_NAME}@${USER}.service

# Reload systemd
systemctl daemon-reload

echo "Installation complete!"
echo "To start the service, run:"
echo "systemctl start ${SERVICE_NAME}@${USER}"
echo "To enable autostart, run:"
echo "systemctl enable ${SERVICE_NAME}@${USER}"
