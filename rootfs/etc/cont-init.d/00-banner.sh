#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Community Add-on: Real-time Microphone Filter
# Displays a simple banner on startup
# ==============================================================================

if bashio::supervisor.ping; then
    bashio::log.blue \
        '-----------------------------------------------------------'
    bashio::log.blue " Add-on: $(bashio::addon.name)"
    bashio::log.blue " $(bashio::addon.description)"
    bashio::log.blue \
        '-----------------------------------------------------------'
    bashio::log.blue " Add-on version: $(bashio::addon.version)"
    bashio::log.blue " Home Assistant version: $(bashio::core.version)"
    bashio::log.blue " Supervisor version: $(bashio::supervisor.version)"
    bashio::log.blue \
        '-----------------------------------------------------------'
    bashio::log.blue " Please, share the above information when looking for help"
    bashio::log.blue " or support in, e.g., GitHub, forums or the Discord chat."
    bashio::log.blue \
        '-----------------------------------------------------------'
fi