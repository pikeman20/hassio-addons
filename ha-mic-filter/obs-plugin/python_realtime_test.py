"""
Real-time Audio Processing Test with Audio Pipeline Manager
==========================================================

This script demonstrates real-time audio processing using the new AudioPipelineManager class.
It provides a simple interface to test the comprehensive audio pipeline functionality.

Requirements:
- PyAudio: pip install PyAudio
- numpy: pip install numpy
- obs-mic-filter.dll (built from this project)

Usage:
python python_realtime_test.py
"""

import numpy as np
import pyaudio
import time
import threading
import sys
import os

# Import the new AudioPipelineManager
from audio_pipeline_manager import AudioPipelineManager, FilterType

# Audio constants
SAMPLE_RATE = 48000
CHANNELS = 1
FRAMES_PER_BUFFER = 480
CHUNK_DURATION_MS = int(FRAMES_PER_BUFFER * 1000 / SAMPLE_RATE)


class RealTimeAudioProcessor:
    """Real-time audio processor using PyAudio and AudioPipelineManager"""
    
    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.pipeline_manager = AudioPipelineManager()
        self.stream_in = None
        self.stream_out = None
        self.running = False
        self.audio_queue = []
        self.queue_lock = threading.Lock()
        
    def list_audio_devices(self):
        """List available audio devices"""
        print("Available audio devices:")
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            print(f"  {i}: {info['name']} (inputs: {info['maxInputChannels']}, outputs: {info['maxOutputChannels']})")
        print()
    
    def setup_pipeline(self):
        """Setup the audio processing pipeline using AudioPipelineManager"""
        print("Setting up audio pipeline...")
        
        # Create pipeline
        success = self.pipeline_manager.create_pipeline(
            sample_rate=SAMPLE_RATE,
            channels=CHANNELS,
            buffer_size_ms=CHUNK_DURATION_MS
        )
        
        if not success:
            raise RuntimeError("Failed to create audio pipeline")
        
        # Check supported filters
        supported_filters = self.pipeline_manager.get_supported_filters()
        print("Supported filters:")
        for filter_type in supported_filters:
            print(f"  ✓ {filter_type.name}")
        print()
        
        # Create a professional voice processing chain
        print("Creating professional voice processing chain...")
        filter_ids = self.pipeline_manager.create_professional_voice_preset()
        
        if filter_ids:
            print(f"Successfully created {len(filter_ids)} filters")
        else:
            print("Warning: No filters were added - using basic setup")
            # Fallback to basic filters
            self._setup_basic_filters()
        
        # Print pipeline summary
        self.pipeline_manager.print_pipeline_summary()
        
        print("Pipeline setup complete!\n")
    
    def _setup_basic_filters(self):
        """Setup basic filters as fallback"""
        print("Setting up basic filters...")
        
        # Add basic noise suppression
        self.pipeline_manager.add_filter(
            FilterType.NOISE_SUPPRESS,
            method=1,  # RNNoise
            suppress_level=-30,
            intensity=0.5
        )
        
        # Add basic gain
        self.pipeline_manager.add_filter(
            FilterType.GAIN,
            gain_db=3.0
        )
        
        print("Basic filters added")
    
    def audio_callback_input(self, in_data, frame_count, time_info, status):
        """Audio input callback"""
        if status:
            print(f"Input stream status: {status}")
        
        try:
            # Convert audio data to numpy array
            audio_np = np.frombuffer(in_data, dtype=np.float32)
            
            # Process through the pipeline manager
            processed_audio = self.pipeline_manager.apply_filters(audio_np)
            
            # Add to output queue
            with self.queue_lock:
                self.audio_queue.append(processed_audio)
                # Keep queue size reasonable
                if len(self.audio_queue) > 10:
                    self.audio_queue.pop(0)
        
        except Exception as e:
            print(f"Error in input callback: {e}")
        
        return (None, pyaudio.paContinue)
    
    def audio_callback_output(self, in_data, frame_count, time_info, status):
        """Audio output callback"""
        if status:
            print(f"Output stream status: {status}")
        
        try:
            # Get processed audio from queue
            with self.queue_lock:
                if self.audio_queue:
                    audio_data = self.audio_queue.pop(0)
                else:
                    # Return silence if no data available
                    audio_data = np.zeros(frame_count, dtype=np.float32)
            
            # Ensure correct frame count
            if len(audio_data) != frame_count:
                if len(audio_data) < frame_count:
                    # Pad with zeros
                    audio_data = np.pad(audio_data, (0, frame_count - len(audio_data)))
                else:
                    # Truncate
                    audio_data = audio_data[:frame_count]
            
            return (audio_data.tobytes(), pyaudio.paContinue)
        
        except Exception as e:
            print(f"Error in output callback: {e}")
            # Return silence on error
            silence = np.zeros(frame_count, dtype=np.float32)
            return (silence.tobytes(), pyaudio.paContinue)
    
    def start_streaming(self, input_device=None, output_device=None):
        """Start real-time audio streaming"""
        print("Starting real-time audio processing...")
        print("Press Ctrl+C to stop\n")
        
        try:
            # Open input stream
            self.stream_in = self.audio.open(
                format=pyaudio.paFloat32,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=input_device,
                frames_per_buffer=FRAMES_PER_BUFFER,
                stream_callback=self.audio_callback_input
            )
            
            # Open output stream
            self.stream_out = self.audio.open(
                format=pyaudio.paFloat32,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                output=True,
                output_device_index=output_device,
                frames_per_buffer=FRAMES_PER_BUFFER,
                stream_callback=self.audio_callback_output
            )
            
            # Start streams
            self.stream_in.start_stream()
            self.stream_out.start_stream()
            self.running = True
            
            print("🎤 Audio processing started!")
            print("Pipeline: Microphone → Professional Voice Chain → Speakers")
            print("Speak into your microphone and listen to the processed audio...\n")
            
            # Interactive commands
            self._interactive_mode()
                
        except KeyboardInterrupt:
            print("\n🛑 Stopping audio processing...")
        except Exception as e:
            print(f"Error during streaming: {e}")
        finally:
            self.stop_streaming()
    
    def _interactive_mode(self):
        """Interactive mode for real-time filter adjustments"""
        print("Interactive Commands:")
        print("  's' - Save current pipeline configuration")
        print("  'l' - Load pipeline configuration")
        print("  'i' - Show pipeline info")
        print("  'q' - Quit")
        print("  Enter - Continue processing")
        print()
        
        while self.running and self.stream_in.is_active() and self.stream_out.is_active():
            try:
                command = input("Command (or Enter to continue): ").strip().lower()
                
                if command == 'q':
                    print("Quitting...")
                    break
                elif command == 's':
                    filename = input("Enter filename to save (default: pipeline_config.json): ").strip()
                    if not filename:
                        filename = "pipeline_config.json"
                    self.pipeline_manager.save_pipeline_config(filename)
                elif command == 'l':
                    filename = input("Enter filename to load (default: pipeline_config.json): ").strip()
                    if not filename:
                        filename = "pipeline_config.json"
                    if os.path.exists(filename):
                        self.pipeline_manager.load_pipeline_config(filename)
                        print("Pipeline configuration loaded!")
                    else:
                        print(f"File not found: {filename}")
                elif command == 'i':
                    self.pipeline_manager.print_pipeline_summary()
                    filter_info = self.pipeline_manager.get_filter_info()
                    if filter_info:
                        print("Detailed filter information:")
                        for filter_id, info in filter_info.items():
                            print(f"  Filter {filter_id}: {info['type']} - {info['parameters']}")
                        print()
                elif command == '':
                    # Just continue
                    time.sleep(0.1)
                else:
                    print("Unknown command. Use 's', 'l', 'i', 'q', or Enter.")
                    
            except EOFError:
                break
            except Exception as e:
                print(f"Error in interactive mode: {e}")
                time.sleep(0.1)
    
    def stop_streaming(self):
        """Stop audio streaming"""
        self.running = False
        
        if self.stream_in:
            try:
                self.stream_in.stop_stream()
                self.stream_in.close()
            except Exception as e:
                print(f"Error stopping input stream: {e}")
            
        if self.stream_out:
            try:
                self.stream_out.stop_stream()
                self.stream_out.close()
            except Exception as e:
                print(f"Error stopping output stream: {e}")
            
        print("Audio streams stopped.")
    
    def cleanup(self):
        """Cleanup resources"""
        self.stop_streaming()
        self.pipeline_manager.cleanup()
        self.audio.terminate()
        print("Cleanup complete.")


def demo_pipeline_management():
    """Demonstrate pipeline management features without audio streaming"""
    print("=== Audio Pipeline Manager Demo (No Audio) ===\n")
    
    try:
        # Create pipeline manager
        manager = AudioPipelineManager()
        
        # Create pipeline
        print("Creating pipeline...")
        success = manager.create_pipeline(sample_rate=48000, channels=1)
        
        if not success:
            print("Failed to create pipeline")
            return
        
        # Show supported filters
        supported = manager.get_supported_filters()
        print(f"Supported filters: {[f.name for f in supported]}")
        print()
        
        # Add some filters
        print("Adding filters...")
        filter_ids = []
        
        # Add noise suppression
        filter_id = manager.add_filter(
            FilterType.NOISE_SUPPRESS,
            method=1,  # RNNoise
            suppress_level=-25,
            intensity=0.7
        )
        if filter_id is not None:
            filter_ids.append(filter_id)
        
        # Add gain
        filter_id = manager.add_filter(
            FilterType.GAIN,
            gain_db=5.0
        )
        if filter_id is not None:
            filter_ids.append(filter_id)
        
        # Add EQ
        filter_id = manager.add_filter(
            FilterType.EQUALIZER_3BAND,
            low_db=2.0,
            mid_db=-1.0,
            high_db=3.0
        )
        if filter_id is not None:
            filter_ids.append(filter_id)
        
        # Print summary
        manager.print_pipeline_summary()
        
        # Save configuration
        print("Saving configuration...")
        manager.save_pipeline_config("demo_config.json")
        
        # Cleanup
        manager.cleanup()
        print("Demo complete!")
        
    except Exception as e:
        print(f"Demo error: {e}")


def main():
    """Main function"""
    print("=== Audio Pipeline Manager Real-Time Test ===\n")
    
    # Check command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        demo_pipeline_management()
        return
    
    processor = None
    try:
        processor = RealTimeAudioProcessor()
        
        # List available audio devices
        processor.list_audio_devices()
        
        # Setup the processing pipeline
        processor.setup_pipeline()
        
        # Start real-time processing
        processor.start_streaming()
        
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure:")
        print("1. obs-mic-filter.dll is available in the current directory or build folders")
        print("2. PyAudio is installed: pip install PyAudio")
        print("3. numpy is installed: pip install numpy")
        print("4. Your microphone and speakers are connected")
        print("\nYou can also run with --demo flag to test without audio devices")
        
    finally:
        if processor:
            processor.cleanup()


if __name__ == "__main__":
    main()