#!/bin/sh
set -eux
# Install Podman
# https://podman.io/getting-started/installation.html

. /etc/os-release
sudo sh -c "echo 'deb http://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/stable/xUbuntu_${VERSION_ID}/ /' > /etc/apt/sources.list.d/devel:kubic:libcontainers:stable.list"
wget -nv https://download.opensuse.org/repositories/devel:kubic:libcontainers:stable/xUbuntu_${VERSION_ID}/Release.key -O- | sudo apt-key add -
sudo apt-get update -qq
sudo apt-get -qq -y install podman

# systemd doesn't seem to work, use cgroupfs instead
sudo sed -i.bak -re 's/cgroup_manager = .+/cgroup_manager = "cgroupfs"/' /usr/share/containers/libpod.conf

# On ubuntu:bionic running podman as non-root defaults to using VFS instead of overlay as the fuse-overlayfs package isn't available:
# https://github.com/containers/libpod/blob/master/docs/tutorials/rootless_tutorial.md#ensure-fuse-overlayfs-is-installed
# VFS is extremely inefficient so use a custom binary built using
# https://github.com/containers/fuse-overlayfs/tree/v0.7.6#static-build

sudo curl -sSfL https://users.openmicroscopy.org.uk/~spli/podman/fuse-overlayfs-0.7.6 -o /usr/bin/fuse-overlayfs
sudo chmod +x /usr/bin/fuse-overlayfs
fuse-overlayfs --version

podman info
