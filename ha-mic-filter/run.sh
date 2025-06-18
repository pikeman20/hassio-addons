#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Add-on: Real-time Microphone Filter
# Main execution script
# ==============================================================================

# Wait for services to be ready
s6-svwait -u /var/run/s6/services/pulseaudio

# Start the main service
bashio::log.info "Starting Real-time Microphone Filter..."
exec python3 /app/ha_mic_filter_service.py