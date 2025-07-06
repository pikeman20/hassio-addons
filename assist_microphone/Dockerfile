ARG BUILD_FROM
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /usr/src
ARG WYOMING_SATELLITE_VERSION
ENV PIP_BREAK_SYSTEM_PACKAGES=1

RUN \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        git netcat-traditional \
        libasound2-plugins \
        alsa-utils \
        python3 \
        python3-pip \
    \
    && pip3 install --no-cache-dir -U \
        setuptools \
        wheel \
    && pip3 install --no-cache-dir \
        "git+https://github.com/pikeman20/wyoming-satellite.git#egg=wyoming-satellite[webrtc]" \
    \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY sounds/ ./sounds/

WORKDIR /
COPY rootfs /

RUN chmod -R a+x /etc/s6-overlay/s6-rc.d

HEALTHCHECK --start-period=10m \
    CMD echo '{ "type": "describe" }' \
        | nc -w 1 localhost 11700 \
        | grep -q "assist" \
        || exit 1
