#!/usr/bin/env python3
"""
PulseAudio diagnostics script for Home Assistant Microphone Filter
"""

import subprocess
import sys
import logging

def run_command(cmd):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def diagnose_pulseaudio():
    """Diagnose PulseAudio configuration and devices"""
    print("=== PulseAudio Diagnostics ===\n")
    
    # Check if PulseAudio is running
    print("1. Checking PulseAudio process...")
    code, stdout, stderr = run_command("pgrep -f pulseaudio")
    if code == 0:
        print(f"✓ PulseAudio is running (PIDs: {stdout.strip()})")
    else:
        print("✗ PulseAudio is not running")
        return
    
    # Check PulseAudio server info
    print("\n2. PulseAudio server info...")
    code, stdout, stderr = run_command("pactl info")
    if code == 0:
        print("✓ PulseAudio server is responding")
        for line in stdout.split('\n'):
            if 'Server Version' in line or 'Default Sink' in line or 'Default Source' in line:
                print(f"   {line}")
    else:
        print(f"✗ Failed to get server info: {stderr}")
    
    # List sinks
    print("\n3. Available sinks (output devices)...")
    code, stdout, stderr = run_command("pactl list sinks short")
    if code == 0:
        if stdout.strip():
            print("✓ Sinks found:")
            for line in stdout.strip().split('\n'):
                print(f"   {line}")
        else:
            print("✗ No sinks found")
    else:
        print(f"✗ Failed to list sinks: {stderr}")
    
    # List sources
    print("\n4. Available sources (input devices)...")
    code, stdout, stderr = run_command("pactl list sources short")
    if code == 0:
        if stdout.strip():
            print("✓ Sources found:")
            for line in stdout.strip().split('\n'):
                print(f"   {line}")
        else:
            print("✗ No sources found")
    else:
        print(f"✗ Failed to list sources: {stderr}")
    
    # Check for virtual devices
    print("\n5. Checking for virtual devices...")
    code, stdout, stderr = run_command("pactl list sinks short | grep virtual_mic_sink")
    if code == 0:
        print("✓ Virtual sink found")
    else:
        print("✗ Virtual sink not found")
    
    code, stdout, stderr = run_command("pactl list sources short | grep virtual_mic")
    if code == 0:
        print("✓ Virtual source found")
    else:
        print("✗ Virtual source not found")
    
    # Check socket
    print("\n6. Checking external socket...")
    code, stdout, stderr = run_command("ls -la /tmp/pulse-external-socket")
    if code == 0:
        print("✓ External socket exists")
    else:
        print("✗ External socket not found")
    
    # Test Python PulseAudio connection
    print("\n7. Testing Python PulseAudio connection...")
    try:
        import pulsectl
        with pulsectl.Pulse('test-connection') as pulse:
            server_info = pulse.server_info()
            print(f"✓ Python connection successful (version: {server_info.server_version})")
            
            sources = pulse.source_list()
            sinks = pulse.sink_list()
            print(f"   Found {len(sources)} sources and {len(sinks)} sinks")
    except Exception as e:
        print(f"✗ Python connection failed: {e}")
    
    print("\n=== Diagnostics Complete ===")

if __name__ == "__main__":
    diagnose_pulseaudio()