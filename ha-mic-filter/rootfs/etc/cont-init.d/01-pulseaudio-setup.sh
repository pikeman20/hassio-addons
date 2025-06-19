#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Community Add-on: Real-time Microphone Filter
# Setup virtual microphone devices on existing PulseAudio
# ==============================================================================

bashio::log.info "Setting up virtual microphone devices..."

# Get virtual microphone name from Home Assistant config
VIRTUAL_MIC_NAME="${VIRTUAL_MIC_NAME:-HA_Filtered_Mic}"

# Wait for Home Assistant's PulseAudio to be available
sleep 2

# Function to check if PulseAudio is ready
check_pulseaudio() {
    pactl info >/dev/null 2>&1
}

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
    exit 1
fi

# Clean up any existing virtual devices
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
sleep 1

# Verify devices were created
if pactl list sinks short | grep -q virtual_mic_sink && pactl list sources short | grep -q virtual_mic; then
    bashio::log.info "Virtual microphone devices created successfully"
else
    bashio::log.error "Virtual devices not found after creation"
    exit 1
fi

bashio::log.info "Virtual microphone setup completed"