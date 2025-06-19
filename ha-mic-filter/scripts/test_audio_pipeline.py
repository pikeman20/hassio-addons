#!/usr/bin/env python3
"""
Test script for audio pipeline functionality
"""

import sys
import os
import logging

# Add the app directory to Python path
sys.path.insert(0, '/app')

from audio_pipeline_manager import AudioPipelineManager
from pulse_audio_manager import PulseAudioManager

def test_audio_pipeline():
    """Test the audio pipeline initialization"""
    print("=== Audio Pipeline Test ===\n")
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Test audio pipeline manager
    print("1. Testing Audio Pipeline Manager...")
    try:
        apm = AudioPipelineManager()
        if apm.library:
            print("✓ Audio pipeline library loaded successfully")
            
            # Test pipeline creation
            if apm.create_pipeline(sample_rate=48000, channels=1, buffer_size_ms=10):
                print("✓ Audio pipeline created successfully")
            else:
                print("✗ Failed to create audio pipeline")
                
        else:
            print("✗ Failed to load audio pipeline library")
    except Exception as e:
        print(f"✗ Audio pipeline error: {e}")
    
    # Test PulseAudio manager
    print("\n2. Testing PulseAudio Manager...")
    try:
        pam = PulseAudioManager()
        if pam.pulse:
            print("✓ PulseAudio connection successful")
            
            devices = pam.get_devices()
            print(f"✓ Found {len(devices)} audio devices")
            
            for device in devices:
                print(f"   - {device.name}: {device.description}")
                
        else:
            print("✗ Failed to connect to PulseAudio")
    except Exception as e:
        print(f"✗ PulseAudio error: {e}")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    test_audio_pipeline()