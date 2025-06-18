"""
Device naming constants for Home Assistant Microphone Filter
Ensures consistent device names across PulseAudio config and Python code
"""

# Virtual microphone device names (these are INTERNAL names, fixed)
VIRTUAL_MIC_SINK_NAME = "virtual_mic_sink"
VIRTUAL_MIC_SOURCE_NAME = "virtual_mic"

# Default descriptions (these can be overridden by user config)
DEFAULT_VIRTUAL_MIC_DESCRIPTION = "HA_Filtered_Microphone"
DEFAULT_VIRTUAL_SINK_DESCRIPTION = "Virtual_Microphone_Sink"

# PulseAudio socket paths
PULSE_EXTERNAL_SOCKET = "/tmp/pulse-external-socket"
PULSE_CONFIG_PATH = "/tmp/pulse-config"