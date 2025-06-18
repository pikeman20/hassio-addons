# Home Assistant Real-time Microphone Filter

This Home Assistant addon provides real-time microphone filtering for Home Assistant Assist using advanced audio processing techniques. It creates a virtual microphone device that applies professional-grade audio filters to enhance voice quality for voice assistants.

## Features

- **Real-time Audio Processing**: Advanced audio pipeline with multiple filter stages
- **Virtual Microphone Device**: Creates a PulseAudio virtual microphone for Home Assistant Assist
- **Professional Audio Filters**:
  - RNNoise AI-powered noise suppression
  - Multi-band equalizer (3-band)
  - Dynamic range compressor
  - Expander/Gate
  - Limiter
  - Gain control
- **Home Assistant Integration**: Seamless integration with Home Assistant OS
- **Persistent Configuration**: Settings are saved and restored between restarts

## Installation

1. Add this repository to your Home Assistant Add-on Store
2. Install the "Real-time Microphone Filter" addon
3. Configure the addon through the Configuration tab
4. Start the addon

## Configuration

### Basic Settings

- **Input Device ID**: The physical microphone device to use as input
- **Output Device ID**: The output device (usually the virtual microphone)
- **Monitoring Device ID**: Optional device for monitoring filtered audio
- **Virtual Mic Name**: Name for the virtual microphone device (default: "HA_Filtered_Mic")
- **Sample Rate**: Audio sample rate in Hz (default: 48000)
- **Channels**: Number of audio channels (default: 1 for mono)
- **Buffer Size**: Audio buffer size in milliseconds (default: 10)
- **Auto Start**: Automatically start filtering when addon starts
- **Log Level**: Logging verbosity (debug, info, warning, error)

### Audio Pipeline Configuration

The addon provides a comprehensive audio processing pipeline with the following filters:

#### Noise Suppression
- **Enabled**: Enable/disable noise suppression
- **Method**: Algorithm to use (speex, rnnoise, nvafx_denoiser, nvafx_dereverb, nvafx_both)
- **Intensity**: Suppression intensity (0.0 to 1.0)
- **Suppress Level**: Noise suppression level in dB

#### Gain Control
- **Enabled**: Enable/disable gain adjustment
- **Gain (dB)**: Gain adjustment in decibels

#### 3-Band Equalizer
- **Enabled**: Enable/disable equalizer
- **Low Band (dB)**: Low frequency adjustment
- **Mid Band (dB)**: Mid frequency adjustment
- **High Band (dB)**: High frequency adjustment

#### Expander/Gate
- **Enabled**: Enable/disable expander
- **Ratio**: Expansion ratio
- **Threshold (dB)**: Expansion threshold
- **Attack Time (ms)**: Attack time
- **Release Time (ms)**: Release time
- **Output Gain (dB)**: Output gain adjustment

#### Compressor
- **Enabled**: Enable/disable compressor
- **Ratio**: Compression ratio
- **Threshold (dB)**: Compression threshold
- **Attack Time (ms)**: Attack time
- **Release Time (ms)**: Release time
- **Output Gain (dB)**: Output gain adjustment

#### Limiter
- **Enabled**: Enable/disable limiter
- **Threshold (dB)**: Limiting threshold
- **Release Time (ms)**: Release time

## Usage

1. **Configure Audio Devices**: Set the input device ID to your physical microphone
2. **Adjust Pipeline Settings**: Tune the audio processing parameters for your environment
3. **Start the Addon**: Enable auto-start or manually start the filtering
4. **Configure Home Assistant Assist**: Set the virtual microphone as the input device for Assist

## Device Discovery

To find the correct device IDs:

1. Check the addon logs for available audio devices
2. Look for your microphone in the input devices list
3. Note the device ID number for configuration

## Troubleshooting

### Common Issues

**No Audio Devices Found**
- Ensure audio permissions are properly set
- Check that PulseAudio is running
- Verify audio devices are connected

**Virtual Microphone Not Created**
- Check addon logs for PulseAudio errors
- Ensure sufficient permissions
- Restart the addon

**Poor Audio Quality**
- Adjust noise suppression intensity
- Fine-tune equalizer settings
- Check sample rate compatibility

**High CPU Usage**
- Increase buffer size
- Disable unused filters
- Reduce sample rate if acceptable

### Log Analysis

Enable debug logging to see detailed information about:
- Audio device detection
- Pipeline initialization
- Real-time processing statistics
- Error conditions

## Technical Details

### Audio Pipeline Architecture

The addon uses a modular audio processing pipeline:

1. **Input Stage**: Captures audio from physical microphone
2. **Filter Chain**: Applies filters in sequence:
   - Noise Suppression
   - Gain Control
   - Equalizer
   - Expander
   - Compressor
   - Limiter
3. **Output Stage**: Sends processed audio to virtual microphone

### Virtual Device Creation

The addon creates PulseAudio virtual devices:
- **Virtual Sink**: Internal audio routing
- **Virtual Source**: The microphone device used by Home Assistant

### Performance Optimization

- Uses efficient C++ audio processing library
- Optimized buffer management
- Real-time priority scheduling
- Minimal latency design

## Support

For issues and feature requests, please check the addon logs and provide:
- Home Assistant version
- Addon configuration
- Relevant log messages
- Audio device information

## License

This addon is released under the Apache License 2.0.