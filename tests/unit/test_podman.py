"""Tests for podman client"""

import pytest
import re
from repo2podman.podman import PodmanCommandError, PodmanContainer, PodmanEngine
from time import sleep


def test_run():
    client = PodmanEngine(parent=None)
    c = client.run("busybox", command=["id", "-un"])
    assert isinstance(c, PodmanContainer)
    # If image was pulled the progress logs will also be present
    out = c.logs()
    # assert len(out) == 1
    assert out[-1].strip() == "root", out
    c.remove()


@pytest.mark.parametrize("autoremove", (True, False))
def test_run_remove(autoremove):
    client = PodmanEngine(parent=None)
    c = client.run("busybox", command=["id", "-un"], remove=autoremove)
    if not autoremove:
        c.reload()
        c.remove()
        sleep(0.1)
    with pytest.raises(PodmanCommandError) as exc:
        c.reload()
    msg = "".join(exc.value.output)
    assert "error looking up container" in msg


def test_run_detach_nostream():
    client = PodmanEngine(parent=None)
    c = client.run("busybox", command=["id", "-un"])
    assert re.match("^[0-9a-f]{64}$", c.id)
    sleep(1)
    c.reload()
    assert c.status == "exited"
    out = "".join(c.logs())
    assert out.strip() == "root"
    c.remove()
    with pytest.raises(PodmanCommandError):
        c.reload()


def test_run_detach_stream_live():
    client = PodmanEngine(parent=None)
    c = client.run("busybox", command=["sh", "-c", "sleep 5; id -un"])
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
    c = client.run("busybox", command=["id", "-un"])
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
