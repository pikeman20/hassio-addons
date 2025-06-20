#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Community Add-on: Real-time Microphone Filter
# Displays a simple banner on startup
# ==============================================================================

# Try to get supervisor info, but don't fail if API is not accessible
bashio::log.blue \
    '-----------------------------------------------------------'
bashio::log.blue " Add-on: Real-time Microphone Filter"
bashio::log.blue " Real-time microphone filtering for Home Assistant Assist with virtual audio device support"
bashio::log.blue \
    '-----------------------------------------------------------'
bashio::log.blue " Add-on version: 1.0.4"

# Try to get HA/Supervisor versions, but continue if they fail
if bashio::supervisor.ping 2>/dev/null; then
    HA_VERSION=$(bashio::core.version 2>/dev/null || echo "Unknown")
    SUPERVISOR_VERSION=$(bashio::supervisor.version 2>/dev/null || echo "Unknown")
    bashio::log.blue " Home Assistant version: ${HA_VERSION}"
    bashio::log.blue " Supervisor version: ${SUPERVISOR_VERSION}"
else
    bashio::log.blue " Home Assistant version: (API not accessible)"
    bashio::log.blue " Supervisor version: (API not accessible)"
fi

bashio::log.blue \
    '-----------------------------------------------------------'
bashio::log.blue " Please, share the above information when looking for help"
bashio::log.blue " or support in, e.g., GitHub, forums or the Discord chat."
bashio::log.blue \
    '-----------------------------------------------------------'