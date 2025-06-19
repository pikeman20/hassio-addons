"""
PulseAudio Manager for Home Assistant Addon
===========================================

This module manages PulseAudio devices and virtual microphone creation
for the Home Assistant Real-time Microphone Filter addon.

Features:
- Virtual microphone device creation
- Audio device enumeration
- Real-time audio streaming
- Device monitoring and management
- Home Assistant OS integration
"""

import subprocess
import time
import threading
import logging
import json
import os
from typing import Dict, List, Optional, Tuple, Any
import pulsectl
import numpy as np
import sounddevice as sd
from device_constants import (
    VIRTUAL_MIC_SINK_NAME,
    VIRTUAL_MIC_SOURCE_NAME,
    DEFAULT_VIRTUAL_MIC_DESCRIPTION,
    DEFAULT_VIRTUAL_SINK_DESCRIPTION
)


class AudioDevice:
    """Represents an audio device"""
    
    def __init__(self, device_id: int, name: str, description: str, 
                 max_input_channels: int = 0, max_output_channels: int = 0,
                 default_sample_rate: float = 48000.0):
        self.device_id = device_id
        self.name = name
        self.description = description
        self.max_input_channels = max_input_channels
        self.max_output_channels = max_output_channels
        self.default_sample_rate = default_sample_rate
        self.is_input = max_input_channels > 0
        self.is_output = max_output_channels > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert device to dictionary"""
        return {
            'id': self.device_id,
            'name': self.name,
            'description': self.description,
            'max_input_channels': self.max_input_channels,
            'max_output_channels': self.max_output_channels,
            'default_sample_rate': self.default_sample_rate,
            'is_input': self.is_input,
            'is_output': self.is_output
        }


class PulseAudioManager:
    """
    PulseAudio manager for virtual microphone device creation and management
    """
    
    def __init__(self):
        """Initialize PulseAudio manager"""
        self.logger = logging.getLogger(__name__)
        self.pulse = None
        self.virtual_sink_name = VIRTUAL_MIC_SINK_NAME
        self.virtual_source_name = VIRTUAL_MIC_SOURCE_NAME
        self.virtual_sink_module_id = None
        self.virtual_source_module_id = None
        self.loopback_module_id = None
        self.devices: Dict[int, AudioDevice] = {}
        self.is_streaming = False
        self.stream_thread = None
        self.input_stream = None
        self.output_stream = None
        
        # Connect to PulseAudio
        self.connect()
    
    def connect(self) -> bool:
        """
        Connect to Home Assistant's PulseAudio server
        
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            # Connect to Home Assistant's PulseAudio server
            self.pulse = pulsectl.Pulse('ha-mic-filter')
            
            # Test the connection by getting server info
            server_info = self.pulse.server_info()
            self.logger.info(f"Connected to Home Assistant's PulseAudio server (version: {server_info.server_version})")
            
            # Log default devices
            if server_info.default_sink_name:
                self.logger.info(f"Default sink: {server_info.default_sink_name}")
            if server_info.default_source_name:
                self.logger.info(f"Default source: {server_info.default_source_name}")
            
            self.refresh_devices()
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to Home Assistant's PulseAudio: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from PulseAudio server"""
        if self.pulse:
            try:
                self.pulse.close()
                self.pulse = None
                self.logger.info("Disconnected from PulseAudio server")
            except Exception as e:
                self.logger.error(f"Error disconnecting from PulseAudio: {e}")
    
    def refresh_devices(self):
        """Refresh the list of available audio devices"""
        if not self.pulse:
            return
        
        try:
            self.devices.clear()
            device_id = 0
            
            # Get sources (input devices) - include ALL sources for proper device detection
            for source in self.pulse.source_list():
                # Only skip monitor sources of our virtual devices to avoid duplicates
                if source.name.endswith('.monitor') and 'virtual_mic' in source.name:
                    continue
                device = AudioDevice(
                    device_id=device_id,
                    name=source.name,
                    description=source.description,
                    max_input_channels=source.channel_count,
                    max_output_channels=0,
                    default_sample_rate=float(source.sample_spec.rate)
                )
                self.devices[device_id] = device
                device_id += 1
            
            # Get sinks (output devices) - include ALL sinks
            for sink in self.pulse.sink_list():
                device = AudioDevice(
                    device_id=device_id,
                    name=sink.name,
                    description=sink.description,
                    max_input_channels=0,
                    max_output_channels=sink.channel_count,
                    default_sample_rate=float(sink.sample_spec.rate)
                )
                self.devices[device_id] = device
                device_id += 1
            
            self.logger.info(f"Refreshed {len(self.devices)} audio devices")
            
        except Exception as e:
            self.logger.error(f"Error refreshing devices: {e}")
    
    def get_devices(self) -> List[AudioDevice]:
        """
        Get list of available audio devices
        
        Returns:
            List of AudioDevice objects
        """
        return list(self.devices.values())
    
    def get_input_devices(self) -> List[AudioDevice]:
        """Get list of input devices only"""
        return [device for device in self.devices.values() if device.is_input]
    
    def get_output_devices(self) -> List[AudioDevice]:
        """Get list of output devices only"""
        return [device for device in self.devices.values() if device.is_output]
    
    def find_device_by_name(self, device_name: str) -> Optional[AudioDevice]:
        """
        Find device by name or description
        
        Args:
            device_name: Device name or description to search for
            
        Returns:
            AudioDevice if found, None otherwise
        """
        if not device_name:
            return None
        
        # Search by exact name match first
        for device in self.devices.values():
            if device.name == device_name:
                return device
        
        # Search by description match
        for device in self.devices.values():
            if device.description == device_name:
                return device
        
        # Search by partial name match (case insensitive)
        device_name_lower = device_name.lower()
        for device in self.devices.values():
            if device_name_lower in device.name.lower():
                return device
        
        # Search by partial description match (case insensitive)
        for device in self.devices.values():
            if device_name_lower in device.description.lower():
                return device
        
        return None
    
    def get_ha_default_devices(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get Home Assistant's default audio input and output devices from PulseAudio
        
        When 'audio: true' is set in config.yaml, HA maps the audio system into the container.
        We can get the default devices directly from PulseAudio server info.
        
        Returns:
            Tuple of (default_input_device_name, default_output_device_name)
        """
        try:
            default_input = None
            default_output = None
            
            if self.pulse:
                try:
                    # Get server information which contains default devices
                    server_info = self.pulse.server_info()
                    
                    if server_info.default_source_name:
                        default_input = server_info.default_source_name
                        self.logger.info(f"Found HA default input: {default_input}")
                    
                    if server_info.default_sink_name:
                        default_output = server_info.default_sink_name
                        self.logger.info(f"Found HA default output: {default_output}")
                    
                    # Also log available devices for debugging
                    self.logger.debug("Available sources (inputs):")
                    for source in self.pulse.source_list():
                        self.logger.debug(f"  - {source.name}: {source.description}")
                    
                    self.logger.debug("Available sinks (outputs):")
                    for sink in self.pulse.sink_list():
                        self.logger.debug(f"  - {sink.name}: {sink.description}")
                        
                except Exception as e:
                    self.logger.warning(f"Could not get PulseAudio default devices: {e}")
            else:
                self.logger.warning("PulseAudio not connected - cannot get default devices")
            
            return default_input, default_output
            
        except Exception as e:
            self.logger.error(f"Error getting HA default devices: {e}")
            return None, None
    
    def get_device_by_name_or_id(self, device_identifier) -> Optional[AudioDevice]:
        """
        Get device by name, description, or ID
        
        Args:
            device_identifier: Device name, description, or ID
            
        Returns:
            AudioDevice if found, None otherwise
        """
        if device_identifier is None:
            return None
        
        # If it's an integer, treat as device ID
        if isinstance(device_identifier, int):
            return self.devices.get(device_identifier)
        
        # If it's a string that looks like a number, try as ID first
        if isinstance(device_identifier, str) and device_identifier.isdigit():
            device_id = int(device_identifier)
            device = self.devices.get(device_id)
            if device:
                return device
        
        # Otherwise, search by name/description
        if isinstance(device_identifier, str):
            return self.find_device_by_name(device_identifier)
        
        return None
    
    def create_virtual_microphone(self, virtual_mic_name: str = "HA_Filtered_Mic") -> bool:
        """
        Create virtual microphone device
        
        Args:
            virtual_mic_name: Name for the virtual microphone
            
        Returns:
            True if created successfully, False otherwise
        """
        if not self.pulse:
            self.logger.error("PulseAudio not connected")
            return False
        
        try:
            # Remove existing virtual devices
            self.remove_virtual_microphone()
            
            # Create null sink for virtual microphone
            self.logger.info("Creating virtual microphone sink...")
            sink_description = f"{virtual_mic_name}_Sink"
            
            result = subprocess.run([
                'pactl', 'load-module', 'module-null-sink',
                f'sink_name={self.virtual_sink_name}',
                f'sink_properties=device.description="{sink_description}"'
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                self.virtual_sink_module_id = int(result.stdout.strip())
                self.logger.info(f"Virtual sink created with module ID: {self.virtual_sink_module_id}")
            else:
                self.logger.error(f"Failed to create virtual sink: {result.stderr}")
                return False
            
            # Create virtual source from the null sink monitor
            self.logger.info("Creating virtual microphone source...")
            source_description = virtual_mic_name
            
            result = subprocess.run([
                'pactl', 'load-module', 'module-virtual-source',
                f'source_name={self.virtual_source_name}',
                f'source_properties=device.description="{source_description}"',
                f'master={self.virtual_sink_name}.monitor'
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                self.virtual_source_module_id = int(result.stdout.strip())
                self.logger.info(f"Virtual source created with module ID: {self.virtual_source_module_id}")
            else:
                self.logger.error(f"Failed to create virtual source: {result.stderr}")
                self.remove_virtual_microphone()
                return False
            
            # Wait for devices to be available
            time.sleep(1)
            self.refresh_devices()
            
            self.logger.info(f"Virtual microphone '{virtual_mic_name}' created successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating virtual microphone: {e}")
            return False
    
    def remove_virtual_microphone(self):
        """Remove virtual microphone device"""
        try:
            # Remove virtual source
            if self.virtual_source_module_id is not None:
                subprocess.run(['pactl', 'unload-module', str(self.virtual_source_module_id)])
                self.virtual_source_module_id = None
                self.logger.info("Virtual source removed")
            
            # Remove virtual sink
            if self.virtual_sink_module_id is not None:
                subprocess.run(['pactl', 'unload-module', str(self.virtual_sink_module_id)])
                self.virtual_sink_module_id = None
                self.logger.info("Virtual sink removed")
            
            # Remove loopback if exists
            if self.loopback_module_id is not None:
                subprocess.run(['pactl', 'unload-module', str(self.loopback_module_id)])
                self.loopback_module_id = None
                self.logger.info("Loopback module removed")
                
        except Exception as e:
            self.logger.error(f"Error removing virtual microphone: {e}")
    
    def start_audio_streaming(self, audio_processor_callback=None, sample_rate: int = 48000,
                            channels: int = 1, frames_per_buffer: int = 480,
                            monitor_to_speakers: bool = False) -> bool:
        """
        Start real-time audio streaming using Home Assistant's default audio devices
        
        Args:
            audio_processor_callback: Callback function for audio processing
            sample_rate: Sample rate in Hz
            channels: Number of channels
            frames_per_buffer: Frames per buffer
            monitor_to_speakers: Whether to output processed audio to speakers for monitoring
            
        Returns:
            True if streaming started successfully, False otherwise
        """
        if self.is_streaming:
            self.logger.warning("Audio streaming already running")
            return False
        
        try:
            # Get HA default devices
            ha_default_input, ha_default_output = self.get_ha_default_devices()
            
            if not ha_default_input:
                self.logger.error("No default input device available from Home Assistant")
                return False
            
            # Find input device
            input_device = self.find_device_by_name(ha_default_input)
            if not input_device or not input_device.is_input:
                self.logger.error(f"Invalid or not found HA default input device: {ha_default_input}")
                return False
            
            # Find virtual microphone sink for output
            virtual_output_device = self.find_device_by_name(self.virtual_sink_name)
            if not virtual_output_device:
                self.logger.error(f"Virtual microphone sink not found: {self.virtual_sink_name}")
                return False
            
            self.logger.info(f"Starting audio streaming: {input_device.description} -> Virtual Microphone")
            
            # Configure streaming parameters
            self.sample_rate = sample_rate
            self.channels = channels
            self.frames_per_buffer = frames_per_buffer
            self.audio_processor_callback = audio_processor_callback
            self.monitor_to_speakers = monitor_to_speakers
            
            # Get speaker device for monitoring if enabled
            self.speaker_device = None
            if monitor_to_speakers and ha_default_output:
                self.speaker_device = self.find_device_by_name(ha_default_output)
                if self.speaker_device and self.speaker_device.is_output:
                    self.logger.info(f"Monitor output enabled to: {self.speaker_device.description}")
                else:
                    self.logger.warning(f"Could not find speaker device for monitoring: {ha_default_output}")
                    self.speaker_device = None
            
            # Start streaming thread
            self.is_streaming = True
            self.stream_thread = threading.Thread(target=self._streaming_worker,
                                                 args=(input_device, virtual_output_device))
            self.stream_thread.daemon = True
            self.stream_thread.start()
            
            self.logger.info("Audio streaming started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error starting audio streaming: {e}")
            return False
    
    def stop_audio_streaming(self):
        """Stop audio streaming"""
        if not self.is_streaming:
            return
        
        self.logger.info("Stopping audio streaming...")
        self.is_streaming = False
        
        # Close streams
        if self.input_stream:
            self.input_stream.stop()
            self.input_stream.close()
            self.input_stream = None
        
        if self.output_stream:
            self.output_stream.stop()
            self.output_stream.close()
            self.output_stream = None
        
        # Wait for thread to finish
        if self.stream_thread:
            self.stream_thread.join(timeout=5)
            self.stream_thread = None
        
        self.logger.info("Audio streaming stopped")
    
    def _streaming_worker(self, input_device: AudioDevice, output_device: AudioDevice):
        """Worker thread for audio streaming"""
        speaker_stream = None
        try:
            # Create audio streams using sounddevice
            stream_contexts = []
            
            # Always create input and virtual microphone output streams
            input_stream = sd.InputStream(
                device=input_device.name,
                channels=self.channels,
                samplerate=self.sample_rate,
                blocksize=self.frames_per_buffer,
                dtype=np.float32
            )
            stream_contexts.append(input_stream)
            
            output_stream = sd.OutputStream(
                device=output_device.name,
                channels=self.channels,
                samplerate=self.sample_rate,
                blocksize=self.frames_per_buffer,
                dtype=np.float32
            )
            stream_contexts.append(output_stream)
            
            # Create speaker monitoring stream if enabled
            if self.monitor_to_speakers and hasattr(self, 'speaker_device') and self.speaker_device:
                speaker_stream = sd.OutputStream(
                    device=self.speaker_device.name,
                    channels=self.channels,
                    samplerate=self.sample_rate,
                    blocksize=self.frames_per_buffer,
                    dtype=np.float32
                )
                stream_contexts.append(speaker_stream)
            
            # Start all streams
            for stream in stream_contexts:
                stream.start()
            
            self.input_stream = input_stream
            self.output_stream = output_stream
            
            self.logger.info("Audio streams created, starting processing loop...")
            
            while self.is_streaming:
                try:
                    # Read audio from input
                    audio_data, overflowed = input_stream.read(self.frames_per_buffer)
                    
                    if overflowed:
                        self.logger.warning("Input overflow detected")
                    
                    # Process audio through the pipeline
                    if self.audio_processor_callback:
                        processed_audio = self.audio_processor_callback(audio_data.flatten())
                        
                        # Reshape if needed
                        if len(processed_audio.shape) == 1 and self.channels > 1:
                            processed_audio = processed_audio.reshape(-1, self.channels)
                        elif len(processed_audio.shape) == 1:
                            processed_audio = processed_audio.reshape(-1, 1)
                    else:
                        processed_audio = audio_data
                    
                    # Write to output (virtual microphone)
                    output_stream.write(processed_audio)
                    
                    # Write to speakers for monitoring if enabled
                    if speaker_stream is not None:
                        try:
                            speaker_stream.write(processed_audio)
                        except Exception as e:
                            self.logger.warning(f"Error writing to speaker monitoring: {e}")
                    
                except Exception as e:
                    if self.is_streaming:  # Only log if we're still supposed to be streaming
                        self.logger.error(f"Error in streaming loop: {e}")
                    break
            
        except Exception as e:
            self.logger.error(f"Error in streaming worker: {e}")
        finally:
            # Clean up streams
            try:
                if hasattr(self, 'input_stream') and self.input_stream:
                    self.input_stream.stop()
                    self.input_stream.close()
                if hasattr(self, 'output_stream') and self.output_stream:
                    self.output_stream.stop()
                    self.output_stream.close()
                if speaker_stream:
                    speaker_stream.stop()
                    speaker_stream.close()
            except Exception as e:
                self.logger.warning(f"Error cleaning up streams: {e}")
            
            self.is_streaming = False
            self.logger.info("Streaming worker finished")
    
    def get_virtual_microphone_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the virtual microphone
        
        Returns:
            Dictionary with virtual microphone info or None if not created
        """
        if self.virtual_sink_module_id is None or self.virtual_source_module_id is None:
            return None
        
        return {
            'sink_name': self.virtual_sink_name,
            'source_name': self.virtual_source_name,
            'sink_module_id': self.virtual_sink_module_id,
            'source_module_id': self.virtual_source_module_id,
            'is_streaming': self.is_streaming
        }
    
    def cleanup(self):
        """Cleanup resources"""
        self.logger.info("Cleaning up PulseAudio manager...")
        
        # Stop streaming
        self.stop_audio_streaming()
        
        # Remove virtual microphone
        self.remove_virtual_microphone()
        
        # Disconnect from PulseAudio
        self.disconnect()
        
        self.logger.info("PulseAudio manager cleanup complete")