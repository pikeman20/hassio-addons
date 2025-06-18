#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Community Add-on: Real-time Microphone Filter
# Setup PulseAudio for virtual microphone device creation
# ==============================================================================

bashio::log.info "Setting up PulseAudio for virtual microphone..."

# Create PulseAudio configuration directory
mkdir -p /etc/pulse

# Create PulseAudio system configuration
cat > /etc/pulse/system.pa << 'EOF'
#!/usr/bin/pulseaudio -nF

# Load audio drivers
load-module module-alsa-sink
load-module module-alsa-source

# Load null sink for virtual microphone
load-module module-null-sink sink_name=virtual_mic_sink sink_properties=device.description="Virtual_Microphone_Sink"

# Load virtual source (microphone) from the null sink monitor
load-module module-virtual-source source_name=virtual_mic source_properties=device.description="HA_Filtered_Microphone" master=virtual_mic_sink.monitor

# Load loopback module for real-time processing
load-module module-loopback

# Load native protocol
load-module module-native-protocol-unix auth-anonymous=1 socket=/tmp/pulse-socket

# Load CLI protocol for control
load-module module-cli-protocol-unix

# Set default devices
set-default-sink virtual_mic_sink
EOF

# Create PulseAudio client configuration
cat > /etc/pulse/client.conf << 'EOF'
default-server = unix:/tmp/pulse-socket
autospawn = no
EOF

# Create PulseAudio daemon configuration
cat > /etc/pulse/daemon.conf << 'EOF'
system-instance = yes
disable-shm = yes
exit-idle-time = -1
flat-volumes = no
rlimit-memlock = -1
EOF

bashio::log.info "PulseAudio configuration created successfully"