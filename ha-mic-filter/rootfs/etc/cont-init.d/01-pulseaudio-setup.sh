#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Community Add-on: Real-time Microphone Filter
# Setup PulseAudio for virtual microphone device creation
# ==============================================================================

bashio::log.info "Setting up PulseAudio for virtual microphone..."

# Create PulseAudio configuration directory in writable location
mkdir -p /tmp/pulse-config

# Create PulseAudio system configuration
cat > /tmp/pulse-config/system.pa << 'EOF'
#!/usr/bin/pulseaudio -nF

# Load basic modules first
load-module module-device-restore
load-module module-stream-restore
load-module module-card-restore

# Try to load ALSA modules, but continue if they fail (container environment)
.ifexists module-udev-detect.so
load-module module-udev-detect
.endif

# Load native protocol first for basic connectivity
load-module module-native-protocol-unix

# Load fallback null sink (this will be loaded by module-always-sink if no other sinks)
load-module module-always-sink

# Load suspend on idle
load-module module-suspend-on-idle

# Load position event sounds
load-module module-position-event-sounds

# Try to load ALSA sink/source modules, but continue if they fail
.ifexists module-alsa-sink.so
.nofail
load-module module-alsa-sink
.fail
.endif

.ifexists module-alsa-source.so
.nofail
load-module module-alsa-source
.fail
.endif

# Load null sink for virtual microphone
load-module module-null-sink sink_name=virtual_mic_sink sink_properties=device.description="Virtual_Microphone_Sink"

# Load virtual source (microphone) from the null sink monitor
load-module module-virtual-source source_name=virtual_mic source_properties=device.description="HA_Filtered_Microphone" master=virtual_mic_sink.monitor

# Load loopback module for real-time processing
load-module module-loopback

# Load additional protocol modules
load-module module-native-protocol-unix auth-anonymous=1 socket=/tmp/pulse-socket
load-module module-cli-protocol-unix

# Set default devices
set-default-sink virtual_mic_sink
EOF

# Create PulseAudio client configuration
cat > /tmp/pulse-config/client.conf << 'EOF'
default-server = unix:/tmp/pulse-socket
autospawn = no
EOF

# Create PulseAudio daemon configuration
cat > /tmp/pulse-config/daemon.conf << 'EOF'
system-instance = yes
disable-shm = yes
exit-idle-time = -1
flat-volumes = no
rlimit-memlock = -1
high-priority = no
realtime-scheduling = no
nice-level = 0
EOF

# Set environment variable for PulseAudio to find the config files
export PULSE_CONFIG_PATH=/tmp/pulse-config

bashio::log.info "PulseAudio configuration created successfully"