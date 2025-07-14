ARG BUILD_FROM
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /usr/src
COPY ../bumper-dev /bumper-dev

ARG BUMPER_VERSION
ENV PIP_BREAK_SYSTEM_PACKAGES=1

RUN \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
    && pip3 install --no-cache-dir uv

WORKDIR /bumper-dev

RUN uv sync --no-dev

WORKDIR /

COPY rootfs /

RUN chmod -R a+x /etc/s6-overlay/s6-rc.d
