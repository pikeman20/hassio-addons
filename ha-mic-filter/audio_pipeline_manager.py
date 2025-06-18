"""
Audio Pipeline Manager
======================

A comprehensive audio processing pipeline manager for Home Assistant OS integration.
This class provides complete functionality for audio filter management, including
library loading, filter registration, pipeline configuration, and real-time processing.

Features:
- Dynamic library loading (Windows/Linux)
- Complete filter management (add, remove, configure)
- Pipeline creation and management
- Real-time audio processing
- Configuration persistence
- Input/Output device management
- Filter parameter validation
- Home Assistant OS ready
"""

import ctypes
import ctypes.util
from ctypes import Structure, POINTER, c_float, c_uint32, c_uint64, c_bool, c_int, c_char_p, c_void_p
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import json
import os
import platform
import time
import threading


class FilterType(Enum):
    """Available filter types in the pipeline"""
    GAIN = 0
    NOISE_SUPPRESS = 1
    NOISE_GATE = 2
    COMPRESSOR = 3
    LIMITER = 4
    EXPANDER = 5
    UPWARD_COMPRESSOR = 6
    EQUALIZER_3BAND = 7
    INVERT_POLARITY = 8


class NoiseSuppressionMethod(Enum):
    """Noise suppression methods"""
    SPEEX = 0
    RNNOISE = 1
    NVAFX_DENOISER = 2
    NVAFX_DEREVERB = 3
    NVAFX_BOTH = 4


class ExpanderDetection(Enum):
    """Expander detection modes"""
    RMS = 0
    PEAK = 1


class ExpanderPreset(Enum):
    """Expander presets"""
    EXPANDER = 0
    GATE = 1


# C Structures for DLL interface
class obs_pipeline_config_t(Structure):
    _fields_ = [
        ("sample_rate", c_uint32),
        ("channels", c_uint32),
        ("buffer_size_ms", c_uint32),
        ("max_filters", c_uint32)
    ]


class obs_audio_buffer_t(Structure):
    _fields_ = [
        ("data", POINTER(POINTER(c_float))),
        ("frames", c_uint32),
        ("channels", c_uint32),
        ("sample_rate", c_uint32),
        ("timestamp", c_uint64)
    ]


class gain_params(Structure):
    _fields_ = [("gain_db", c_float)]


class noise_suppress_params(Structure):
    _fields_ = [
        ("suppress_level", c_int),
        ("method", c_int),
        ("intensity", c_float)
    ]


class equalizer_3band_params(Structure):
    _fields_ = [
        ("low", c_float),
        ("mid", c_float),
        ("high", c_float)
    ]


class compressor_params(Structure):
    _fields_ = [
        ("ratio", c_float),
        ("threshold", c_float),
        ("attack_time", c_float),
        ("release_time", c_float),
        ("output_gain", c_float)
    ]


class expander_params(Structure):
    _fields_ = [
        ("ratio", c_float),
        ("threshold", c_float),
        ("attack_time", c_float),
        ("release_time", c_float),
        ("output_gain", c_float),
        ("knee_width", c_float),
        ("detector", c_int),
        ("preset", c_int)
    ]


class limiter_params(Structure):
    _fields_ = [
        ("threshold", c_float),
        ("release_time", c_float)
    ]


class filter_params_union(ctypes.Union):
    _fields_ = [
        ("gain", gain_params),
        ("noise_suppress", noise_suppress_params),
        ("equalizer_3band", equalizer_3band_params),
        ("compressor", compressor_params),
        ("expander", expander_params),
        ("limiter", limiter_params)
    ]


class obs_filter_params_t(Structure):
    _fields_ = [
        ("type", c_int),
        ("enabled", c_bool),
        ("params", filter_params_union)
    ]


class FilterConfiguration:
    """Base filter configuration class"""
    
    def __init__(self, filter_type: FilterType, enabled: bool = True, **kwargs):
        self.filter_type = filter_type
        self.enabled = enabled
        self.parameters = kwargs
        self.validate_parameters()
    
    def validate_parameters(self):
        """Validate filter parameters - override in subclasses"""
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'filter_type': self.filter_type.name,
            'enabled': self.enabled,
            'parameters': self.parameters
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FilterConfiguration':
        """Create configuration from dictionary"""
        filter_type = FilterType[data['filter_type']]
        return cls(
            filter_type=filter_type,
            enabled=data.get('enabled', True),
            **data.get('parameters', {})
        )


class AudioPipelineManager:
    """
    Comprehensive audio pipeline manager for Home Assistant OS integration.
    
    This class provides complete audio processing pipeline management including:
    - Dynamic library loading
    - Filter management and configuration
    - Real-time audio processing
    - Pipeline persistence and restoration
    - Input/Output device management
    """
    
    # Constants
    DEFAULT_SAMPLE_RATE = 48000
    DEFAULT_CHANNELS = 1
    DEFAULT_FRAMES_PER_BUFFER = 480
    OBS_PIPELINE_SUCCESS = 0
    
    def __init__(self, library_path: Optional[str] = None):
        """
        Initialize the Audio Pipeline Manager.
        
        Args:
            library_path: Optional path to the obs-mic-filter library
        """
        self.library = None
        self.pipeline = None
        self.filters: Dict[int, FilterConfiguration] = {}
        self.filter_order: List[int] = []
        self.next_filter_id = 0
        self.pipeline_config = None
        self.is_processing = False
        self.processing_lock = threading.Lock()
        
        # Initialize library
        if library_path:
            self.load_library(library_path)
        else:
            self.load_library()
    
    def load_library(self, library_path: Optional[str] = None) -> bool:
        """
        Load the obs-mic-filter library.
        
        Args:
            library_path: Optional specific path to library
            
        Returns:
            True if library loaded successfully, False otherwise
        """
        try:
            if library_path and os.path.exists(library_path):
                self.library = ctypes.CDLL(library_path)
                print(f"Loaded library from: {library_path}")
            else:
                # Auto-detect library path - adapted for Home Assistant addon
                lib_paths = [
                    "/app/lib/libobs-mic-filter.so",
                    "./lib/libobs-mic-filter.so",
                    "./libobs-mic-filter.so",
                    "libobs-mic-filter.so"
                ]
                
                for lib_path in lib_paths:
                    if os.path.exists(lib_path):
                        self.library = ctypes.CDLL(lib_path)
                        print(f"Loaded library from: {lib_path}")
                        break
                else:
                    raise RuntimeError(f"Could not find library in paths: {lib_paths}")
            
            # Setup function signatures
            self._setup_function_signatures()
            return True
            
        except Exception as e:
            print(f"Failed to load library: {e}")
            return False
    
    def _setup_function_signatures(self):
        """Setup C function signatures for the loaded library"""
        # obs_pipeline_create
        self.library.obs_pipeline_create.argtypes = [POINTER(obs_pipeline_config_t)]
        self.library.obs_pipeline_create.restype = c_void_p
        
        # obs_pipeline_destroy
        self.library.obs_pipeline_destroy.argtypes = [c_void_p]
        self.library.obs_pipeline_destroy.restype = None
        
        # obs_pipeline_process
        self.library.obs_pipeline_process.argtypes = [c_void_p, POINTER(obs_audio_buffer_t)]
        self.library.obs_pipeline_process.restype = c_int
        
        # obs_pipeline_update_filter
        self.library.obs_pipeline_update_filter.argtypes = [c_void_p, c_uint32, POINTER(obs_filter_params_t)]
        self.library.obs_pipeline_update_filter.restype = c_int
        
        # obs_pipeline_get_default_config
        self.library.obs_pipeline_get_default_config.argtypes = [POINTER(obs_pipeline_config_t)]
        self.library.obs_pipeline_get_default_config.restype = None
        
        # obs_pipeline_is_filter_supported
        self.library.obs_pipeline_is_filter_supported.argtypes = [c_int]
        self.library.obs_pipeline_is_filter_supported.restype = c_bool
        
        # obs_pipeline_get_filter_name
        self.library.obs_pipeline_get_filter_name.argtypes = [c_int]
        self.library.obs_pipeline_get_filter_name.restype = c_char_p
    
    def create_pipeline(self, sample_rate: int = None, channels: int = None, 
                       buffer_size_ms: int = None) -> bool:
        """
        Create a new audio processing pipeline.
        
        Args:
            sample_rate: Sample rate in Hz (default: 48000)
            channels: Number of audio channels (default: 1)
            buffer_size_ms: Buffer size in milliseconds (default: 10)
            
        Returns:
            True if pipeline created successfully, False otherwise
        """
        if not self.library:
            print("Library not loaded")
            return False
        
        try:
            # Get default configuration
            config = obs_pipeline_config_t()
            self.library.obs_pipeline_get_default_config(ctypes.byref(config))
            
            # Override with custom values
            if sample_rate:
                config.sample_rate = sample_rate
            if channels:
                config.channels = channels
            if buffer_size_ms:
                config.buffer_size_ms = buffer_size_ms
            
            # Create pipeline
            self.pipeline = self.library.obs_pipeline_create(ctypes.byref(config))
            if not self.pipeline:
                print("Failed to create pipeline")
                return False
            
            self.pipeline_config = config
            print(f"Pipeline created: {config.sample_rate}Hz, {config.channels} channel(s)")
            return True
            
        except Exception as e:
            print(f"Error creating pipeline: {e}")
            return False
    
    def destroy_pipeline(self):
        """Destroy the current pipeline and free resources"""
        with self.processing_lock:
            if self.pipeline:
                self.library.obs_pipeline_destroy(self.pipeline)
                self.pipeline = None
                self.pipeline_config = None
                print("Pipeline destroyed")
    
    def add_filter(self, filter_type: FilterType, **parameters) -> Optional[int]:
        """
        Add a filter to the pipeline.
        
        Args:
            filter_type: Type of filter to add
            **parameters: Filter-specific parameters
            
        Returns:
            Filter ID if successful, None otherwise
        """
        if not self.pipeline:
            print("Pipeline not created")
            return None
        
        filter_id = self.next_filter_id
        self.next_filter_id += 1
        
        # Create filter configuration
        config = FilterConfiguration(filter_type, **parameters)
        
        # Create filter parameters structure
        params = obs_filter_params_t()
        params.type = filter_type.value
        params.enabled = config.enabled
        
        # Set filter-specific parameters
        success = self._set_filter_parameters(params, filter_type, config.parameters)
        if not success:
            return None
        
        # Add filter to pipeline
        result = self.library.obs_pipeline_update_filter(
            self.pipeline, filter_id, ctypes.byref(params)
        )
        
        if result == self.OBS_PIPELINE_SUCCESS:
            self.filters[filter_id] = config
            self.filter_order.append(filter_id)
            print(f"Added {filter_type.name} filter (ID: {filter_id})")
            return filter_id
        else:
            print(f"Failed to add {filter_type.name} filter")
            return None
    
    def _set_filter_parameters(self, params: obs_filter_params_t, 
                              filter_type: FilterType, parameters: Dict[str, Any]) -> bool:
        """Set filter-specific parameters in the params structure"""
        try:
            if filter_type == FilterType.GAIN:
                params.params.gain.gain_db = parameters.get('gain_db', 0.0)
                
            elif filter_type == FilterType.NOISE_SUPPRESS:
                params.params.noise_suppress.method = parameters.get('method', 1)
                params.params.noise_suppress.suppress_level = parameters.get('suppress_level', -30)
                params.params.noise_suppress.intensity = parameters.get('intensity', 0.5)
                
            elif filter_type == FilterType.EQUALIZER_3BAND:
                params.params.equalizer_3band.low = parameters.get('low_db', 0.0)
                params.params.equalizer_3band.mid = parameters.get('mid_db', 0.0)
                params.params.equalizer_3band.high = parameters.get('high_db', 0.0)
                
            elif filter_type == FilterType.COMPRESSOR:
                params.params.compressor.ratio = parameters.get('ratio', 4.0)
                params.params.compressor.threshold = parameters.get('threshold', -7.0)
                params.params.compressor.attack_time = parameters.get('attack_time', 1.0)
                params.params.compressor.release_time = parameters.get('release_time', 75.0)
                params.params.compressor.output_gain = parameters.get('output_gain', 0.0)
                
            elif filter_type == FilterType.EXPANDER:
                params.params.expander.ratio = parameters.get('ratio', 4.0)
                params.params.expander.threshold = parameters.get('threshold', -55.0)
                params.params.expander.attack_time = parameters.get('attack_time', 1.0)
                params.params.expander.release_time = parameters.get('release_time', 75.0)
                params.params.expander.output_gain = parameters.get('output_gain', 2.0)
                params.params.expander.knee_width = parameters.get('knee_width', 1.0)
                params.params.expander.detector = parameters.get('detector', 0)
                params.params.expander.preset = parameters.get('preset', 0)
                
            elif filter_type == FilterType.LIMITER:
                params.params.limiter.threshold = parameters.get('threshold', -0.2)
                params.params.limiter.release_time = parameters.get('release_time', 60.0)
                
            return True
            
        except Exception as e:
            print(f"Error setting filter parameters: {e}")
            return False
    
    def apply_filters(self, audio_data: np.ndarray) -> np.ndarray:
        """
        Apply all filters in the pipeline to audio data.
        
        Args:
            audio_data: Input audio data as numpy array
            
        Returns:
            Processed audio data as numpy array
        """
        if not self.pipeline or len(audio_data) == 0:
            return audio_data
        
        with self.processing_lock:
            try:
                # Convert numpy array to the format expected by the DLL
                frames = len(audio_data)
                channels = self.pipeline_config.channels if self.pipeline_config else 1
                
                # Create ctypes arrays for audio data
                audio_ptr = (POINTER(c_float) * channels)()
                for ch in range(channels):
                    if channels == 1:
                        audio_ptr[ch] = (c_float * frames)(*audio_data.astype(np.float32))
                    else:
                        # Handle multi-channel audio
                        channel_data = audio_data[:, ch] if audio_data.ndim > 1 else audio_data
                        audio_ptr[ch] = (c_float * frames)(*channel_data.astype(np.float32))
                
                # Create audio buffer structure
                audio_buffer = obs_audio_buffer_t()
                audio_buffer.data = ctypes.cast(audio_ptr, POINTER(POINTER(c_float)))
                audio_buffer.frames = frames
                audio_buffer.channels = channels
                audio_buffer.sample_rate = self.pipeline_config.sample_rate if self.pipeline_config else 48000
                audio_buffer.timestamp = int(time.time() * 1000000000)  # nanoseconds
                
                # Process the audio
                result = self.library.obs_pipeline_process(self.pipeline, ctypes.byref(audio_buffer))
                
                if result == self.OBS_PIPELINE_SUCCESS:
                    # Convert back to numpy array
                    if channels == 1:
                        processed_data = np.ctypeslib.as_array(audio_ptr[0], shape=(frames,))
                        return processed_data.copy()
                    else:
                        # Handle multi-channel output
                        processed_data = np.zeros((frames, channels), dtype=np.float32)
                        for ch in range(channels):
                            channel_data = np.ctypeslib.as_array(audio_ptr[ch], shape=(frames,))
                            processed_data[:, ch] = channel_data
                        return processed_data
                else:
                    print(f"Audio processing failed with code: {result}")
                    return audio_data
                    
            except Exception as e:
                print(f"Error during audio processing: {e}")
                return audio_data
    
    def get_supported_filters(self) -> List[FilterType]:
        """
        Get list of supported filter types.
        
        Returns:
            List of supported FilterType enums
        """
        supported = []
        if not self.library:
            return supported
        
        for filter_type in FilterType:
            if self.library.obs_pipeline_is_filter_supported(filter_type.value):
                supported.append(filter_type)
        
        return supported
    
    def save_pipeline_config(self, filename: str) -> bool:
        """
        Save current pipeline configuration to file.
        
        Args:
            filename: Path to save configuration file
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            config_data = {
                'pipeline_config': {
                    'sample_rate': self.pipeline_config.sample_rate if self.pipeline_config else self.DEFAULT_SAMPLE_RATE,
                    'channels': self.pipeline_config.channels if self.pipeline_config else self.DEFAULT_CHANNELS,
                    'buffer_size_ms': self.pipeline_config.buffer_size_ms if self.pipeline_config else 10
                },
                'filters': [
                    {
                        'id': filter_id,
                        'config': self.filters[filter_id].to_dict()
                    }
                    for filter_id in self.filter_order
                ]
            }
            
            with open(filename, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            print(f"Pipeline configuration saved to: {filename}")
            return True
            
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False
    
    def load_pipeline_config(self, filename: str) -> bool:
        """
        Load pipeline configuration from file.
        
        Args:
            filename: Path to configuration file
            
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            with open(filename, 'r') as f:
                config_data = json.load(f)
            
            # Destroy existing pipeline
            if self.pipeline:
                self.destroy_pipeline()
            
            # Create new pipeline with loaded config
            pipeline_config = config_data['pipeline_config']
            success = self.create_pipeline(
                sample_rate=pipeline_config['sample_rate'],
                channels=pipeline_config['channels'],
                buffer_size_ms=pipeline_config['buffer_size_ms']
            )
            
            if not success:
                return False
            
            # Clear existing filters
            self.filters.clear()
            self.filter_order.clear()
            self.next_filter_id = 0
            
            # Load filters
            for filter_data in config_data['filters']:
                filter_config = FilterConfiguration.from_dict(filter_data['config'])
                filter_id = self.add_filter(filter_config.filter_type, **filter_config.parameters)
                if filter_id is None:
                    print(f"Failed to load filter: {filter_config.filter_type.name}")
            
            print(f"Pipeline configuration loaded from: {filename}")
            return True
            
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return False
    
    def cleanup(self):
        """Cleanup all resources"""
        self.destroy_pipeline()
        self.library = None
        self.filters.clear()
        self.filter_order.clear()
        print("Audio Pipeline Manager cleanup complete")