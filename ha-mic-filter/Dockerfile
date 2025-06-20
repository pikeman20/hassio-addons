ARG BUILD_FROM
FROM $BUILD_FROM

# Install system dependencies
RUN apk add --no-cache \
    alsa-lib \
    alsa-lib-dev \
    alsa-plugins-pulse \
    alsa-utils \
    pulseaudio \
    pulseaudio-dev \
    pulseaudio-utils \
    portaudio-dev \
    gcc \
    g++ \
    make \
    cmake \
    musl-dev \
    linux-headers \
    git \
    curl \
    bash \
    jq \
    nodejs \
    npm

# Install Python dependencies
RUN pip3 install --break-system-packages \
    numpy \
    pulsectl \
    sounddevice \
    pyaudio

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
COPY device_constants.py /app/

# Set permissions
RUN chmod a+x /etc/services.d/*/run
RUN chmod a+x /etc/services.d/*/finish
RUN chmod a+x /etc/cont-init.d/*

# Copy and set permissions for run script
COPY run.sh /
RUN chmod a+x /run.sh

# Set environment variables for container
ENV PULSE_SERVER=unix:/tmp/pulse-external-socket
ENV PULSE_SCRIPT=/tmp/pulse-config/system.pa
ENV PULSE_CONFIG_PATH=/tmp/pulse-config

# Labels
LABEL \
    io.hass.name="Real-time Microphone Filter" \
    io.hass.type="addon" \
    io.hass.arch="aarch64|amd64|armv7" \
    io.hass.version="1.0.28"

# Main command
CMD [ "/run.sh" ]