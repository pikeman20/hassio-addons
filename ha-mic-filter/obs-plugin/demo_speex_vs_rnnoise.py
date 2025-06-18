#!/usr/bin/env python3
"""
Demo script to compare Speex vs RNNoise noise suppression methods
================================================================

This script demonstrates the difference between Speex and RNNoise methods
for noise suppression, allowing you to switch between them during runtime.

Press:
- 's' to switch to Speex (lower CPU usage)
- 'r' to switch to RNNoise (higher quality, more CPU)
- 'q' to quit

Requirements:
- Python 3.7+
- PyAudio: pip install PyAudio
- numpy: pip install numpy
- keyboard: pip install keyboard
- obs-mic-filter DLL/SO built with both Speex and RNNoise support
"""

import ctypes
import numpy as np
import pyaudio
import time
import threading
import sys
import os
from ctypes import Structure, POINTER, c_float, c_uint32, c_uint64, c_bool, c_int, c_char_p, c_void_p

# Import from main script
from python_realtime_test import (
    ObsMicFilter, RealTimeAudioProcessor, load_library,
    OBS_NOISE_SUPPRESS_SPEEX, OBS_NOISE_SUPPRESS_RNNOISE,
    SAMPLE_RATE, CHANNELS, FRAMES_PER_BUFFER
)

class InteractiveNoiseDemo:
    """Interactive demo comparing Speex vs RNNoise"""
    
    def __init__(self):
        self.processor = RealTimeAudioProcessor()
        self.current_method = OBS_NOISE_SUPPRESS_SPEEX
        self.running = False
        
    def setup_demo(self):
        """Setup the demo pipeline"""
        print("🎛️  Setting up Speex vs RNNoise Demo...")
        
        # Create pipeline
        self.processor.filter.create_pipeline(SAMPLE_RATE, CHANNELS)
        
        # Check filter support
        self.processor.filter.check_filter_support()
        
        # Add initial filters
        print("Adding filters to pipeline:")
        
        # Start with Speex noise suppression
        self.processor.filter.add_noise_suppress_filter(0, OBS_NOISE_SUPPRESS_SPEEX, -30)
        
        # Add EQ and gain
        self.processor.filter.add_equalizer_filter(1, low_db=1.0, mid_db=0.0, high_db=1.0)
        self.processor.filter.add_gain_filter(2, 2.0)
        
        print("Demo setup complete!\n")
        
    def switch_method(self, method):
        """Switch noise suppression method"""
        if method == self.current_method:
            return
            
        method_name = "RNNoise" if method == OBS_NOISE_SUPPRESS_RNNOISE else "Speex"
        cpu_usage = "High CPU" if method == OBS_NOISE_SUPPRESS_RNNOISE else "Low CPU"
        quality = "Highest Quality" if method == OBS_NOISE_SUPPRESS_RNNOISE else "Good Quality"
        
        print(f"\n🔄 Switching to {method_name} ({cpu_usage}, {quality})")
        
        success = self.processor.filter.switch_noise_method(0, method)
        if success:
            self.current_method = method
            print(f"✅ Successfully switched to {method_name}")
        else:
            print(f"❌ Failed to switch to {method_name}")
    
    def print_instructions(self):
        """Print usage instructions"""
        print("=" * 60)
        print("🎤 SPEEX vs RNNOISE NOISE SUPPRESSION DEMO")
        print("=" * 60)
        print()
        print("This demo lets you compare two noise suppression methods:")
        print()
        print("📊 SPEEX DSP:")
        print("   • Lower CPU usage (~5-10%)")
        print("   • Good noise reduction")
        print("   • Works on all sample rates")
        print("   • Traditional DSP algorithm")
        print()
        print("🧠 RNNOISE (AI):")
        print("   • Higher CPU usage (~15-25%)")
        print("   • Superior noise reduction")
        print("   • Requires 48kHz sample rate")
        print("   • Deep learning based")
        print()
        print("🎮 CONTROLS:")
        print("   • Press 's' - Switch to Speex")
        print("   • Press 'r' - Switch to RNNoise")
        print("   • Press 'q' - Quit demo")
        print()
        current_name = "RNNoise" if self.current_method == OBS_NOISE_SUPPRESS_RNNOISE else "Speex"
        print(f"🔊 Current method: {current_name}")
        print("=" * 60)
        print()
        print("🎯 Start speaking into your microphone to test noise suppression...")
        print("Try making background noise, typing, etc. to compare methods")
        print()
        
    def run_demo(self):
        """Run the interactive demo"""
        try:
            self.setup_demo()
            self.print_instructions()
            
            # Start audio processing in background thread
            audio_thread = threading.Thread(target=self.processor.start_streaming, daemon=True)
            audio_thread.start()
            
            # Wait a moment for audio to start
            time.sleep(1)
            self.running = True
            
            # Main input loop
            while self.running:
                try:
                    # Get user input
                    key = input().strip().lower()
                    
                    if key == 's':
                        self.switch_method(OBS_NOISE_SUPPRESS_SPEEX)
                    elif key == 'r':
                        self.switch_method(OBS_NOISE_SUPPRESS_RNNOISE)
                    elif key == 'q':
                        print("\n👋 Quitting demo...")
                        break
                    elif key == 'h' or key == 'help':
                        self.print_instructions()
                    else:
                        print("❓ Unknown command. Press 's' (Speex), 'r' (RNNoise), or 'q' (quit)")
                        
                except KeyboardInterrupt:
                    break
                    
        except Exception as e:
            print(f"❌ Error running demo: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup resources"""
        self.running = False
        self.processor.cleanup()
        print("🧹 Demo cleanup complete.")

def main():
    """Main function"""
    print("🚀 Starting Speex vs RNNoise Demo...\n")
    
    try:
        demo = InteractiveNoiseDemo()
        demo.run_demo()
        
    except Exception as e:
        print(f"💥 Error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure obs-mic-filter DLL/SO is available")
        print("2. Install required packages: pip install PyAudio numpy")
        print("3. Check microphone and speaker connections")
        print("4. Run: ./build_all.sh to build the DLL/SO")

if __name__ == "__main__":
    main()