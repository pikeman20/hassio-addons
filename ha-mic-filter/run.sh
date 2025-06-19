#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Add-on: Real-time Microphone Filter
# Main execution script
# ==============================================================================

# Wait for PulseAudio to be ready (but not wait for it to stop)
bashio::log.info "Waiting for PulseAudio to be ready..."
sleep 5

# Check if PulseAudio is accessible (not if it's running as a process)
# In Home Assistant addons, PulseAudio is provided by the host system
bashio::log.info "Checking PulseAudio connectivity..."
if pactl info >/dev/null 2>&1; then
    bashio::log.info "PulseAudio is accessible"
else
    bashio::log.warning "PulseAudio not accessible via default connection, but continuing anyway"
    bashio::log.info "Service will attempt to use Home Assistant's audio system"
fi

# Start the main service
bashio::log.info "Starting Real-time Microphone Filter..."

# Set Python path
export PYTHONPATH="/app:${PYTHONPATH:-}"

exec python3 /app/ha_mic_filter_service.py