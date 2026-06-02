#!/bin/bash

set -e

sudo apt update

sudo apt install -y \
python3 \
python3-pip \
python3-venv \
git \
nginx \
certbot \
python3-certbot-nginx \
libreoffice

if [ ! -d "$HOME/venv" ]; then
    python3 -m venv $HOME/venv
fi

echo "Server setup completed"
