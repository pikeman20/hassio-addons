#!/bin/bash
# Script to properly restart PulseAudio and clean up any stuck processes

echo "Cleaning up PulseAudio processes..."

# Kill any existing PulseAudio processes
pkill -f pulseaudio || true

# Remove socket files
rm -f /tmp/pulse-external-socket || true
rm -f /var/run/pulse/* || true

# Wait a moment
sleep 2

echo "PulseAudio cleanup completed"