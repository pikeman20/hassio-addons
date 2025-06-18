ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.18
ARG BUILD_ARCH=amd64
FROM $BUILD_FROM

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    python3-dev \
    py3-pip \
    pulseaudio \
    pulseaudio-dev \
    pulseaudio-utils \
    alsa-utils \
    alsa-lib-dev \
    portaudio-dev \
    gcc \
    g++ \
    make \
    cmake \
    git \
    curl \
    bash \
    jq \
    nodejs \
    npm

# Install Python dependencies
RUN pip3 install --no-cache-dir \
    numpy \
    pyaudio \
    pulsectl \
    sounddevice

# Copy obs-plugin and rnnoise
COPY obs-plugin /tmp/obs-plugin
COPY rnnoise /tmp/rnnoise

WORKDIR /tmp/obs-plugin

# Build obs-mic-filter for Linux
RUN rm -rf build-linux && \
    mkdir -p build-linux && \
    cd build-linux && \
    cmake .. -DCMAKE_BUILD_TYPE=Release && \
    make -j$(nproc)

# Create application directory and copy built library
WORKDIR /app
RUN mkdir -p /app/lib
RUN cp /tmp/obs-plugin/build-linux/libobs-mic-filter.so /app/lib/ || \
    cp /tmp/obs-plugin/build-linux/obs-mic-filter.so /app/lib/libobs-mic-filter.so

# Copy rootfs
COPY rootfs /

# Copy audio processing modules
COPY audio_pipeline_manager.py /app/
COPY pulse_audio_manager.py /app/
COPY ha_mic_filter_service.py /app/

# Set permissions
RUN chmod a+x /etc/services.d/*/run
RUN chmod a+x /etc/services.d/*/finish
RUN chmod a+x /etc/cont-init.d/*


# Labels
LABEL \
    io.hass.name="Real-time Microphone Filter" \
    io.hass.description="Real-time microphone filtering for Home Assistant Assist" \
    io.hass.arch="amd64" \
    io.hass.type="addon" \
    io.hass.version="1.0.0"