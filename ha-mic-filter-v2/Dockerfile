FROM ghcr.io/home-assistant/amd64-base

# Install system dependencies for PulseAudio, GStreamer, LADSPA, and audio processing
RUN apk add --no-cache \
    alsa-lib \
    alsa-lib-dev \
    alsa-plugins-pulse \
    alsa-utils \
    pulseaudio \
    pulseaudio-dev \
    pulseaudio-utils \
    portaudio-dev \
    ladspa-sdk \
    swh-plugins \
    libgstrnnoise \
    gstreamer \
    gstreamer-plugins-base \
    gstreamer-plugins-good \
    gstreamer-plugins-bad \
    gstreamer-plugins-ugly \
    gstreamer-plugins-libav \
    bash \
    jq

COPY run.sh /
RUN chmod a+x /run.sh

ENV PULSE_SERVER=unix:/run/audio/pulse.sock

CMD [ "/run.sh" ]