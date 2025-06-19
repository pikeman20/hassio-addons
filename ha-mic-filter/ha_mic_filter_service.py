"""
Home Assistant Microphone Filter Service
========================================

Main service for the Home Assistant Real-time Microphone Filter addon.
This service integrates the audio pipeline manager with PulseAudio virtual
device management and provides a web interface for configuration.

Features:
- Real-time microphone filtering
- Virtual microphone device creation
- Web interface for configuration
- Home Assistant integration
- Persistent configuration
- Device monitoring
"""

import os
import sys
import json
import time
import logging
import threading
import argparse
from typing import Dict, List, Optional, Any
import numpy as np

# Import our modules
from audio_pipeline_manager import AudioPipelineManager, FilterType, NoiseSuppressionMethod
from pulse_audio_manager import PulseAudioManager, AudioDevice
from device_constants import (
    VIRTUAL_MIC_SINK_NAME,
    VIRTUAL_MIC_SOURCE_NAME,
    DEFAULT_VIRTUAL_MIC_DESCRIPTION,
    DEFAULT_VIRTUAL_SINK_DESCRIPTION
)


class HAMicFilterService:
    """Main service class for Home Assistant Microphone Filter addon"""
    
    def __init__(self, config_file: str = "/data/config.json"):
        """
        Initialize the service
        
        Args:
            config_file: Path to configuration file
        """
        self.config_file = config_file
        self.config = {}
        self.running = False
        
        # Setup logging
        self.setup_logging()
        
        # Initialize components
        self.audio_pipeline = None
        self.pulse_manager = None
        
        # Audio streaming state
        self.is_streaming = False
        self.current_input_device = None
        self.current_output_device = None
        self.current_monitoring_device = None
        
        # Load configuration
        self.load_configuration()
        
        self.logger.info("HA Microphone Filter Service initialized")
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        
        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Logging initialized at level: {log_level}")
    
    def load_configuration(self):
        """Load configuration from Home Assistant and config file"""
        # Load Home Assistant addon configuration
        try:
            ha_config = self.load_ha_config()
            self.config.update(ha_config)
            self.logger.info("Home Assistant configuration loaded")
        except Exception as e:
            self.logger.error(f"Failed to load HA config: {e}")
        
        # Load persistent configuration
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    persistent_config = json.load(f)
                    self.config.update(persistent_config)
                self.logger.info(f"Persistent configuration loaded from {self.config_file}")
        except Exception as e:
            self.logger.error(f"Failed to load persistent config: {e}")
        
        # Set defaults
        self.config.setdefault('sample_rate', 48000)
        self.config.setdefault('channels', 1)
        self.config.setdefault('buffer_size_ms', 10)
        self.config.setdefault('virtual_mic_name', 'HA_Filtered_Mic')
        self.config.setdefault('auto_start', False)
    
    def load_ha_config(self) -> Dict[str, Any]:
        """Load Home Assistant addon configuration"""
        config = {}
        
        # Read config from environment variables (set by bashio)
        config_mapping = {
            'virtual_mic_name': 'VIRTUAL_MIC_NAME',
            'sample_rate': 'SAMPLE_RATE',
            'channels': 'CHANNELS',
            'buffer_size_ms': 'BUFFER_SIZE_MS',
            'auto_start': 'AUTO_START',
            'log_level': 'LOG_LEVEL',
            'monitor_to_speakers': 'MONITOR_TO_SPEAKERS'
        }
        
        for key, env_var in config_mapping.items():
            value = os.getenv(env_var)
            if value is not None and value != 'null':
                # Convert types
                if key in ['sample_rate', 'channels', 'buffer_size_ms']:
                    try:
                        config[key] = int(value)
                    except ValueError:
                        pass
                elif key in ['auto_start', 'monitor_to_speakers']:
                    config[key] = value.lower() in ('true', '1', 'yes', 'on')
                else:
                    config[key] = value
        
        # Load audio pipeline configuration
        pipeline_config = self.load_pipeline_config_from_env()
        if pipeline_config:
            config['audio_pipeline'] = pipeline_config
        
        return config
    
    def load_pipeline_config_from_env(self) -> Optional[Dict[str, Any]]:
        """Load audio pipeline configuration from environment variables"""
        config = {}
        
        # Helper function to safely get environment variables
        def get_env_value(env_var, default_value, value_type=str):
            value = os.getenv(env_var)
            if value is None or value == 'null':
                return default_value
            try:
                if value_type == bool:
                    return value.lower() in ('true', '1', 'yes', 'on')
                elif value_type == int:
                    return int(value)
                elif value_type == float:
                    return float(value)
                else:
                    return value
            except (ValueError, TypeError):
                return default_value
        
        # Load noise suppression configuration
        config['noise_suppression'] = {
            'enabled': get_env_value('NOISE_SUPPRESSION_ENABLED', True, bool),
            'method': get_env_value('NOISE_SUPPRESSION_METHOD', 'rnnoise'),
            'intensity': get_env_value('NOISE_SUPPRESSION_INTENSITY', 0.8, float),
            'suppress_level': get_env_value('NOISE_SUPPRESSION_SUPPRESS_LEVEL', -30, int)
        }
        
        # Load gain configuration
        config['gain'] = {
            'enabled': get_env_value('GAIN_ENABLED', True, bool),
            'gain_db': get_env_value('GAIN_DB', 10.5, float)
        }
        
        # Load equalizer configuration
        config['equalizer'] = {
            'enabled': get_env_value('EQ_ENABLED', True, bool),
            'low_db': get_env_value('EQ_LOW_DB', 10.0, float),
            'mid_db': get_env_value('EQ_MID_DB', -20.0, float),
            'high_db': get_env_value('EQ_HIGH_DB', 12.5, float)
        }
        
        # Load expander configuration
        config['expander'] = {
            'enabled': get_env_value('EXP_ENABLED', True, bool),
            'ratio': get_env_value('EXP_RATIO', 4.0, float),
            'threshold': get_env_value('EXP_THRESHOLD', -55.0, float),
            'attack_time': get_env_value('EXP_ATTACK_TIME', 1.0, float),
            'release_time': get_env_value('EXP_RELEASE_TIME', 75.0, float),
            'output_gain': get_env_value('EXP_OUTPUT_GAIN', 2.0, float)
        }
        
        # Load compressor configuration
        config['compressor'] = {
            'enabled': get_env_value('COMP_ENABLED', True, bool),
            'ratio': get_env_value('COMP_RATIO', 4.0, float),
            'threshold': get_env_value('COMP_THRESHOLD', -7.0, float),
            'attack_time': get_env_value('COMP_ATTACK_TIME', 1.0, float),
            'release_time': get_env_value('COMP_RELEASE_TIME', 75.0, float),
            'output_gain': get_env_value('COMP_OUTPUT_GAIN', 0.0, float)
        }
        
        # Load limiter configuration
        config['limiter'] = {
            'enabled': get_env_value('LIM_ENABLED', True, bool),
            'threshold': get_env_value('LIM_THRESHOLD', -0.2, float),
            'release_time': get_env_value('LIM_RELEASE_TIME', 60.0, float)
        }
        
        return config
    
    def save_configuration(self):
        """Save current configuration to file"""
        try:
            # Create data directory if it doesn't exist
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            self.logger.info(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save configuration: {e}")
            return False
    
    def initialize_components(self) -> bool:
        """Initialize all service components"""
        try:
            # Initialize audio pipeline manager
            self.logger.info("Initializing audio pipeline manager...")
            self.audio_pipeline = AudioPipelineManager()
            
            if not self.audio_pipeline.library:
                self.logger.error("Failed to load audio pipeline library")
                return False
            
            # Initialize PulseAudio manager
            self.logger.info("Initializing PulseAudio manager...")
            self.pulse_manager = PulseAudioManager()
            
            if not self.pulse_manager.pulse:
                self.logger.error("Failed to connect to PulseAudio")
                return False
            
            # Use constants for device names
            self.pulse_manager.virtual_sink_name = VIRTUAL_MIC_SINK_NAME
            self.pulse_manager.virtual_source_name = VIRTUAL_MIC_SOURCE_NAME
            
            # Virtual devices are created by init script, just verify they exist
            self.logger.info("Virtual microphone devices should be created by init script")
            self.logger.info(f"Expected devices: sink='{VIRTUAL_MIC_SINK_NAME}', source='{VIRTUAL_MIC_SOURCE_NAME}'")
            
            # Refresh devices and check for virtual devices
            try:
                self.pulse_manager.refresh_devices()
                self.logger.info("Device refresh completed")
                
                # Check if virtual devices exist
                virtual_sink_found = any(device.name == VIRTUAL_MIC_SINK_NAME for device in self.pulse_manager.get_devices())
                virtual_source_found = any(device.name == VIRTUAL_MIC_SOURCE_NAME for device in self.pulse_manager.get_devices())
                
                if virtual_sink_found and virtual_source_found:
                    self.logger.info("Virtual devices detected in device list")
                else:
                    self.logger.warning(f"Virtual devices not in device list (sink: {virtual_sink_found}, source: {virtual_source_found})")
                    self.logger.info("This is normal - devices may be filtered out but still usable")
                
            except Exception as e:
                self.logger.warning(f"Device refresh failed: {e}")
            
            # Setup audio pipeline
            if not self.setup_audio_pipeline():
                self.logger.error("Failed to setup audio pipeline")
                return False
            
            
            # Log available devices for user reference
            self.log_available_devices()
            
            self.logger.info("All components initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error initializing components: {e}")
            return False
    
    def log_available_devices(self):
        """Log available audio devices for user reference"""
        try:
            if not self.pulse_manager:
                return
            
            input_devices = self.pulse_manager.get_input_devices()
            output_devices = self.pulse_manager.get_output_devices()
            
            self.logger.info("=== Available Audio Devices ===")
            
            if input_devices:
                self.logger.info("Input Devices (Microphones):")
                for device in input_devices:
                    self.logger.info(f"  - Name: '{device.name}' | Description: '{device.description}'")
            else:
                self.logger.warning("No input devices found")
            
            if output_devices:
                self.logger.info("Output Devices (Speakers/Sinks):")
                for device in output_devices:
                    self.logger.info(f"  - Name: '{device.name}' | Description: '{device.description}'")
            else:
                self.logger.warning("No output devices found")
            
            self.logger.info("=== End Device List ===")
            
        except Exception as e:
            self.logger.error(f"Error logging available devices: {e}")
    
    def setup_audio_pipeline(self) -> bool:
        """Setup the audio processing pipeline"""
        try:
            # Create pipeline
            sample_rate = self.config.get('sample_rate', 48000)
            channels = self.config.get('channels', 1)
            buffer_size_ms = self.config.get('buffer_size_ms', 10)
            
            if not self.audio_pipeline.create_pipeline(
                sample_rate=sample_rate,
                channels=channels,
                buffer_size_ms=buffer_size_ms
            ):
                return False
            
            # Load filters from configuration
            pipeline_config = self.config.get('audio_pipeline', {})
            
            # Add noise suppression
            noise_config = pipeline_config.get('noise_suppression', {})
            if noise_config.get('enabled', True):
                method_name = noise_config.get('method', 'rnnoise')
                method_map = {
                    'speex': NoiseSuppressionMethod.SPEEX.value,
                    'rnnoise': NoiseSuppressionMethod.RNNOISE.value,
                    'nvafx_denoiser': NoiseSuppressionMethod.NVAFX_DENOISER.value,
                    'nvafx_dereverb': NoiseSuppressionMethod.NVAFX_DEREVERB.value,
                    'nvafx_both': NoiseSuppressionMethod.NVAFX_BOTH.value
                }
                
                self.audio_pipeline.add_filter(
                    FilterType.NOISE_SUPPRESS,
                    method=method_map.get(method_name, NoiseSuppressionMethod.RNNOISE.value),
                    intensity=noise_config.get('intensity', 0.8),
                    suppress_level=noise_config.get('suppress_level', -30)
                )
            
            # Add gain
            gain_config = pipeline_config.get('gain', {})
            if gain_config.get('enabled', True):
                self.audio_pipeline.add_filter(
                    FilterType.GAIN,
                    gain_db=gain_config.get('gain_db', 10.5)
                )
            
            # Add equalizer
            eq_config = pipeline_config.get('equalizer', {})
            if eq_config.get('enabled', True):
                self.audio_pipeline.add_filter(
                    FilterType.EQUALIZER_3BAND,
                    low_db=eq_config.get('low_db', 10.0),
                    mid_db=eq_config.get('mid_db', -20.0),
                    high_db=eq_config.get('high_db', 12.5)
                )
            
            # Add expander
            exp_config = pipeline_config.get('expander', {})
            if exp_config.get('enabled', True):
                self.audio_pipeline.add_filter(
                    FilterType.EXPANDER,
                    ratio=exp_config.get('ratio', 4.0),
                    threshold=exp_config.get('threshold', -55.0),
                    attack_time=exp_config.get('attack_time', 1.0),
                    release_time=exp_config.get('release_time', 75.0),
                    output_gain=exp_config.get('output_gain', 2.0)
                )
            
            # Add compressor
            comp_config = pipeline_config.get('compressor', {})
            if comp_config.get('enabled', True):
                self.audio_pipeline.add_filter(
                    FilterType.COMPRESSOR,
                    ratio=comp_config.get('ratio', 4.0),
                    threshold=comp_config.get('threshold', -7.0),
                    attack_time=comp_config.get('attack_time', 1.0),
                    release_time=comp_config.get('release_time', 75.0),
                    output_gain=comp_config.get('output_gain', 0.0)
                )
            
            # Add limiter
            lim_config = pipeline_config.get('limiter', {})
            if lim_config.get('enabled', True):
                self.audio_pipeline.add_filter(
                    FilterType.LIMITER,
                    threshold=lim_config.get('threshold', -0.2),
                    release_time=lim_config.get('release_time', 60.0)
                )
            
            self.logger.info("Audio pipeline setup completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Error setting up audio pipeline: {e}")
            return False
    
    def audio_processor_callback(self, audio_data: np.ndarray) -> np.ndarray:
        """Audio processing callback for real-time filtering"""
        if self.audio_pipeline:
            return self.audio_pipeline.apply_filters(audio_data)
        return audio_data
    
    def start_streaming(self) -> bool:
        """
        Start audio streaming using Home Assistant's default audio devices
        
        Returns:
            True if streaming started successfully, False otherwise
        """
        if self.is_streaming:
            self.logger.warning("Audio streaming already active")
            return False
        
        # Start streaming with HA defaults
        success = self.pulse_manager.start_audio_streaming(
            audio_processor_callback=self.audio_processor_callback,
            sample_rate=self.config.get('sample_rate', 48000),
            channels=self.config.get('channels', 1),
            frames_per_buffer=480,
            monitor_to_speakers=self.config.get('monitor_to_speakers', False)
        )
        
        if success:
            self.is_streaming = True
            # Get the devices that were actually used
            ha_input, ha_output = self.pulse_manager.get_ha_default_devices()
            self.current_input_device = ha_input
            self.current_output_device = self.pulse_manager.virtual_sink_name
            self.current_monitoring_device = ha_output if self.config.get('monitor_to_speakers', False) else None
            self.logger.info("Audio streaming started")
        
        return success
    
    def stop_streaming(self):
        """Stop audio streaming"""
        if not self.is_streaming:
            return
        
        self.pulse_manager.stop_audio_streaming()
        self.is_streaming = False
        self.current_input_device = None
        self.current_output_device = None
        self.current_monitoring_device = None
        self.logger.info("Audio streaming stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current service status"""
        return {
            'running': self.running,
            'streaming': self.is_streaming,
            'audio_pipeline_ready': self.audio_pipeline is not None and self.audio_pipeline.pipeline is not None,
            'pulseaudio_connected': self.pulse_manager is not None and self.pulse_manager.pulse is not None,
            'virtual_microphone': self.pulse_manager.get_virtual_microphone_info() if self.pulse_manager else None,
            'current_devices': {
                'input': self.current_input_device,
                'output': self.current_output_device,
                'monitoring': self.current_monitoring_device
            },
            'config': self.config
        }
    
    def run(self, auto_start: bool = False):
        """
        Run the main service
        
        Args:
            auto_start: Whether to automatically start streaming
        """
        self.logger.info("Starting HA Microphone Filter Service...")
        
        # Initialize components
        if not self.initialize_components():
            self.logger.error("Failed to initialize components")
            return
        
        self.running = True
        
        # Auto-start streaming if configured
        if auto_start or self.config.get('auto_start', False):
            self.logger.info("Auto-starting audio streaming...")
            
            # Wait a bit more for devices to be fully ready
            time.sleep(3)
            
            # Try auto-start with retries
            max_retries = 3
            for retry in range(max_retries):
                if self.start_streaming():
                    self.logger.info("Auto-start successful")
                    break
                else:
                    if retry < max_retries - 1:
                        self.logger.warning(f"Auto-start attempt {retry + 1} failed, retrying in 5 seconds...")
                        time.sleep(5)
                        # Refresh devices before retry
                        try:
                            self.pulse_manager.refresh_devices()
                        except Exception:
                            pass
                    else:
                        self.logger.warning("Auto-start failed after all retries - continuing in standby mode")
        
        
        self.logger.info("Service running - press Ctrl+C to stop")
        
        try:
            # Main service loop
            while self.running:
                time.sleep(1)
                
                # Periodic status check
                if self.is_streaming and not self.pulse_manager.is_streaming:
                    self.logger.warning("Streaming stopped unexpectedly")
                    self.is_streaming = False
                
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        except Exception as e:
            self.logger.error(f"Unexpected error in main loop: {e}")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Shutdown the service"""
        self.logger.info("Shutting down HA Microphone Filter Service...")
        
        self.running = False
        
        # Stop streaming
        if self.is_streaming:
            self.stop_streaming()
        
        # Cleanup components
        if self.pulse_manager:
            self.pulse_manager.cleanup()
        
        if self.audio_pipeline:
            self.audio_pipeline.cleanup()
        
        # Save configuration
        self.save_configuration()
        
        self.logger.info("Service shutdown complete")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='HA Microphone Filter Service')
    parser.add_argument('--auto-start', action='store_true', 
                       help='Automatically start audio streaming')
    parser.add_argument('--config', default='/data/config.json',
                       help='Configuration file path')
    
    args = parser.parse_args()
    
    # Create and run service
    service = HAMicFilterService(config_file=args.config)
    service.run(auto_start=args.auto_start)


if __name__ == '__main__':
    main()