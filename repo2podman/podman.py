# Use Podman instead of Docker
from functools import partial
import json
import logging
from queue import Queue, Empty
import re
from subprocess import CalledProcessError, PIPE, STDOUT, Popen
import tarfile
from tempfile import TemporaryDirectory
from threading import Thread
from traitlets import Unicode

from repo2docker.engine import (
    Container,
    ContainerEngine,
    Image,
)


DEFAULT_READ_TIMEOUT = 1

# Use repo2docker logger so that we use custom formatters
# https://github.com/jupyterhub/repo2docker/blob/2021.08.0/repo2docker/app.py#L483-L486


def log_debug(m):
    log = logging.getLogger("repo2docker")
    if isinstance(m, list):
        log.debug("".join(m))
    else:
        log.debug(m)


def log_info(m):
    log = logging.getLogger("repo2docker")
    if isinstance(m, list):
        log.info("".join(m))
    else:
        log.info(m)


class ProcessTerminated(CalledProcessError):
    """
    Thrown when a process was forcibly terminated
    """

    def __init__(self, message=None):
        self.message = message

    def __str__(self):
        s = "ProcessTerminated\n  {}\n  {}".format(self.e, self.message)
        return s


def execute_cmd(cmd, capture=None, *, read_timeout=None, break_callback=None, **kwargs):
    """
    Call given command, yielding output line by line if capture is set.

    break_callback: A callable that returns a boolean indicating whether to
    stop execution.
    See https://stackoverflow.com/a/4896288
    This is needed to work around https://github.com/manics/repo2podman/issues/6
    If a process is terminated due to break_callback then ProcessTerminated is thrown

    Modified version of repo2docker.utils.execute_cmd
    that allows capturing of stdout, stderr or both.

    Must be yielded from.
    """
    if capture == "stdout":
        kwargs["stdout"] = PIPE
    elif capture == "stderr":
        kwargs["stderr"] = PIPE
    elif capture == "both":
        kwargs["stdout"] = PIPE
        kwargs["stderr"] = STDOUT
        capture = "stdout"
    elif capture is not None:
        raise ValueError("Invalid capture argument: {}".format(capture))

    if read_timeout is None:
        read_timeout = DEFAULT_READ_TIMEOUT

    proc = Popen(cmd, **kwargs)

    if not capture:
        # not capturing output, let subprocesses talk directly to terminal
        ret = proc.wait()
        if ret != 0:
            raise CalledProcessError(ret, cmd)
        return

    # Capture output for logging.
    # Each line will be yielded as text.
    # This should behave the same as .readline(), but splits on `\r` OR `\n`,
    # not just `\n`.
    buf = []
    q = Queue()

    def readToQueue(proc, capture, q):
        try:
            for c in iter(partial(getattr(proc, capture).read, 1), b""):
                q.put(c)
        finally:
            proc.wait()

    def flush():
        """Flush next line of the buffer"""
        line = b"".join(buf).decode("utf8", "replace")
        buf[:] = []
        return line

    t = Thread(target=readToQueue, args=(proc, capture, q))
    # thread dies with the program
    t.daemon = True
    t.start()

    c_last = ""
    terminate = False
    terminated = False
    while True:
        try:
            c = q.get(block=True, timeout=read_timeout)
            if c_last == b"\r" and buf and c != b"\n":
                yield flush()
            buf.append(c)
            if c == b"\n":
                yield flush()
            c_last = c
        except Empty:
            # Only terminate if timeout occurred so that all output has been read
            if proc.poll() is not None:
                break
            if terminate:
                proc.terminate()
                terminated = True
                break
            if break_callback:
                terminate = break_callback()
    if buf:
        yield flush()

    t.join()

    if terminated:
        raise ProcessTerminated(cmd)
    if proc.returncode != 0:
        raise CalledProcessError(proc.returncode, cmd)


class PodmanCommandError(Exception):
    def __init__(self, error, output=None):
        self.e = error
        self.output = output

    def __str__(self):
        s = "PodmanCommandError\n  {}".format(self.e)
        if self.output is not None:
            s += "\n  {}".format("".join(self.output))
        return s


def exec_podman(args, *, capture, read_timeout=None, break_callback=None):
    """
    Execute a podman command
    capture:
    - None: Command will output directly to terminal, raise PodmanCommandError if
      exit code is not 0
    - "both": Capture stdout and stderr combined
    - "stdout": Capture stdout
    - "stderr": Capture stderr

    Raises PodmanCommandError if exit code is not 0 (if capturing this will include
    any output that occurred before the exception).
    Note podman usually exits with code 125 if a podman error occurred to differentiate
    it from the exit code of the container.
    """
    cmd = ["podman"] + args
    log_debug("Executing: {}".format(" ".join(cmd)))
    try:
        p = execute_cmd(cmd, capture=capture, break_callback=break_callback)
    except CalledProcessError as e:
        raise PodmanCommandError(e) from None
    # Need to iterate even if not capturing because execute_cmd is a generator
    lines = []
    try:
        for line in p:
            # log_debug(line)
            lines.append(line)
        return lines
    except CalledProcessError as e:
        raise PodmanCommandError(e, lines) from None


def exec_podman_stream(args, *, read_timeout=None, break_callback=None):
    """
    Execute a podman command and stream the output

    Passes on CalledProcessError if exit code is not 0
    """
    cmd = ["podman"] + args
    log_debug("Executing: {}".format(" ".join(cmd)))
    p = execute_cmd(cmd, capture="both", break_callback=break_callback)
    # This will stream the output and also pass any exceptions to the caller
    yield from p


class PodmanContainer(Container):
    def __init__(self, cid):
        self.id = cid
        self.reload()

    def reload(self):
        lines = exec_podman(
            ["inspect", "--type", "container", "--format", "json", self.id],
            capture="stdout",
        )
        d = json.loads("".join(lines))
        assert len(d) == 1
        self.attrs = d[0]
        assert self.attrs["Id"].startswith(self.id)

    def _exited(self):
        status = "\n".join(
            exec_podman(
                ["inspect", "--format={{.State.Status}}", self.id], capture="both"
            )
        )
        return status.strip() == "exited"

    def logs(self, *, stream=False, timestamps=False, since=None):
        log_command = ["logs"]
        if timestamps:
            log_command.append("--timestamps")
        if since:
            log_command.extend(["--since", since])

        if stream:

            # Podman logs --follow may hang if container is stopped
            def iter_logs(cid):
                try:
                    for line in exec_podman_stream(
                        log_command + ["--follow", cid],
                        read_timeout=2,
                        break_callback=self._exited,
                    ):
                        yield line.encode("utf-8")
                except ProcessTerminated:
                    # Popen.terminate was called
                    pass

            return iter_logs(self.id)

        return "\n".join(exec_podman(log_command + [self.id], capture="both")).encode(
            "utf-8"
        )

    def kill(self, *, signal="KILL"):
        lines = exec_podman(["kill", "--signal", signal, self.id], capture="stdout")
        log_info(lines)

    def remove(self):
        lines = exec_podman(["rm", self.id], capture="stdout")
        log_info(lines)

    def stop(self, *, timeout=10):
        lines = exec_podman(
            ["stop", "--timeout", str(timeout), self.id], capture="stdout"
        )
        log_info(lines)

    def wait(self):
        lines = exec_podman(["wait", self.id], capture="stdout")
        log_info(lines)

    @property
    def exitcode(self):
        return self.attrs["State"]["ExitCode"]

    @property
    def status(self):
        return self.attrs["State"]["Status"]


class PodmanEngine(ContainerEngine):
    """
    Podman container engine
    """

    def __init__(self, *, parent):
        super().__init__(parent=parent)

        lines = exec_podman(["info"], capture="stdout")
        log_debug(lines)

    default_transport = Unicode(
        "docker://docker.io/",
        help="""
        Default transport image protocol if not specified in the image tag
        """,
        config=True,
    )

    def build(
        self,
        *,
        buildargs=None,
        cache_from=None,
        container_limits=None,
        tag="",
        custom_context=False,
        dockerfile="",
        fileobj=None,
        path="",
        **kwargs,
    ):
        log_debug("podman build")
        cmdargs = ["build"]

        bargs = buildargs or {}
        for k, v in bargs.items():
            cmdargs.extend(["--build-arg", "{}={}".format(k, v)])

        # podman --cache-from is a NOOP
        if cache_from:
            cmdargs.extend(["--cache-from", ",".join(cache_from)])

        try:
            climits = container_limits or {}
            try:
                cmdargs.extend(["--cpuset-cpus", climits.pop("cpusetcpus")])
            except KeyError:
                pass
            try:
                cmdargs.extend(["--cpu-shares", climits.pop("cpushares")])
            except KeyError:
                pass
            try:
                cmdargs.extend(["--memory", climits.pop("memory")])
            except KeyError:
                pass
            try:
                cmdargs.extend(["--memory-swap", climits.pop("memswap")])
            except KeyError:
                pass
        except KeyError:
            pass

        cmdargs.append("--force-rm")

        cmdargs.append("--rm")

        if tag:
            cmdargs.extend(["--tag", tag])

        if dockerfile:
            cmdargs.extend(["--file", dockerfile])

        # TODO: what to do with these?
        # for ignore in ("custom_context", "decode"):
        #     try:
        #         kwargs.pop(ignore)
        #     except KeyError:
        #         pass

        if kwargs:
            raise ValueError("Additional kwargs not supported")

        # Avoid try-except so that if build errors occur they don't result in a
        # confusing message about an exception whilst handling an exception
        if fileobj:
            with TemporaryDirectory() as builddir:
                tarf = tarfile.open(fileobj=fileobj)
                tarf.extractall(builddir)
                log_debug(builddir)

                lines = execute_cmd(["ls", "-lRa", builddir], capture="stdout")
                log_debug(lines)
                for line in exec_podman_stream(cmdargs + [builddir]):
                    yield line
        else:
            builddir = path
            assert path
            for line in exec_podman_stream(cmdargs + [builddir]):
                yield line

    def images(self):
        def remove_local(tags):
            if tags:
                for tag in tags:
                    # yield original and normalised tag
                    yield tag
                    if tag.startswith("localhost/"):
                        yield tag[10:]

        lines = exec_podman(["image", "list", "--format", "json"], capture="stdout")
        lines = "".join(lines)

        if lines.strip():
            images = json.loads(lines)
            try:
                return [
                    Image(tags=list(remove_local(image["names"]))) for image in images
                ]
            except KeyError:
                # Podman 1.9.1+
                # Some images may not have a name
                return [
                    Image(tags=list(remove_local(image["Names"])))
                    for image in images
                    if "Names" in image
                ]
        return []

    def inspect_image(self, image):
        lines = exec_podman(
            ["inspect", "--type", "image", "--format", "json", image], capture="stdout"
        )
        d = json.loads("".join(lines))
        assert len(d) == 1
        tags = d[0]["RepoTags"]
        config = d[0]["Config"]
        if "WorkingDir" not in config:
            log_debug("inspect_image: WorkingDir not found, setting to /")
            config["WorkingDir"] = "/"
        image = Image(tags=tags, config=config)
        return image

    def push(self, image_spec):
        if re.match(r"\w+://", image_spec):
            destination = image_spec
        else:
            destination = self.default_transport + image_spec
        args = ["push", image_spec, destination]

        def iter_out():
            for line in exec_podman_stream(args):
                yield line

        return iter_out()

    def run(
        self,
        image_spec,
        *,
        command=None,
        environment=None,
        ports=None,
        publish_all_ports=False,
        remove=False,
        volumes=None,
        **kwargs,
    ):
        log_debug("podman run")
        cmdargs = ["run"]

        if publish_all_ports:
            cmdargs.append("--publish-all")

        ports = ports or {}
        for k, v in ports.items():
            if k.endswith("/tcp"):
                k = k[:-4]
            cmdargs.extend(["--publish", "{}:{}".format(k, v)])

        cmdargs.append("--detach")

        volumes = volumes or {}
        for k, v in volumes.items():
            raise NotImplementedError("podman run volumes not implemented")

        env = environment or []
        for e in env:
            cmdargs.extend(["--env", e])

        if remove:
            cmdargs.append("--rm")

        # TODO: Make this configurable via a config traitlet
        cmdargs.append("--log-level=debug")

        command = command or []

        if kwargs:
            raise ValueError("Additional kwargs not supported")

        cmdline = cmdargs + [image_spec] + command
        lines = exec_podman(cmdline, capture="stdout")

        # Note possible race condition:
        # If the container exits immediately and remove=True the next line may fail
        # since it's not possible to fetch the container details

        # If image was pulled the progress logs will also be present
        # assert len(lines) == 1, lines
        return PodmanContainer(lines[-1].strip())
