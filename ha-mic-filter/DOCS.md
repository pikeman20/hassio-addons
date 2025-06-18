# Configuration

The Real-time Microphone Filter addon enhances your Home Assistant Assist experience by providing professional-grade audio processing for your microphone input. This creates a virtual microphone device that Home Assistant Assist can use for improved voice recognition.

## Basic Configuration

### Audio Device Settings

- **Input Device**: Select the physical microphone device by name or description. Leave null to auto-detect. You can use device names like "alsa_input.usb-Blue_Microphones_Yeti_Stereo_Microphone" or friendly descriptions like "Blue Yeti Microphone".
- **Output Device**: Select the output device by name or description (typically the virtual microphone). Leave null to auto-detect.
- **Monitoring Device**: Optional device for monitoring the filtered audio output by name or description.
- **Virtual Mic Name**: Name for the virtual microphone device (default: "HA_Filtered_Mic").

### Audio Parameters

- **Sample Rate**: Audio sample rate in Hz. Higher values provide better quality but use more CPU (default: 48000).
- **Channels**: Number of audio channels. Use 1 for mono, 2 for stereo (default: 1).
- **Buffer Size**: Audio buffer size in milliseconds. Lower values reduce latency but may cause audio dropouts (default: 10).

### Service Settings

- **Auto Start**: Automatically start audio filtering when the addon starts.
- **Log Level**: Set logging verbosity (debug, info, warning, error).

## Audio Pipeline Configuration

The addon features a sophisticated audio processing pipeline with multiple filter stages. Each filter can be individually enabled or disabled and fine-tuned for your environment.

### Noise Suppression

Advanced AI-powered noise suppression to remove background noise while preserving voice quality.

- **Enabled**: Enable or disable noise suppression
- **Method**: Choose the algorithm:
  - `rnnoise`: AI-powered noise suppression (recommended)
  - `speex`: Traditional spectral subtraction
  - `nvafx_denoiser`: NVIDIA RTX voice denoiser (requires compatible hardware)
  - `nvafx_dereverb`: NVIDIA RTX voice dereverb
  - `nvafx_both`: Combined NVIDIA RTX processing
- **Intensity**: Control suppression strength (0.0 to 1.0, default: 0.8)
- **Suppress Level**: Noise suppression threshold in dB (default: -30)

### Gain Control

Adjust the overall input level to optimize for your microphone and environment.

- **Enabled**: Enable or disable gain adjustment
- **Gain (dB)**: Boost or cut the signal level in decibels (default: 10.5)

### 3-Band Equalizer

Shape the frequency response to enhance voice clarity and reduce unwanted frequencies.

- **Enabled**: Enable or disable equalizer processing
- **Low Band (dB)**: Adjust low frequencies (typically 80-250 Hz, default: 10.0)
- **Mid Band (dB)**: Adjust mid frequencies (typically 250-4000 Hz, default: -20.0)
- **High Band (dB)**: Adjust high frequencies (typically 4000-16000 Hz, default: 12.5)

### Expander/Gate

Reduce background noise during quiet periods while preserving natural speech dynamics.

- **Enabled**: Enable or disable expander processing
- **Ratio**: Expansion ratio (default: 4.0)
- **Threshold (dB)**: Level below which expansion occurs (default: -55.0)
- **Attack Time (ms)**: How quickly the expander responds (default: 1.0)
- **Release Time (ms)**: How quickly the expander recovers (default: 75.0)
- **Output Gain (dB)**: Additional gain after expansion (default: 2.0)

### Compressor

Control dynamic range to ensure consistent voice levels and prevent sudden volume spikes.

- **Enabled**: Enable or disable compressor processing
- **Ratio**: Compression ratio (default: 4.0)
- **Threshold (dB)**: Level above which compression occurs (default: -7.0)
- **Attack Time (ms)**: How quickly the compressor responds (default: 1.0)
- **Release Time (ms)**: How quickly the compressor recovers (default: 75.0)
- **Output Gain (dB)**: Makeup gain after compression (default: 0.0)

### Limiter

Prevent audio clipping and protect against sudden loud sounds.

- **Enabled**: Enable or disable limiter processing
- **Threshold (dB)**: Maximum output level (default: -0.2)
- **Release Time (ms)**: How quickly the limiter recovers (default: 60.0)

## Getting Started

1. **Install the Addon**: Add this addon to your Home Assistant and install it.

2. **Initial Setup**: Start with the default configuration and enable auto-start.

3. **Test Audio**: Check the addon logs to verify your microphone is detected and the virtual microphone is created.

4. **Configure Home Assistant Assist**: In Home Assistant, go to Settings > Voice Assistants and select the virtual microphone ("HA_Filtered_Mic") as the input device.

5. **Fine-tune Settings**: Adjust the audio pipeline parameters based on your environment and preferences.

## Tips for Optimal Performance

### For Noisy Environments
- Increase noise suppression intensity to 0.9
- Lower the expander threshold to -45 dB
- Reduce low-frequency EQ to -5 dB

### For Quiet Environments
- Reduce noise suppression intensity to 0.5
- Increase expander threshold to -65 dB
- Boost mid-frequency EQ to 5 dB

### For Distant Microphones
- Increase gain to 15-20 dB
- Enable aggressive noise suppression
- Use higher compression ratio (6:1 or 8:1)

### For Close Microphones
- Reduce gain to 5-10 dB
- Use gentle compression (2:1 or 3:1)
- Enable limiter to prevent clipping

## Device Selection

You can now specify audio devices using:

1. **Device Names**: Exact PulseAudio device names (e.g., "alsa_input.usb-Blue_Microphones_Yeti")
2. **Device Descriptions**: Friendly device descriptions (e.g., "Blue Yeti Microphone")
3. **Partial Matches**: Case-insensitive partial matches (e.g., "Blue Yeti" will match "Blue Yeti Microphone")
4. **Device IDs**: Legacy numeric IDs are still supported for backward compatibility

### Finding Device Names

To find available device names, check the addon logs when it starts - it will list all detected audio devices with their names and descriptions.

## Troubleshooting

### Virtual Microphone Not Available
- Check that the addon is running
- Verify PulseAudio is working properly
- Restart the addon and check logs

### Device Not Found
- Check addon logs for list of available devices
- Verify device name or description spelling
- Try using partial device name matches
- Ensure device is properly connected and recognized by the system

### Poor Audio Quality
- Ensure sample rate matches your microphone
- Check for audio dropouts in logs
- Increase buffer size if experiencing glitches

### High CPU Usage
- Disable unused filters
- Increase buffer size
- Consider reducing sample rate to 44100 Hz

### No Audio Input Detected
- Verify microphone is connected and working
- Check device permissions
- Review addon logs for device detection
- Try using device description instead of device name

For more detailed troubleshooting, enable debug logging and check the addon logs for specific error messages.