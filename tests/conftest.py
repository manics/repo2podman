"""
Custom test collector for our integration tests.

Each directory that has a script named 'verify' is considered
a test. jupyter-repo2docker is run on that directory,
and then ./verify is run inside the built container. It should
return a non-zero exit code for the test to be considered a
success.
"""

import os
import pipes
import requests
import time

import pytest
import yaml

from repo2docker.__main__ import make_r2d


CONTAINER_ENGINE = os.getenv("CONTAINER_ENGINE")


def pytest_collect_file(parent, path):
    if path.basename == "verify":
        return LocalRepo.from_parent(parent, fspath=path)
    # elif path.basename.endswith(".repos.yaml"):
    #     return RemoteRepoList(path, parent)


def make_test_func(args):
    """Generate a test function that runs repo2docker"""

    def test():
        app = make_r2d(args)
        app.initialize()
        if app.run_cmd:
            # verify test, run it
            app.start()
            return
        # no run_cmd given, starting notebook server
        app.run = False
        app.start()  # This just build the image and does not run it.
        container = app.start_container()
        port = app.port
        # wait a bit for the container to be ready
        container_url = "http://localhost:%s/api" % port
        # give the container a chance to start
        time.sleep(1)
        try:
            # try a few times to connect
            success = False
            for i in range(1, 4):
                container.reload()
                assert container.status == "running"
                try:
                    info = requests.get(container_url).json()
                except Exception as e:
                    print("Error: %s" % e)
                    time.sleep(i * 3)
                else:
                    print(info)
                    success = True
                    break
            assert success, "Notebook never started in %s" % container
        finally:
            # stop the container
            container.stop()
            app.wait_for_container(container)

    return test


class Repo2DockerTest(pytest.Function):
    """A pytest.Item for running repo2docker"""

    def __init__(self, name, parent, args):
        self.args = args
        self.save_cwd = os.getcwd()
        f = parent.obj = make_test_func(args)
        super().__init__(name, parent, callobj=f)

    def reportinfo(self):
        return self.parent.fspath, None, ""

    def repr_failure(self, excinfo):
        err = excinfo.value
        if isinstance(err, SystemExit):
            cmd = "jupyter-repo2docker %s" % " ".join(map(pipes.quote, self.args))
            return "%s | exited with status=%s" % (cmd, err.code)
        else:
            return super().repr_failure(excinfo)

    def teardown(self):
        super().teardown()
        os.chdir(self.save_cwd)


class LocalRepo(pytest.File):
    def collect(self):
        args = [
            "--appendix",
            'RUN echo "appendix" > /tmp/appendix',
            "--engine=podman",
        ]
        if CONTAINER_ENGINE:
            args.append(f"--PodmanEngine.podman_executable={CONTAINER_ENGINE}")
        # If there's an extra-args.yaml file in a test dir, assume it contains
        # a yaml list with extra arguments to be passed to repo2docker
        extra_args_path = os.path.join(self.fspath.dirname, "extra-args.yaml")
        if os.path.exists(extra_args_path):
            with open(extra_args_path) as f:
                extra_args = yaml.safe_load(f)
            args += extra_args

        args.append(self.fspath.dirname)

        yield Repo2DockerTest.from_parent(self, name="build", args=args)
        yield Repo2DockerTest.from_parent(
            self, name=self.fspath.basename, args=args + ["./verify"]
        )
