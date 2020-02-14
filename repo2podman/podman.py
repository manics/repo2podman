# Use Podman instead of Docker
import json
import re
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
import tarfile
from traitlets import Unicode

from repo2docker.engine import (
    Container,
    ContainerEngine,
    ContainerEngineException,
    Image,
)
from repo2docker.utils import execute_cmd


def exec_podman(args, capture=False, **kwargs):
    cmd = ["podman"] + args
    print("Executing: {} {}".format(" ".join(cmd), kwargs))
    try:
        p = execute_cmd(cmd, capture=capture, **kwargs)
    except CalledProcessError:
        print(kwargs["stdout"])
        print(kwargs["stderr"])
        raise
    if capture:
        yield from p
    for line in p:
        print(line)
        # pass


class PodmanContainer(Container):
    def __init__(self, cid):
        self.id = cid
        self.reload()

    def reload(self):
        lines = list(
            exec_podman(
                ["inspect", "--type", "container", "--format", "json", self.id],
                capture=True,
            )
        )
        d = json.loads("".join(lines))
        assert len(d) == 1
        self.attrs = d[0]
        assert self.attrs["Id"] == self.id

    def logs(self, *, stream=False):
        if stream:

            def iter_logs(cid):
                exited = False
                try:
                    for line in exec_podman(
                        ["attach", "--no-stdin", cid], capture=True
                    ):
                        if exited or line.startswith(
                            "Error: you can only attach to running containers"
                        ):
                            # Swallow all output to ensure process exited
                            print(line)
                            exited = True
                            continue
                        else:
                            yield line.encode("utf-8")
                except CalledProcessError as e:
                    print(e, line.encode("utf-8"))
                    if e.returncode == 125 and exited:
                        for line in exec_podman(["logs", self.id], capture=True):
                            yield line.encode("utf-8")
                    else:
                        raise

            return iter_logs(self.id)
        return "".join(exec_podman(["logs", self.id], capture=True))

    def kill(self, *, signal="KILL"):
        for line in exec_podman(["kill", "--signal", signal, self.id]):
            print(line)

    def remove(self):
        print("podman remove")
        cmdargs = ["rm"]
        for line in exec_podman(cmdargs + [self.id]):
            print(line)

    def stop(self, *, timeout=10):
        for line in exec_podman(["stop", "--timeout", str(timeout), self.id]):
            print(line)

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

        exec_podman(["info"])

        print(self.default_transport)

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
        **kwargs
    ):
        print("podman build")
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
                print(builddir)
                for line in execute_cmd(["ls", "-lRa", builddir]):
                    print(line)
                for line in exec_podman(cmdargs + [builddir], capture=True):
                    yield line
        else:
            builddir = path
            assert path
            for line in exec_podman(cmdargs + [builddir], capture=True):
                yield line

    def images(self):
        def remove_local(tags):
            if tags:
                for tag in tags:
                    # yield original and normalised tag
                    yield tag
                    if tag.startswith("localhost/"):
                        yield tag[10:]

        lines = "".join(
            exec_podman(["image", "list", "--format", "json"], capture=True)
        )
        if lines.strip():
            images = json.loads(lines)
            return [Image(tags=list(remove_local(image["names"]))) for image in images]
        return []

    def inspect_image(self, image):
        lines = list(
            exec_podman(
                ["inspect", "--type", "image", "--format", "json", image], capture=True
            )
        )
        d = json.loads("".join(lines))
        assert len(d) == 1
        tags = d[0]["RepoTags"]
        config = d[0]["Config"]
        if "WorkingDir" not in config:
            print("inspect_image: WorkingDir not found, setting to /")
            config["WorkingDir"] = "/"
        image = Image(tags=tags, config=config)
        return image

    def push(self, image_spec):
        if re.match("\w+://", image_spec):
            destination = image_spec
        else:
            destination = self.default_transport + image_spec
        args = ["push", image_spec, destination]

        def iter_out():
            for line in exec_podman(args, capture=True):
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
        **kwargs
    ):
        print("podman run")
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

        cmdargs.append("--rm")

        command = command or []

        if kwargs:
            raise ValueError("Additional kwargs not supported")

        cmdline = cmdargs + [image_spec] + command
        lines = list(exec_podman(cmdline, capture=True))

        # If image was pulled the progress logs will also be present
        # assert len(lines) == 1, lines
        return PodmanContainer(lines[-1].strip())
