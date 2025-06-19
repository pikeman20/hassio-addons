#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Community Add-on: Real-time Microphone Filter
# Setup virtual microphone devices using Home Assistant's PulseAudio
# ==============================================================================

bashio::log.info "Setting up virtual microphone devices..."

# Get virtual microphone name from Home Assistant config
VIRTUAL_MIC_NAME="${VIRTUAL_MIC_NAME:-HA_Filtered_Mic}"

# Set up PulseAudio environment for Home Assistant
export PULSE_SERVER=unix:/run/audio/pulse.sock

# Wait for Home Assistant's PulseAudio socket to be available
sleep 5

# Function to check if PulseAudio is ready
check_pulseaudio() {
    pactl info >/dev/null 2>&1
}

# Check if Home Assistant PulseAudio socket exists
if [ ! -S "/run/audio/pulse.sock" ]; then
    bashio::log.warning "Home Assistant PulseAudio socket not found at /run/audio/pulse.sock"
    bashio::log.info "Checking fallback locations..."
    
    # Check alternative socket locations as fallback
    if [ -S "/var/run/pulse/native" ]; then
        export PULSE_SERVER=unix:/var/run/pulse/native
        bashio::log.info "Using fallback PulseAudio socket at /var/run/pulse/native"
    elif [ -S "/run/pulse/native" ]; then
        export PULSE_SERVER=unix:/run/pulse/native
        bashio::log.info "Using fallback PulseAudio socket at /run/pulse/native"
    else
        bashio::log.warning "No PulseAudio socket found, will try default connection"
        unset PULSE_SERVER
    fi
else
    bashio::log.info "Using Home Assistant PulseAudio socket at /run/audio/pulse.sock"
fi

# Wait for PulseAudio to be ready (up to 30 seconds)
for i in {1..30}; do
    if check_pulseaudio; then
        bashio::log.info "PulseAudio server is ready"
        break
    fi
    bashio::log.info "Waiting for PulseAudio server... (attempt $i/30)"
    sleep 1
done

if ! check_pulseaudio; then
    bashio::log.error "PulseAudio server not available after 30 seconds"
    bashio::log.info "PULSE_SERVER: ${PULSE_SERVER:-not set}"
    bashio::log.info "Available sockets in /var/run/pulse/:"
    ls -la /var/run/pulse/ 2>/dev/null || bashio::log.info "Directory not found"
    bashio::log.info "Available sockets in /run/pulse/:"
    ls -la /run/pulse/ 2>/dev/null || bashio::log.info "Directory not found"
    bashio::log.warning "Cannot connect to PulseAudio - skipping virtual device creation"
    bashio::log.info "Container will continue running for debugging"
    exit 0
fi

# Get server info for debugging
bashio::log.info "PulseAudio server info:"
pactl info | grep -E "(Server Version|Default Sink|Default Source)" || true

# Clean up any existing virtual devices with the same names
bashio::log.info "Cleaning up existing virtual devices..."
pactl unload-module module-null-sink 2>/dev/null || true
pactl unload-module module-virtual-source 2>/dev/null || true

# Create virtual sink for the filtered microphone
bashio::log.info "Creating virtual sink..."
if pactl load-module module-null-sink sink_name=virtual_mic_sink sink_properties=device.description="Virtual_Microphone_Sink"; then
    bashio::log.info "Virtual sink created successfully"
else
    bashio::log.error "Failed to create virtual sink"
    exit 1
fi

# Create virtual source from the sink monitor
bashio::log.info "Creating virtual source..."
if pactl load-module module-virtual-source source_name=virtual_mic source_properties=device.description="${VIRTUAL_MIC_NAME}" master=virtual_mic_sink.monitor; then
    bashio::log.info "Virtual source created successfully"
else
    bashio::log.error "Failed to create virtual source"
    exit 1
fi

# Wait a moment for devices to be ready
sleep 2

# Verify devices were created
if pactl list sinks short | grep -q virtual_mic_sink && pactl list sources short | grep -q virtual_mic; then
    bashio::log.info "Virtual microphone devices created successfully"
    bashio::log.info "Virtual sink: virtual_mic_sink"
    bashio::log.info "Virtual source: virtual_mic"
else
    bashio::log.error "Virtual devices not found after creation"
    bashio::log.info "Available sinks:"
    pactl list sinks short || true
    bashio::log.info "Available sources:"
    pactl list sources short || true
    exit 1
fi

# Get monitor_to_speakers setting from config
MONITOR_TO_SPEAKERS="${MONITOR_TO_SPEAKERS:-false}"

# Create loopback to default speakers if monitoring is enabled
if [ "${MONITOR_TO_SPEAKERS}" = "true" ]; then
    bashio::log.info "Monitor to speakers enabled - creating loopback to default speakers..."
    
    # Get default sink (speakers)
    DEFAULT_SINK=$(pactl info | grep "Default Sink:" | cut -d' ' -f3)
    if [ -n "${DEFAULT_SINK}" ]; then
        bashio::log.info "Default sink: ${DEFAULT_SINK}"
        
        # Create loopback from virtual_mic_sink to default speakers
        if pactl load-module module-loopback source=virtual_mic_sink.monitor sink="${DEFAULT_SINK}" latency_msec=10; then
            bashio::log.info "Loopback created: virtual_mic_sink.monitor -> ${DEFAULT_SINK}"
        else
            bashio::log.warning "Failed to create loopback to speakers"
        fi
    else
        bashio::log.warning "Could not detect default sink for speaker monitoring"
    fi
else
    bashio::log.info "Monitor to speakers disabled - no loopback created"
fi

bashio::log.info "Virtual microphone setup completed"