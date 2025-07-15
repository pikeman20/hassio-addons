ARG BUILD_FROM
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /usr/src

ARG BUMPER_VERSION
ENV PIP_BREAK_SYSTEM_PACKAGES=1

RUN \
    apk add --no-cache git \
    && pip3 install --no-cache-dir uv

RUN git clone https://github.com/pikeman20/bumper-dev.git /bumper-dev

WORKDIR /bumper-dev

RUN uv sync

WORKDIR /

COPY rootfs /

RUN chmod -R a+x /etc/s6-overlay/s6-rc.d
