# repo2podman

[![Build Status](https://github.com/manics/repo2podman/actions/workflows/build.yml/badge.svg)](https://github.com/manics/repo2podman/actions/workflows/build.yml)
[![Latest PyPI version](https://img.shields.io/pypi/v/repo2podman?logo=pypi)](https://pypi.python.org/pypi/repo2podman)

`repo2podman` is a plugin for [repo2docker](http://repo2docker.readthedocs.io) that lets you use [Podman](https://podman.io/) instead of Docker.

Requires Podman 3+.

## Installation

    pip install repo2podman

## Running

Simply include `--engine podman` in the arguments to `repo2docker`:

    repo2docker --engine podman repository/to/build
