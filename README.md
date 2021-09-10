# repo2docker podman

[![Build Status](https://github.com/manics/repo2docker-podman/actions/workflows/test.yml/badge.svg)](https://github.com/manics/repo2docker-podman/actions/workflows/test.yml)

`repo2docker-podman` is a plugin for [repo2docker](http://repo2docker.readthedocs.io) that lets you use [Podman](https://podman.io/) instead of Docker.

Requires Podman 3+.

## Installation

    pip install -U git+https://github.com/manics/repo2docker-podman.git@main

## Running

Simply include `--engine podman` in the arguments to `repo2docker`:

    repo2docker --engine podman repository/to/build
