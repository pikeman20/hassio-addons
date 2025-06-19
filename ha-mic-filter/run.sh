#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Add-on: Real-time Microphone Filter
# Main execution script
# ==============================================================================

# Set up Home Assistant PulseAudio environment
export PULSE_SERVER=unix:/run/audio/pulse.sock

# Wait for PulseAudio to be ready
bashio::log.info "Waiting for Home Assistant PulseAudio to be ready..."
sleep 5

# Check if PulseAudio is accessible via the Home Assistant socket
bashio::log.info "Checking Home Assistant PulseAudio connectivity..."
if pactl info >/dev/null 2>&1; then
    bashio::log.info "Home Assistant PulseAudio is accessible"
else
    bashio::log.warning "PulseAudio not accessible via Home Assistant socket, but continuing anyway"
    bashio::log.info "Service will attempt to use fallback connection methods"
fi

# Start the main service
bashio::log.info "Starting Real-time Microphone Filter..."

# Set Python path
export PYTHONPATH="/app:${PYTHONPATH:-}"

exec python3 /app/ha_mic_filter_service.py