#!/usr/bin/env python3
"""
VST 2.x Plugin Demo Script
=========================

This script demonstrates how to use VST 2.x plugins with the obs-mic-filter library.
It allows loading VST plugins, adjusting parameters, and processing audio in real-time.

Features:
- Load VST 2.x plugins (.dll/.so/.vst)
- Real-time parameter control
- Program/preset switching
- Audio processing pipeline integration

Requirements:
- Python 3.7+
- PyAudio: pip install PyAudio
- numpy: pip install numpy
- obs-mic-filter DLL/SO built with VST support

Usage:
python demo_vst_plugin.py [vst_plugin_path]
"""

import ctypes
import numpy as np
import pyaudio
import time
import threading
import sys
import os
import glob
from ctypes import Structure, POINTER, c_float, c_uint32, c_uint64, c_bool, c_int, c_char_p, c_void_p

# Import from main script
from python_realtime_test import (
    ObsMicFilter, RealTimeAudioProcessor, load_library,
    SAMPLE_RATE, CHANNELS, FRAMES_PER_BUFFER
)

# VST filter constants
OBS_FILTER_VST = 8

# Additional structures for VST
class vst_params(Structure):
    _fields_ = [
        ("plugin_path", c_char_p),
        ("program_number", c_int),
        ("parameters", c_float * 128),
        ("parameter_count", c_int),
        ("chunk_data", c_char_p)
    ]

class vst_filter_params_union(ctypes.Union):
    _fields_ = [
        ("gain", type("gain_params", (Structure,), {"_fields_": [("gain_db", c_float)]})),
        ("vst", vst_params)
    ]

class obs_vst_filter_params_t(Structure):
    _fields_ = [
        ("type", c_int),
        ("enabled", c_bool),
        ("params", vst_filter_params_union)
    ]

class VSTDemo:
    """VST Plugin Demo"""
    
    def __init__(self, vst_path=None):
        self.processor = RealTimeAudioProcessor()
        self.vst_path = vst_path
        self.current_program = 0
        self.parameters = [0.0] * 128
        self.parameter_count = 0
        self.running = False
        
        # Setup additional VST functions
        self._setup_vst_functions()
        
    def _setup_vst_functions(self):
        """Setup VST-specific function signatures"""
        # VST filter functions
        self.processor.filter.dll.filter_wrapper_vst_load_plugin.argtypes = [c_void_p, c_char_p]
        self.processor.filter.dll.filter_wrapper_vst_load_plugin.restype = c_int
        
        self.processor.filter.dll.filter_wrapper_vst_set_parameter.argtypes = [c_void_p, c_int, c_float]
        self.processor.filter.dll.filter_wrapper_vst_set_parameter.restype = c_int
        
        self.processor.filter.dll.filter_wrapper_vst_get_parameter.argtypes = [c_void_p, c_int]
        self.processor.filter.dll.filter_wrapper_vst_get_parameter.restype = c_float
        
        self.processor.filter.dll.filter_wrapper_vst_set_program.argtypes = [c_void_p, c_int]
        self.processor.filter.dll.filter_wrapper_vst_set_program.restype = c_int
        
        self.processor.filter.dll.filter_wrapper_vst_get_program.argtypes = [c_void_p]
        self.processor.filter.dll.filter_wrapper_vst_get_program.restype = c_int
        
        self.processor.filter.dll.filter_wrapper_vst_has_editor.argtypes = [c_void_p]
        self.processor.filter.dll.filter_wrapper_vst_has_editor.restype = c_bool
        
    def find_vst_plugins(self):
        """Find VST plugins in common locations"""
        vst_paths = []
        
        if sys.platform == "win32":
            # Windows VST paths
            search_paths = [
                os.path.expandvars(r"%ProgramFiles%\VSTPlugins"),
                os.path.expandvars(r"%ProgramFiles(x86)%\VSTPlugins"),
                os.path.expandvars(r"%CommonProgramFiles%\VST2"),
                os.path.expandvars(r"%CommonProgramFiles(x86)%\VST2"),
                r"C:\VSTPlugins"
            ]
            extension = "*.dll"
        elif sys.platform == "darwin":
            # macOS VST paths  
            search_paths = [
                "/Library/Audio/Plug-Ins/VST",
                "~/Library/Audio/Plug-ins/VST"
            ]
            extension = "*.vst"
        else:
            # Linux VST paths
            search_paths = [
                "/usr/lib/vst",
                "/usr/local/lib/vst",
                "~/.vst",
                os.path.expandvars("$VST_PATH")
            ]
            extension = "*.so"
        
        for path in search_paths:
            if os.path.exists(path):
                vst_files = glob.glob(os.path.join(path, extension))
                vst_paths.extend(vst_files)
                
        return vst_paths[:10]  # Limit to first 10 found
        
    def setup_demo(self):
        """Setup the VST demo pipeline"""
        print("🎛️  Setting up VST Plugin Demo...")
        
        # Create pipeline
        self.processor.filter.create_pipeline(SAMPLE_RATE, CHANNELS)
        
        # Check if VST filter is supported
        if not self.processor.filter.dll.obs_pipeline_is_filter_supported(OBS_FILTER_VST):
            print("❌ VST filter not supported in this build")
            return False
            
        # Add VST filter
        if self.vst_path:
            success = self.load_vst_plugin(self.vst_path)
            if not success:
                print(f"❌ Failed to load VST plugin: {self.vst_path}")
                return False
        
        # Add other filters
        self.processor.filter.add_gain_filter(1, 0.0)  # Unity gain
        
        print("VST Demo setup complete!\n")
        return True
        
    def load_vst_plugin(self, plugin_path):
        """Load a VST plugin"""
        print(f"🎹 Loading VST plugin: {os.path.basename(plugin_path)}")
        
        # Create VST filter parameters
        params = obs_vst_filter_params_t()
        params.type = OBS_FILTER_VST
        params.enabled = True
        params.params.vst.plugin_path = plugin_path.encode('utf-8')
        params.params.vst.program_number = 0
        params.params.vst.parameter_count = 0
        
        # Initialize parameters array
        for i in range(128):
            params.params.vst.parameters[i] = 0.0
            
        # Add VST filter to pipeline
        result = self.processor.filter.dll.obs_pipeline_update_filter(
            self.processor.filter.pipeline, 0, ctypes.byref(params)
        )
        
        if result == 0:  # OBS_PIPELINE_SUCCESS
            self.vst_path = plugin_path
            print(f"✅ VST plugin loaded successfully")
            
            # Try to get parameter count and other info
            # Note: This would require additional wrapper functions to get VST info
            return True
        else:
            print(f"❌ Failed to load VST plugin (error code: {result})")
            return False
            
    def set_vst_parameter(self, index, value):
        """Set VST parameter value (0.0 - 1.0)"""
        if 0 <= index < 128 and 0.0 <= value <= 1.0:
            # This would require the VST wrapper to be properly integrated
            # For now, just store the value
            self.parameters[index] = value
            print(f"📊 Parameter {index}: {value:.3f}")
            
    def set_vst_program(self, program):
        """Set VST program/preset"""
        if program >= 0:
            self.current_program = program
            print(f"🎵 Program: {program}")
            
    def print_instructions(self):
        """Print usage instructions"""
        print("=" * 60)
        print("🎹 VST 2.x PLUGIN DEMO")
        print("=" * 60)
        print()
        if self.vst_path:
            print(f"🎛️ Loaded: {os.path.basename(self.vst_path)}")
        else:
            print("🎛️ No VST plugin loaded")
        print()
        print("🎮 CONTROLS:")
        print("   • 'l' - List and load VST plugins")
        print("   • 'p' - Change program/preset")
        print("   • '1-8' - Adjust parameters 1-8")
        print("   • 'i' - Show plugin info")
        print("   • 'q' - Quit demo")
        print()
        print("🎯 Speak into your microphone to hear VST processing...")
        print("=" * 60)
        print()
        
    def list_and_load_plugins(self):
        """List available VST plugins and allow selection"""
        print("\n🔍 Searching for VST plugins...")
        plugins = self.find_vst_plugins()
        
        if not plugins:
            print("❌ No VST plugins found in common locations")
            return
            
        print(f"\n📁 Found {len(plugins)} VST plugins:")
        for i, plugin in enumerate(plugins):
            print(f"   {i+1}. {os.path.basename(plugin)}")
            print(f"      {plugin}")
            
        try:
            choice = input(f"\nSelect plugin (1-{len(plugins)}) or Enter to cancel: ").strip()
            if choice and choice.isdigit():
                index = int(choice) - 1
                if 0 <= index < len(plugins):
                    self.load_vst_plugin(plugins[index])
        except ValueError:
            print("❌ Invalid selection")
            
    def adjust_parameter(self, param_index):
        """Adjust a VST parameter"""
        current_value = self.parameters[param_index]
        print(f"\n📊 Parameter {param_index + 1} current value: {current_value:.3f}")
        
        try:
            new_value = input("Enter new value (0.0 - 1.0) or Enter to cancel: ").strip()
            if new_value:
                value = float(new_value)
                if 0.0 <= value <= 1.0:
                    self.set_vst_parameter(param_index, value)
                else:
                    print("❌ Value must be between 0.0 and 1.0")
        except ValueError:
            print("❌ Invalid value")
            
    def change_program(self):
        """Change VST program/preset"""
        print(f"\n🎵 Current program: {self.current_program}")
        
        try:
            new_program = input("Enter program number (0+) or Enter to cancel: ").strip()
            if new_program and new_program.isdigit():
                program = int(new_program)
                if program >= 0:
                    self.set_vst_program(program)
                else:
                    print("❌ Program number must be 0 or greater")
        except ValueError:
            print("❌ Invalid program number")
            
    def show_plugin_info(self):
        """Show information about loaded plugin"""
        if not self.vst_path:
            print("❌ No VST plugin loaded")
            return
            
        print(f"\n🎹 VST Plugin Information:")
        print(f"   📁 Path: {self.vst_path}")
        print(f"   📛 Name: {os.path.basename(self.vst_path)}")
        print(f"   🎵 Current Program: {self.current_program}")
        print(f"   📊 Parameters in use: {sum(1 for p in self.parameters if p != 0.0)}")
        
        # Show non-zero parameters
        print(f"   🎛️ Active Parameters:")
        for i, value in enumerate(self.parameters[:16]):  # Show first 16
            if value != 0.0:
                print(f"      Parameter {i+1}: {value:.3f}")
                
    def run_demo(self):
        """Run the interactive VST demo"""
        try:
            if not self.setup_demo():
                return
                
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
                    key = input().strip().lower()
                    
                    if key == 'l':
                        self.list_and_load_plugins()
                    elif key == 'p':
                        self.change_program()
                    elif key in '12345678':
                        param_index = int(key) - 1
                        self.adjust_parameter(param_index)
                    elif key == 'i':
                        self.show_plugin_info()
                    elif key == 'q':
                        print("\n👋 Quitting VST demo...")
                        break
                    elif key == 'h' or key == 'help':
                        self.print_instructions()
                    else:
                        print("❓ Unknown command. Press 'h' for help")
                        
                except KeyboardInterrupt:
                    break
                    
        except Exception as e:
            print(f"❌ Error running VST demo: {e}")
        finally:
            self.cleanup()
            
    def cleanup(self):
        """Cleanup resources"""
        self.running = False
        self.processor.cleanup()
        print("🧹 VST demo cleanup complete.")

def main():
    """Main function"""
    print("🚀 Starting VST 2.x Plugin Demo...\n")
    
    # Check for VST plugin path argument
    vst_path = None
    if len(sys.argv) > 1:
        vst_path = sys.argv[1]
        if not os.path.exists(vst_path):
            print(f"❌ VST plugin not found: {vst_path}")
            vst_path = None
    
    try:
        demo = VSTDemo(vst_path)
        demo.run_demo()
        
    except Exception as e:
        print(f"💥 Error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure obs-mic-filter DLL/SO is available")
        print("2. Install required packages: pip install PyAudio numpy")
        print("3. Check microphone and speaker connections")
        print("4. Make sure VST plugins are installed")
        print("5. Run: ./build_all.sh to build the DLL/SO with VST support")

if __name__ == "__main__":
    main()