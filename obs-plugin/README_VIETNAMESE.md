# OBS Mic Filter - Real-time Audio Processing DLL

Đây là một DLL standalone được tách xuất từ OBS Studio's obs-filters plugin, cho phép xử lý audio real-time bên ngoài OBS.

## Tính năng

✅ **Gain Control** - Điều chỉnh âm lượng (-30dB đến +30dB)  
✅ **RNNoise Noise Suppression** - Khử tiếng ồn AI-powered  
✅ **3-Band Equalizer** - Điều chỉnh Low/Mid/High frequencies  
✅ **Compressor** - Nén dynamic range  
✅ **Limiter** - Giới hạn peak audio  
✅ **Expander/Gate** - Mở rộng dynamic range  
✅ **Noise Gate** - Cắt tiếng ồn dưới ngưỡng  

## Cấu trúc Project

```
obs-mic-filter/
├── include/
│   └── obs_pipeline.h          # Public API header
├── src/
│   ├── obs_pipeline.c          # Main API implementation
│   ├── pipeline_manager.c      # Filter chain management
│   ├── filter_wrapper_*.c     # Individual filter wrappers
│   ├── memory_utils.c         # Memory management
│   └── audio_utils.c          # Audio utility functions
├── examples/
│   └── simple_test.c          # C usage example
├── python_realtime_test.py    # Python real-time test script
├── rebuild_dll.py             # Build automation script
└── CMakeLists.txt             # Build configuration
```

## Yêu cầu System

- **Windows**: MinGW-w64 hoặc Visual Studio
- **Linux**: GCC, MinGW-w64 (cho cross-compilation)
- **Dependencies**: RNNoise source code từ OBS Studio

## Build Instructions

### 1. Chuẩn bị

Đảm bảo bạn có OBS Studio source code:
```bash
# Directory structure phải như thế này:
parent_directory/
├── obs-studio/
│   └── plugins/obs-filters/rnnoise/  # RNNoise source
└── obs-mic-filter/                   # Project này
```

### 2. Linux với MinGW Cross-compilation

```bash
# Cài đặt MinGW-w64
sudo apt-get install mingw-w64

# Build DLL cho Windows
python rebuild_dll.py
```

### 3. Windows với MinGW

```bash
mkdir build-win64
cd build-win64
cmake .. -G "MinGW Makefiles"
mingw32-make
```

### 4. Windows với Visual Studio

```bash
mkdir build-win64
cd build-win64
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
```

## Python Real-time Test

### Cài đặt Python dependencies

```bash
pip install -r requirements.txt
```

### Chạy real-time test

```bash
python python_realtime_test.py
```

Script này sẽ:
1. Load `obs-mic-filter.dll`
2. Setup audio pipeline với: Noise Suppression → EQ → Gain
3. Capture audio từ microphone
4. Process qua filter chain
5. Output processed audio ra speakers

### Pipeline mặc định

```
Microphone → RNNoise Noise Suppression → 3-Band EQ → Gain (+3dB) → Speakers
```

## API Usage (C/C++)

### Basic Usage

```c
#include "obs_pipeline.h"

// 1. Create pipeline
obs_pipeline_config_t config;
obs_pipeline_get_default_config(&config);
config.sample_rate = 48000;
config.channels = 1;

obs_pipeline_t* pipeline = obs_pipeline_create(&config);

// 2. Add filters
obs_filter_params_t params;

// Add noise suppression
obs_pipeline_get_default_filter_params(OBS_FILTER_NOISE_SUPPRESS, &params);
params.params.noise_suppress.method = OBS_NOISE_SUPPRESS_RNNOISE;
obs_pipeline_update_filter(pipeline, 0, &params);

// Add gain
obs_pipeline_get_default_filter_params(OBS_FILTER_GAIN, &params);
params.params.gain.gain_db = 3.0f;
obs_pipeline_update_filter(pipeline, 1, &params);

// 3. Process audio
obs_audio_buffer_t audio_buffer;
// ... setup audio_buffer ...
obs_pipeline_process(pipeline, &audio_buffer);

// 4. Cleanup
obs_pipeline_destroy(pipeline);
```

### Filter Parameters

#### Gain Filter
```c
params.type = OBS_FILTER_GAIN;
params.params.gain.gain_db = 3.0f;  // -30.0 to 30.0 dB
```

#### Noise Suppression
```c
params.type = OBS_FILTER_NOISE_SUPPRESS;
params.params.noise_suppress.method = OBS_NOISE_SUPPRESS_RNNOISE;
params.params.noise_suppress.suppress_level = -30;  // dB
params.params.noise_suppress.intensity = 1.0f;      // 0.0-1.0
```

#### 3-Band Equalizer
```c
params.type = OBS_FILTER_EQUALIZER_3BAND;
params.params.equalizer_3band.low = 2.0f;   // Low frequency gain (dB)
params.params.equalizer_3band.mid = 0.0f;   // Mid frequency gain (dB)
params.params.equalizer_3band.high = 1.5f;  // High frequency gain (dB)
```

## Python Usage với ctypes

```python
import ctypes
import numpy as np

# Load DLL
dll = ctypes.CDLL("./obs-mic-filter.dll")

# Setup function signatures
dll.obs_pipeline_create.argtypes = [ctypes.POINTER(obs_pipeline_config_t)]
dll.obs_pipeline_create.restype = ctypes.c_void_p

# Create pipeline
config = obs_pipeline_config_t()
dll.obs_pipeline_get_default_config(ctypes.byref(config))
pipeline = dll.obs_pipeline_create(ctypes.byref(config))

# Process audio
audio_buffer = obs_audio_buffer_t()
# ... setup audio_buffer ...
dll.obs_pipeline_process(pipeline, ctypes.byref(audio_buffer))
```

## Performance Notes

- **RNNoise**: Yêu cầu 48kHz sample rate, xử lý theo frames 480 samples (10ms)
- **Latency**: ~10-20ms tùy thuộc vào buffer size và số lượng filters
- **CPU Usage**: RNNoise sử dụng ~5-10% CPU trên modern processors

## Troubleshooting

### "Noise Suppress not supported"
- Kiểm tra `LIBRNNOISE_ENABLED` đã được định nghĩa trong build
- Đảm bảo RNNoise source code có sẵn trong `../obs-studio/plugins/obs-filters/rnnoise/`

### Python script không tìm thấy DLL
- Đảm bảo `obs-mic-filter.dll` có trong directory hiện tại hoặc `build-win64/`
- Kiểm tra architecture (32-bit vs 64-bit)

### Audio processing failures
- Đảm bảo sample rate = 48000Hz cho RNNoise
- Kiểm tra audio buffer format (planar float32)
- Verify channel count matches pipeline configuration

## License

Dựa trên OBS Studio (GPL v2) và RNNoise (BSD 3-Clause).