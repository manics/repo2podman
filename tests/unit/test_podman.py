"""Tests for podman client"""

import pytest
import re
from repo2podman.podman import (
    execute_cmd,
    PodmanCommandError,
    PodmanContainer,
    PodmanEngine,
    ProcessTerminated,
)
from time import sleep


BUSYBOX = "docker.io/library/busybox"


class Counter:
    def __init__(self):
        self.n = 0

    def inc(self):
        self.n += 1
        return self.n


def test_execute_cmd():
    r = execute_cmd(["echo", "a"], capture="both", break_callback=None)
    assert list(r) == ["a\n"]

    r = execute_cmd(["echo", "a"], capture="stdout", break_callback=None)
    assert list(r) == ["a\n"]

    r = execute_cmd(["echo", "a"], capture="stderr", break_callback=None)
    assert list(r) == []

    r = execute_cmd(["cat"], capture="both", break_callback=None, input="hello\nworld")
    assert list(r) == ["hello\n", "world"]

    c = Counter()
    with pytest.raises(ProcessTerminated):
        r = execute_cmd(
            ["sleep", "1m"],
            capture="both",
            read_timeout=1,
            break_callback=lambda: c.inc() == 2,
        )
        list(r)
    assert c.n == 2


def test_run():
    client = PodmanEngine(parent=None)
    c = client.run(BUSYBOX, command=["id", "-un"])
    assert isinstance(c, PodmanContainer)

    # If image was pulled the progress logs will also be present
    out = c.logs().splitlines()
    assert out[-1].strip() == b"root", out

    out = c.logs(timestamps=True).splitlines()
    timestamp, msg = out[-1].strip().split(b" ", 1)
    assert re.match(rb"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\S+", timestamp)
    assert msg == b"root", out

    c.remove()
    with pytest.raises(PodmanCommandError) as exc:
        c.reload()
    assert "".join(exc.value.output).strip() == "[]"


def test_run_autoremove():
    client = PodmanEngine(parent=None)
    # Need to sleep in container to prevent race condition
    c = client.run(BUSYBOX, command=["sh", "-c", "sleep 2; id -un"], remove=True)
    # Sleep to ensure container has exited
    sleep(3)
    with pytest.raises(PodmanCommandError) as exc:
        c.reload()
    assert "".join(exc.value.output).strip() == "[]"


def test_run_detach_wait():
    client = PodmanEngine(parent=None)
    c = client.run(BUSYBOX, command=["sh", "-c", "echo before; sleep 5; echo after"])
    assert re.match("^[0-9a-f]{64}$", c.id)
    # If image was pulled the progress logs will also be present
    out = c.logs().splitlines()
    assert out[-1].strip() == b"before", out
    c.wait()
    out = c.logs().splitlines()
    assert out[-1].strip() == b"after", out
    c.remove()
    with pytest.raises(PodmanCommandError) as exc:
        c.reload()
    assert "".join(exc.value.output).strip() == "[]"


def test_run_detach_nostream():
    client = PodmanEngine(parent=None)
    c = client.run(BUSYBOX, command=["id", "-un"])
    assert re.match("^[0-9a-f]{64}$", c.id)
    sleep(1)
    c.reload()
    assert c.status == "exited"
    out = c.logs()
    assert out.strip() == b"root"
    c.remove()
    with pytest.raises(PodmanCommandError):
        c.reload()


def test_run_detach_stream_live():
    client = PodmanEngine(parent=None)
    c = client.run(BUSYBOX, command=["sh", "-c", "sleep 5; id -un"])
    assert isinstance(c, PodmanContainer)
    assert re.match("^[0-9a-f]{64}$", c.id)
    sleep(1)
    c.reload()
    assert c.status == "running"
    out = "\n".join(line.decode("utf-8") for line in c.logs(stream=True))
    assert "".join(out).strip() == "root"
    c.remove()
    with pytest.raises(PodmanCommandError):
        c.reload()


def test_run_detach_stream_exited():
    client = PodmanEngine(parent=None)
    c = client.run(BUSYBOX, command=["id", "-un"])
    assert isinstance(c, PodmanContainer)
    assert re.match("^[0-9a-f]{64}$", c.id)
    sleep(1)
    c.reload()
    assert c.status == "exited"
    out = "\n".join(line.decode("utf-8") for line in c.logs(stream=True))
    assert "".join(out).strip() == "root"
    c.remove()
    with pytest.raises(PodmanCommandError):
        c.reload()


def test_custom_executable(tmp_path):
    # Use a wrapper script to log commands
    log = tmp_path.joinpath("log")
    exe = tmp_path.joinpath("custom_exe.sh")
    with exe.open("w") as f:
        f.write("#!/bin/sh\n")
        f.write(f"echo $@ >> {log}\n")
        f.write("exec podman $@\n")
    exe.chmod(0o755)

    client = PodmanEngine(parent=None)
    client.podman_executable = str(exe)
    client.podman_loglevel = "debug"
    c = client.run(BUSYBOX, command=["id", "-un"])
    assert isinstance(c, PodmanContainer)
    assert c._podman_executable == str(exe)
    cid = c.id

    # If image was pulled the progress logs will also be present
    out = c.logs().splitlines()
    assert out[-1].strip() == b"root", out

    c.remove()

    with log.open() as f:
        lines = f.read().splitlines()
    assert lines == [
        f"run --detach --log-level=debug {BUSYBOX} id -un",
        f"inspect --type container --format json {cid}",
        f"logs {cid}",
        f"rm {cid}",
    ]
