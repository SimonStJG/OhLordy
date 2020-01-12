#!/bin/bash
set -exuo pipefail

if (( EUID != 0 )); then
	echo "You need to be root, soz"
	exit 1
fi

sed -i "/is_raspberry_pi =/c\is_raspberry_pi = True" ohlordy.py

apt update

# python3-distutils required for pip because of https://github.com/pypa/get-pip/issues/43
apt install -y \
	libffi-dev \
	libpython3-dev \
	libssl-dev \
	libvlc5 \
	python3 \
	python3-distutils \
	vlc
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py

python3 get-pip.py
python3 -m pip install .

sudo mkdir -p /var/log/ohlordy
sudo chown pi /var/log/ohlordy

sudo cp ohlordy.service /etc/systemd/system/

sudo systemctl enable myscript.service
sudo systemctl start myscript.service