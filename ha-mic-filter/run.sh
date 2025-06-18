#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Add-on: Real-time Microphone Filter
# Main execution script
# ==============================================================================

# Wait for PulseAudio to be ready (but not wait for it to stop)
bashio::log.info "Waiting for PulseAudio to be ready..."
sleep 5

# Check if PulseAudio is running
if ! pgrep pulseaudio > /dev/null; then
    bashio::log.error "PulseAudio is not running"
    exit 1
fi

# Start the main service
bashio::log.info "Starting Real-time Microphone Filter..."
exec python3 /app/ha_mic_filter_service.py