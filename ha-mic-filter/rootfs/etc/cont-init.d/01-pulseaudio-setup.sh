#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Community Add-on: Real-time Microphone Filter
# Setup PulseAudio for virtual microphone device creation
# ==============================================================================

bashio::log.info "Setting up PulseAudio for virtual microphone..."

# Create PulseAudio configuration directory in writable location
mkdir -p /tmp/pulse-config

# Get virtual microphone name from Home Assistant config
VIRTUAL_MIC_NAME="${VIRTUAL_MIC_NAME:-HA_Filtered_Mic}"

# Create PulseAudio system configuration (minimal to avoid conflicts)
cat > /tmp/pulse-config/system.pa << EOF
#!/usr/bin/pulseaudio -nF

# Essential modules only to avoid duplicates
.ifexists module-device-restore.so
.nofail
load-module module-device-restore
.fail
.endif

.ifexists module-stream-restore.so
.nofail
load-module module-stream-restore
.fail
.endif

# Load null sink for virtual microphone (using configurable name)
load-module module-null-sink sink_name=virtual_mic_sink sink_properties=device.description="Virtual_Microphone_Sink"

# Load virtual source (microphone) from the null sink monitor
load-module module-virtual-source source_name=virtual_mic source_properties=device.description="${VIRTUAL_MIC_NAME}" master=virtual_mic_sink.monitor

# Load loopback module for real-time processing
load-module module-loopback

# Load external access protocol on different socket
load-module module-native-protocol-unix auth-anonymous=1 socket=/tmp/pulse-external-socket

# Set default devices
set-default-sink virtual_mic_sink
EOF

# Create PulseAudio client configuration
cat > /tmp/pulse-config/client.conf << 'EOF'
default-server = unix:/tmp/pulse-external-socket
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