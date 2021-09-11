#!/bin/sh
set -eux
# Install Podman
# https://podman.io/getting-started/installation.html

. /etc/os-release
sudo sh -c "echo 'deb http://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/stable/xUbuntu_${VERSION_ID}/ /' > /etc/apt/sources.list.d/devel:kubic:libcontainers:stable.list"
wget -nv https://download.opensuse.org/repositories/devel:kubic:libcontainers:stable/xUbuntu_${VERSION_ID}/Release.key -O- | sudo apt-key add -
sudo apt-get update -qq
# Travis defaults to --no-install-recommends
sudo apt-get -qq -y install --install-recommends podman

fuse-overlayfs --version
slirp4netns --version
podman info

# If in vagrant:
if [ -d /home/vagrant ]; then
    apt-get install -qq -y python3-venv
    rm -f /etc/resolv.conf
    echo nameserver 1.1.1.1 > /etc/resolv.conf
fi
# python3 -mvenv ~/venv
# . ~/venv/bin/activate
# pip install -r /repo2podman/dev-requirements.txt git+https://github.com/jupyterhub/repo2docker.git@master
