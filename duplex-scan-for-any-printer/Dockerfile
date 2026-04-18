# ARG must be declared before all FROM statements to be usable in FROM
ARG BUILD_FROM

# Stage 1: Build Vue frontend
FROM node:20-slim AS web-builder
WORKDIR /web_ui
COPY web_ui/package.json web_ui/package-lock.json ./
RUN npm ci
COPY web_ui/ ./
RUN npm run build

# Stage 2: Main HA addon image
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /usr/src

ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Install system dependencies
RUN \
    dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-dev \
        cups \
        cups-client \
        cups-bsd \
        cups-ipp-utils \
        libcups2 \
        libcupsimage2 \
        libvips \
        libc6:i386 \
        libstdc++6:i386 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Brother printer drivers (all .deb files, sorted — LPR before wrapper)
COPY drivers/*.deb /tmp/drivers/
RUN \
    for deb in $(ls /tmp/drivers/*.deb | sort); do dpkg -i "$deb" || true; done \
    && apt-get update && apt-get install -f -y \
    && rm -rf /tmp/drivers /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Copy application
WORKDIR /app
COPY src/ ./src/
COPY checkpoints/ ./checkpoints/
COPY --from=web-builder /web_ui/dist/ ./web_ui/dist/

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/src

WORKDIR /

# Bust cache for rootfs on every build so script changes are always picked up
ARG CACHE_BUST=1
COPY rootfs /

RUN chmod -R a+x /etc/s6-overlay/s6-rc.d
