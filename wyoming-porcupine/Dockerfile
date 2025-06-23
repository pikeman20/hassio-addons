ARG BUILD_FROM
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /usr/src
COPY . /wyoming-porcupine
ARG WYOMING_PORCUPINE_VERSION
ENV PIP_BREAK_SYSTEM_PACKAGES=1

RUN \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        netcat-traditional \
        python3 \
        python3-pip \
        libopenblas0 \
    && pip3 install --no-cache-dir -U \
        setuptools \
        wheel \
    && pip3 install --no-cache-dir /wyoming-porcupine \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /

COPY rootfs /

RUN chmod -R a+x /etc/s6-overlay/s6-rc.d

HEALTHCHECK --start-period=10m \
    CMD echo '{ "type": "describe" }' \
        | nc -w 1 localhost 11500 \
        | grep -iq "porcupine" \
        || exit 1