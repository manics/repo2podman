# repo2docker podman

[![Build Status](https://travis-ci.com/manics/repo2docker-podman.svg?branch=master)](https://travis-ci.com/manics/repo2docker-podman)

`repo2docker-podman` is a plugin for [repo2docker](http://repo2docker.readthedocs.io) that lets you use [Podman](https://podman.io/) instead of Docker.

## Installation

This plugin is still in development and relies on [unreleased features of repo2docker](https://github.com/jupyter/repo2docker/pull/848).

    pip install -U git+https://github.com/manics/repo2docker.git@abstractengine
    pip install -U git+https://github.com/manics/repo2docker-podman.git@master

## Running

Simply include `--engine podman` in the arguments to `repo2docker`:

    repo2docker --engine podman repository/to/build
