ARG BUILD_FROM
FROM $BUILD_FROM

# Install system dependencies for PulseAudio, GStreamer, LADSPA, and audio processing
RUN apt update && apt install -y \
    lsp-plugins \
    tap-plugins \
    libpulse0 \
    libpulse-dev \
    pulseaudio \
    libatomic1 \
    alsa-utils \
    ladspa-sdk \
    cmt \
    swh-plugins \
    libasound2-plugins \
    gstreamer1.0-pulseaudio \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-tools \
    bash \
    jq \
 && rm -rf /var/lib/apt/lists/*

COPY run.sh /
RUN chmod a+x /run.sh

# Copy rnnoise LADSPA plugin to LADSPA plugin directory

ENV PULSE_SERVER=unix:/run/audio/pulse.sock
# Set plugin environment paths
ENV LADSPA_PATH=/usr/lib/ladspa \
    LV2_PATH=/usr/lib/lv2 \
    VST_PATH=/usr/lib/vst \
    VST3_PATH=/usr/lib/vst3

# Copy plugins into standard paths
COPY noise-suppression/ladspa/librnnoise_ladspa.so /usr/lib/ladspa/
COPY noise-suppression/rnnoise_mono.lv2 /usr/lib/lv2/rnnoise_mono.lv2
COPY noise-suppression/rnnoise_stereo.lv2 /usr/lib/lv2/rnnoise_stereo.lv2
COPY noise-suppression/vst/*.so /usr/lib/vst/
COPY noise-suppression/rnnoise.vst3 /usr/lib/vst3/rnnoise.vst3

RUN chmod +x /usr/lib/ladspa/librnnoise_ladspa.so \
     /usr/lib/lv2/rnnoise_mono.lv2/* \
     /usr/lib/lv2/rnnoise_stereo.lv2/* \
     /usr/lib/vst/*.so \
     /usr/lib/vst3/rnnoise.vst3/*

COPY rootfs/ /

RUN chmod a+x /etc/cont-init.d/*

CMD [ "./run.sh" ]