# OBS Mic Filter - Standalone DLL

A standalone audio processing library extracted from OBS Studio's audio filters, designed to provide the same audio processing capabilities without OBS dependencies.

## Overview

This library provides a modular audio processing pipeline that abstracts away OBS-specific types and uses plain PCM buffers and parameter structures. It includes implementations of all major OBS audio filters.

## Architecture

### Core Components

- **obs_pipeline.h/c** - Main public API implementation
- **pipeline_manager.h/c** - Internal pipeline management and filter chaining
- **memory_utils.h/c** - Memory management abstraction
- **audio_utils.h/c** - Audio processing utilities

### Filter Wrappers

Each OBS filter has been wrapped to remove OBS dependencies:

- **filter_wrapper_gain.c** - Gain/volume control
- **filter_wrapper_noise_suppress.c** - Noise suppression (RNNoise/Speex/NVAFX)
- **filter_wrapper_eq.c** - 3-Band equalizer
- **filter_wrapper_compressor.c** - Audio compressor
- **filter_wrapper_expander.c** - Audio expander/gate

## Supported Filters

| Filter Type | Status | Description |
|-------------|--------|-------------|
| Gain | ✅ Implemented | Volume/gain adjustment (-30dB to +30dB) |
| Noise Suppression | 🚧 Stub | Noise reduction (RNNoise/Speex/NVAFX) |
| Noise Gate | 🚧 Stub | Gate with threshold control |
| Compressor | 🚧 Stub | Dynamic range compressor |
| Limiter | 🚧 Stub | Audio limiting |
| Expander | 🚧 Stub | Audio expansion/gating |
| Upward Compressor | 🚧 Stub | Upward compression |
| 3-Band Equalizer | 🚧 Stub | Low/Mid/High frequency bands |
| Invert Polarity | 🚧 Stub | Audio polarity inversion |

## API Usage

### Basic Pipeline Setup

```c
#include "obs_pipeline.h"

// Get default configuration
obs_pipeline_config_t config;
obs_pipeline_get_default_config(&config);

// Create pipeline
obs_pipeline_t* pipeline = obs_pipeline_create(&config);

// Add a gain filter
obs_filter_params_t filter_params;
obs_pipeline_get_default_filter_params(OBS_FILTER_GAIN, &filter_params);
filter_params.params.gain.gain_db = 6.0f; // +6dB gain
obs_pipeline_update_filter(pipeline, 0, &filter_params);

// Process audio
obs_audio_buffer_t audio_buffer = {
    .data = channel_pointers,
    .frames = frame_count,
    .channels = 2,
    .sample_rate = 48000,
    .timestamp = current_time
};
obs_pipeline_process(pipeline, &audio_buffer);

// Cleanup
obs_pipeline_destroy(pipeline);
```

### Audio Buffer Format

The library uses planar float audio format:
- **data**: Array of float* pointers (one per channel)
- **frames**: Number of audio frames per channel
- **channels**: Number of audio channels (1-8)
- **sample_rate**: Sample rate in Hz
- **timestamp**: Timestamp in nanoseconds

### Filter Configuration

Each filter type has its own parameter structure:

```c
// Gain filter
filter_params.type = OBS_FILTER_GAIN;
filter_params.params.gain.gain_db = 6.0f;

// Noise suppression filter
filter_params.type = OBS_FILTER_NOISE_SUPPRESS;
filter_params.params.noise_suppress.suppress_level = -30;
filter_params.params.noise_suppress.method = OBS_NOISE_SUPPRESS_RNNOISE;

// Compressor filter
filter_params.type = OBS_FILTER_COMPRESSOR;
filter_params.params.compressor.ratio = 4.0f;
filter_params.params.compressor.threshold = -18.0f;
filter_params.params.compressor.attack_time = 6.0f;
filter_params.params.compressor.release_time = 60.0f;
```

## Building

### Requirements
- CMake 3.16+
- C compiler with C17 support
- Optional: RNNoise library for noise suppression

### Build Steps

```bash
mkdir build
cd build
cmake ..
cmake --build .
```

### Optional Dependencies

- **RNNoise**: For high-quality noise suppression
- **SpeexDSP**: Alternative noise suppression method
- **NVAFX**: NVIDIA audio effects (Windows only)

## Implementation Status

This is the initial skeleton implementation focusing on:
- ✅ Project structure and build system
- ✅ Public API definition
- ✅ Pipeline management framework
- ✅ Filter wrapper architecture
- ✅ Memory and audio utilities
- ✅ Basic gain filter implementation
- 🚧 DSP implementations for other filters (TODO)

## Next Steps

1. **Implement DSP Logic**: Extract and port actual DSP code from OBS filters
2. **Add External Libraries**: Integrate RNNoise, SpeexDSP for noise suppression
3. **Optimize Performance**: Add SIMD optimizations, multi-threading
4. **Add Tests**: Comprehensive unit and integration tests
5. **Documentation**: Complete API documentation and examples

## File Structure

```
obs-mic-filter/
├── include/
│   └── obs_pipeline.h          # Public API header
├── src/
│   ├── obs_pipeline.c          # Main API implementation
│   ├── pipeline_manager.c      # Pipeline management
│   ├── memory_utils.c          # Memory utilities
│   ├── audio_utils.c           # Audio processing utilities
│   └── filter_wrapper_*.c     # Individual filter implementations
├── examples/
│   └── simple_test.c           # Basic usage example
├── CMakeLists.txt              # Build configuration
└── README.md                   # This file
```

## License

This project extracts and adapts code from OBS Studio, which is licensed under GPL v2. This derivative work maintains the same license.