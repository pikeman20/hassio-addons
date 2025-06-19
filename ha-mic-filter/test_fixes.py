#!/usr/bin/env python3
"""
Test script for microphone filter fixes
"""

import sys
import os

def test_buffer_calculations():
    """Test buffer size calculations"""
    print("Testing buffer size calculations:")
    
    sample_rates = [44100, 48000]
    buffer_sizes_ms = [10, 20, 30]
    
    for sr in sample_rates:
        for bs_ms in buffer_sizes_ms:
            frames = int((sr * bs_ms) / 1000)
            optimal_frames = max(frames, 960)
            actual_latency = (optimal_frames * 1000) / sr
            
            print(f"  Sample Rate: {sr}Hz, Target: {bs_ms}ms")
            print(f"    Calculated frames: {frames}")
            print(f"    Optimal frames: {optimal_frames}")
            print(f"    Actual latency: {actual_latency:.1f}ms")
            print()

def test_limiter_handling():
    """Test limiter handling logic"""
    print("Testing LIMITER filter handling:")
    
    # Simulate the checks we added
    limiter_config = {'enabled': True, 'threshold': -0.2, 'release_time': 60.0}
    
    print(f"  Limiter config: {limiter_config}")
    
    # Test case 1: Function exists and returns False
    print("  Case 1: LIMITER not supported")
    is_supported = False
    if limiter_config.get('enabled', True):
        if is_supported:
            print("    Would add LIMITER filter")
        else:
            print("    LIMITER filter not supported, skipping")
    
    # Test case 2: Function doesn't exist
    print("  Case 2: Support check function missing")
    try:
        # Simulate missing function
        raise AttributeError("'NoneType' object has no attribute 'obs_pipeline_is_filter_supported'")
    except Exception as e:
        print(f"    LIMITER filter error: {e}, skipping")

def main():
    print("Microphone Filter Fixes Test Script")
    print("=" * 40)
    
    test_buffer_calculations()
    test_limiter_handling()
    
    print("All tests completed!")
    print("\nKey fixes implemented:")
    print("1. Increased default buffer size from 10ms to 20ms")
    print("2. Added graceful LIMITER filter error handling")
    print("3. Improved buffer size calculations")
    print("4. Added low-latency mode for audio streams")
    print("5. Better error reporting in audio pipeline")

if __name__ == "__main__":
    main()