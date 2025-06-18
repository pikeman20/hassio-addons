# Home Assistant Add-on: Real-time Microphone Filter

Real-time microphone filtering for Home Assistant Assist using advanced audio processing techniques. Creates a virtual microphone device that applies professional-grade audio filters to enhance voice quality for voice assistants.

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]
![Supports armv7 Architecture][armv7-shield]

## About

This add-on provides real-time microphone filtering for Home Assistant Assist using advanced audio processing techniques. It creates a virtual microphone device that applies professional-grade audio filters to enhance voice quality for voice assistants.

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

1. Add the repository to your Home Assistant Add-on Store
2. Install the "Real-time Microphone Filter" add-on
3. Configure the add-on through the Configuration tab
4. Start the add-on

## Configuration

The add-on provides extensive configuration options for audio processing. Please refer to the **Documentation** tab for detailed configuration instructions.

### Basic Settings

- **Input Device**: The physical microphone device to use as input
- **Output Device**: The output device (usually the virtual microphone)
- **Virtual Mic Name**: Name for the virtual microphone device
- **Sample Rate**: Audio sample rate in Hz
- **Auto Start**: Automatically start filtering when add-on starts

### Audio Pipeline

Configure the comprehensive audio processing pipeline including:
- Noise suppression (RNNoise, Speex, NVIDIA RTX Voice)
- Gain control
- 3-band equalizer
- Expander/Gate
- Compressor
- Limiter

## Support

For issues and feature requests, please check the add-on logs and provide:
- Home Assistant version
- Add-on configuration
- Relevant log messages
- Audio device information

## License

This add-on is released under the Apache License 2.0.

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[armv7-shield]: https://img.shields.io/badge/armv7-yes-green.svg