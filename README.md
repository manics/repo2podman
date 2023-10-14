# repo2podman

[![Build Status](https://github.com/manics/repo2podman/actions/workflows/build.yml/badge.svg)](https://github.com/manics/repo2podman/actions/workflows/build.yml)
[![Latest PyPI version](https://img.shields.io/pypi/v/repo2podman?logo=pypi)](https://pypi.python.org/pypi/repo2podman)

`repo2podman` is a plugin for [repo2docker](http://repo2docker.readthedocs.io) that lets you use [Podman](https://podman.io/) instead of Docker.

Requires Podman 3+.

## Installation

    pip install repo2podman

## Running

Simply include `--engine podman` in the arguments to `repo2docker`:

    repo2docker --engine podman <repository>

### Using a different Podman executable

repo2podman uses the `podman` command line executable, so it should be possible to substitute any other docker/podman compatible command line tool.

For example, `nerdctl`:

    repo2docker --engine podman --PodmanEngine.podman_executable=nerdctl <repository>

`podman-remote`:

    export CONTAINER_HOST=ssh://<user>@<host>/home/<user>/podman.sock
    export CONTAINER_SSHKEY=$HOME/.ssh/<ssh-private-key>
    repo2docker --engine=podman --PodmanEngine.podman_executable=podman-remote <repository>
