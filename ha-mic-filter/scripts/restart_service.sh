#!/bin/bash
# Script to restart the microphone filter service for debugging

echo "=== Restarting Microphone Filter Service ==="

echo "1. Stopping current service..."
s6-svc -d /var/run/s6/services/mic-filter

echo "2. Waiting 3 seconds..."
sleep 3

echo "3. Starting service..."
s6-svc -u /var/run/s6/services/mic-filter

echo "4. Service status:"
s6-svstat /var/run/s6/services/mic-filter

echo "=== Restart complete ==="
echo "You can check logs with: tail -f /var/log/mic-filter/current"