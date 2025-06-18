#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Community Add-on: Real-time Microphone Filter
# Setup basic D-Bus directory structure to prevent connection errors
# ==============================================================================

bashio::log.info "Setting up D-Bus directory structure..."

# Create D-Bus system bus socket directory
mkdir -p /run/dbus

# Create a basic D-Bus configuration to prevent connection errors
mkdir -p /etc/dbus-1/system.d

bashio::log.info "D-Bus directory structure created"