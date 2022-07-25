ARG REPO2DOCKER_VERSION=2022.02.0-60.g5b688f4
FROM quay.io/jupyterhub/repo2docker:$REPO2DOCKER_VERSION

RUN sed -i s/v3.15/v3.16/ /etc/apk/repositories \
    && apk add --no-cache podman

COPY . /tmp/repo2podman
RUN pip3 install --no-cache-dir \
      /tmp/repo2podman \
    && rm -rf /tmp/repo2podman \
    && pip3 list
