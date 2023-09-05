ARG PODMAN_VERSION=v4.6.1
FROM quay.io/podman/stable:$PODMAN_VERSION

RUN dnf install -y -q \
      git \
      git-lfs \
      mercurial \
      python3-pip && \
    dnf clean all

RUN pip install \
      hg-evolve \
      jupyter-repo2docker

# To be compatible with Docker:
RUN sed -i -r \
    -e 's/unqualified-search-registries .+/unqualified-search-registries = ["docker.io"]/' \
    /etc/containers/registries.conf

# add git-credential helper
COPY ./helpers/git-credential-env /usr/local/bin/git-credential-env
RUN git config --system credential.helper env

ADD . /repo2podman
RUN pip install /repo2podman
