#!/bin/bash
# Debug script for PulseAudio connection issues

echo "=== PulseAudio Debug Information ==="
echo

echo "1. Environment variables:"
echo "PULSE_SERVER: ${PULSE_SERVER:-not set}"
echo "XDG_RUNTIME_DIR: ${XDG_RUNTIME_DIR:-not set}"
echo

echo "2. Checking socket locations:"
echo "Checking Home Assistant audio socket /run/audio/:"
ls -la /run/audio/ 2>/dev/null || echo "Directory not found"
echo

echo "Checking /var/run/pulse/:"
ls -la /var/run/pulse/ 2>/dev/null || echo "Directory not found"
echo

echo "Checking /run/pulse/:"
ls -la /run/pulse/ 2>/dev/null || echo "Directory not found"
echo

echo "Checking /tmp/:"
ls -la /tmp/ | grep pulse || echo "No pulse-related files in /tmp"
echo

echo "3. Checking for PulseAudio processes:"
ps aux | grep pulse || echo "No PulseAudio processes found"
echo

echo "4. Testing pactl without PULSE_SERVER:"
unset PULSE_SERVER
echo "Testing pactl info..."
pactl info 2>&1 | head -5 || echo "Failed to connect"
echo

echo "5. Testing with different socket paths:"
# Test Home Assistant socket first
for socket in "/run/audio/pulse.sock" "/var/run/pulse/native" "/run/pulse/native" "/tmp/pulse-socket"; do
    if [ -S "$socket" ]; then
        echo "Testing socket: $socket"
        PULSE_SERVER="unix:$socket" pactl info 2>&1 | head -3 || echo "Failed"
    else
        echo "Socket not found: $socket"
    fi
done
echo

echo "6. Home Assistant add-on specific checks:"
echo "Checking if we're in HA add-on environment:"
if [ -f "/data/options.json" ]; then
    echo "✓ Found HA add-on options file"
    echo "audio option from config:"
    cat /data/options.json | grep -i audio || echo "No audio config found"
else
    echo "✗ Not in HA add-on environment"
fi
echo

echo "7. Container audio setup:"
echo "Checking /dev/snd:"
ls -la /dev/snd/ 2>/dev/null || echo "No /dev/snd found"
echo

echo "Checking audio groups:"
groups || echo "Cannot get groups"
echo

echo "=== End Debug Information ==="