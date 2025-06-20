#!/bin/bash

set -x

CONFIG=/data/options.json

# Helper: get value or default
get_cfg() { jq -r --arg k "$1" --arg d "$2" '.[$k] // $d' "$CONFIG"; }

VIRTUAL_MIC_NAME=$(get_cfg "virtual_mic_name" "HA_Filtered_Mic")
MONITOR_TO_SPEAKERS=$(get_cfg "monitor_to_speakers" "false")
SAMPLE_RATE=$(get_cfg "sample_rate" "48000")
CHANNELS=$(get_cfg "channels" "1")

# Detect default PulseAudio source and sink from pactl info
DEFAULT_SOURCE=$(pactl info | grep "Default Source:" | awk -F': ' '{print $2}')
DEFAULT_SINK=$(pactl info | grep "Default Sink:" | awk -F': ' '{print $2}')
echo "[INFO] Default PulseAudio source: $DEFAULT_SOURCE"
echo "[INFO] Default PulseAudio sink: $DEFAULT_SINK"
pactl list sources short | grep "$DEFAULT_SOURCE" || echo "[WARN] Default source '$DEFAULT_SOURCE' not found in sources list"
pactl list sinks short | grep "$DEFAULT_SINK" || echo "[WARN] Default sink '$DEFAULT_SINK' not found in sinks list"

# Extract format for default source
SOURCE_FORMAT_LINE=$(pactl list sources short | grep "$DEFAULT_SOURCE" | head -n1)
SOURCE_SAMPLE=$(echo "$SOURCE_FORMAT_LINE" | awk '{print $4, $5, $6}')
SOURCE_FORMAT=$(echo "$SOURCE_SAMPLE" | awk '{print $1}')
SOURCE_CHANNELS=$(echo "$SOURCE_SAMPLE" | awk '{print $2}' | grep -o '[0-9]\+')
SOURCE_RATE=$(echo "$SOURCE_SAMPLE" | awk '{print $3}' | grep -o '[0-9]\+')

# Extract format for default sink
SINK_FORMAT_LINE=$(pactl list sinks short | grep "$DEFAULT_SINK" | head -n1)
SINK_SAMPLE=$(echo "$SINK_FORMAT_LINE" | awk '{print $4, $5, $6}')
SINK_FORMAT=$(echo "$SINK_SAMPLE" | awk '{print $1}')
SINK_CHANNELS=$(echo "$SINK_SAMPLE" | awk '{print $2}' | grep -o '[0-9]\+')
SINK_RATE=$(echo "$SINK_SAMPLE" | awk '{print $3}' | grep -o '[0-9]\+')

echo "[INFO] Default source format: $SOURCE_FORMAT, channels: $SOURCE_CHANNELS, rate: $SOURCE_RATE"
echo "[INFO] Default sink format: $SINK_FORMAT, channels: $SINK_CHANNELS, rate: $SINK_RATE"


# Set up PulseAudio environment
export PULSE_SERVER=unix:/run/audio/pulse.sock

# Wait for PulseAudio socket to be available
for i in {1..10}; do
  if pactl info > /dev/null 2>&1; then break; fi
  echo "[INFO] Waiting for PulseAudio..."
  sleep 1
done

if ! pactl info > /dev/null 2>&1; then
  echo "[ERROR] Cannot connect to PulseAudio."
  exit 1
fi

echo "[INFO] pactl info output:"
pactl info

# Print available PulseAudio sources (microphones) and sinks (speakers)
echo "[INFO] Available PulseAudio sources (microphones):"
pactl list sources short || true
echo "[INFO] Available PulseAudio sinks (speakers):"
pactl list sinks short || true

# Clean up any existing virtual devices
echo "[INFO] Cleaning up existing virtual devices..."
pactl unload-module module-null-sink 2>/dev/null || true
pactl unload-module module-virtual-source 2>/dev/null || true

# Create virtual sink for filtered mic
echo "[INFO] Creating virtual sink: $VIRTUAL_MIC_NAME with rate=$SAMPLE_RATE, channels=$CHANNELS"
if pactl load-module module-null-sink \
   sink_name=virtual_mic_sink \
   sink_properties="device.description='$VIRTUAL_MIC_NAME' rate=$SAMPLE_RATE channels=$CHANNELS"; then
    echo "[INFO] Virtual sink created successfully"
else
    echo "[ERROR] Failed to create virtual sink"
    exit 1
fi

# Create virtual source from the sink monitor
echo "[INFO] Creating virtual source..."
if pactl load-module module-virtual-source \
   source_name=virtual_mic \
   source_properties="device.description='$VIRTUAL_MIC_NAME' rate=$SAMPLE_RATE channels=$CHANNELS" \
   master=virtual_mic_sink.monitor; then
    echo "[INFO] Virtual source created successfully"
else
    echo "[ERROR] Failed to create virtual source"
    exit 1
fi

sleep 2

# Verify devices were created
if pactl list sinks short | grep -q virtual_mic_sink && pactl list sources short | grep -q virtual_mic; then
  echo "[INFO] Virtual microphone devices created successfully"
else
  echo "[ERROR] Virtual devices not found after creation"
  pactl list sinks short || true
  pactl list sources short || true
  exit 1
fi

# Cleanup on exit
cleanup() {
  echo "[INFO] Cleaning up virtual devices..."
  pactl unload-module module-null-sink 2>/dev/null || true
  pactl unload-module module-virtual-source 2>/dev/null || true
}
trap cleanup EXIT

# Check required GStreamer plugins
check_plugin() {
  if ! gst-inspect-1.0 "$1" > /dev/null 2>&1; then
    echo "[ERROR] GStreamer plugin $1 not found. Please install it."
    exit 1
  fi
}

# Build filter chain
FILTER_CHAIN=""

append_filter() {
  if [ -z "$FILTER_CHAIN" ]; then
    FILTER_CHAIN="$1"
  else
    FILTER_CHAIN="$FILTER_CHAIN ! $1"
  fi
}

# Noise suppression (rnnoise LADSPA)
if [ "$(get_cfg "noise_suppression_enabled" "false")" = "true" ] && [ "$(get_cfg "noise_suppression_method" "rnnoise")" = "rnnoise" ]; then
  append_filter "ladspa-librnnoise-ladspa-so-noise-suppressor-mono"
fi

# Gain
if [ "$(get_cfg "gain_enabled" "false")" = "true" ]; then
  GAIN_DB=$(get_cfg "gain_db" "0")
  if [ "$(awk "BEGIN {print ($GAIN_DB > 70)}")" -eq 1 ]; then
    GAIN_DB=70
  elif [ "$(awk "BEGIN {print ($GAIN_DB < -70)}")" -eq 1 ]; then
    GAIN_DB=-70
  fi
  append_filter "ladspa-amp-1181-so-amp amps-gain=$GAIN_DB"
fi

# 3-band EQ
if [ "$(get_cfg "equalizer_enabled" "false")" = "true" ]; then
  LOW_GAIN=$(get_cfg "equalizer_low_db" "0")
  MID_GAIN=$(get_cfg "equalizer_mid_db" "0")
  HIGH_GAIN=$(get_cfg "equalizer_high_db" "0")
  LOW_GAIN=$(awk "BEGIN {if ($LOW_GAIN < -70) print -70; else if ($LOW_GAIN > 30) print 30; else print $LOW_GAIN}")
  MID_GAIN=$(awk "BEGIN {if ($MID_GAIN < -70) print -70; else if ($MID_GAIN > 30) print 30; else print $MID_GAIN}")
  HIGH_GAIN=$(awk "BEGIN {if ($HIGH_GAIN < -70) print -70; else if ($HIGH_GAIN > 30) print 30; else print $HIGH_GAIN}")
  append_filter "ladspa-mbeq-1197-so-mbeq \
    param-50hz-gain=$LOW_GAIN \
    param-100hz-gain=$LOW_GAIN \
    param-156hz-gain=$LOW_GAIN \
    param-220hz-gain=$LOW_GAIN \
    param-311hz-gain=$LOW_GAIN \
    param-440hz-gain=$LOW_GAIN \
    param-622hz-gain=$LOW_GAIN \
    param-880hz-gain=$MID_GAIN \
    param-1250hz-gain=$MID_GAIN \
    param-1750hz-gain=$MID_GAIN \
    param-2500hz-gain=$MID_GAIN \
    param-3500hz-gain=$MID_GAIN \
    param-5000hz-gain=$HIGH_GAIN \
    param-10000hz-gain=$HIGH_GAIN \
    param-20000hz-gain=$HIGH_GAIN"
fi

# Expander
if [ "$(get_cfg "expander_enabled" "false")" = "true" ]; then
  EXPANDER_RATIO=$(get_cfg "expander_ratio" "4.0")
  EXPANDER_THRESHOLD_DB=$(get_cfg "expander_threshold" "-55.0")
  EXPANDER_ATTACK=$(get_cfg "expander_attack_time" "4.0")
  EXPANDER_RELEASE=$(get_cfg "expander_release_time" "75.0")
  EXPANDER_GAIN_DB=$(get_cfg "expander_output_gain" "2.0")
  EXPANDER_THRESHOLD=$(awk "BEGIN {val = 10^($EXPANDER_THRESHOLD_DB / 20); if (val < 0.001) print 0.001; else if (val > 1) print 1; else print val}")
  EXPANDER_GAIN=$(awk "BEGIN {val = 10^($EXPANDER_GAIN_DB / 20); if (val < 0.001) print 0.001; else if (val > 1000) print 1000; else print val}")
  EXPANDER_RATIO=$(awk "BEGIN {if ($EXPANDER_RATIO < 1) print 1; else if ($EXPANDER_RATIO > 100) print 100; else print $EXPANDER_RATIO}")
  EXPANDER_ATTACK=$(awk "BEGIN {if ($EXPANDER_ATTACK < 0) print 0; else if ($EXPANDER_ATTACK > 2000) print 2000; else print $EXPANDER_ATTACK}")
  EXPANDER_RELEASE=$(awk "BEGIN {if ($EXPANDER_RELEASE < 0) print 0; else if ($EXPANDER_RELEASE > 5000) print 5000; else print $EXPANDER_RELEASE}")
  append_filter "ladspa-lsp-plugins-ladspa-1-2-5-so-http---lsp-plug-in-plugins-ladspa-expander-mono \
    attack-threshold=$EXPANDER_THRESHOLD \
    attack-time=$EXPANDER_ATTACK \
    release-time=$EXPANDER_RELEASE \
    ratio=$EXPANDER_RATIO \
    makeup-gain=$EXPANDER_GAIN"
fi

# Compressor
if [ "$(get_cfg "compressor_enabled" "false")" = "true" ]; then
  COMPRESSOR_RATIO=$(get_cfg "compressor_ratio" "1")
  COMPRESSOR_THRESHOLD=$(get_cfg "compressor_threshold" "-10")
  COMPRESSOR_ATTACK=$(get_cfg "compressor_attack_time" "1")
  COMPRESSOR_RELEASE=$(get_cfg "compressor_release_time" "75")
  COMPRESSOR_GAIN=$(get_cfg "compressor_output_gain" "0")
  COMPRESSOR_THRESHOLD=$(awk "BEGIN {if ($COMPRESSOR_THRESHOLD < -30) print -30; else if ($COMPRESSOR_THRESHOLD > 0) print 0; else print $COMPRESSOR_THRESHOLD}")
  COMPRESSOR_RATIO=$(awk "BEGIN {if ($COMPRESSOR_RATIO < 1) print 1; else if ($COMPRESSOR_RATIO > 20) print 20; else print $COMPRESSOR_RATIO}")
  COMPRESSOR_ATTACK=$(awk "BEGIN {if ($COMPRESSOR_ATTACK < 1.5) print 1.5; else if ($COMPRESSOR_ATTACK > 400) print 400; else print $COMPRESSOR_ATTACK}")
  COMPRESSOR_RELEASE=$(awk "BEGIN {if ($COMPRESSOR_RELEASE < 2) print 2; else if ($COMPRESSOR_RELEASE > 800) print 800; else print $COMPRESSOR_RELEASE}")
  COMPRESSOR_GAIN=$(awk "BEGIN {if ($COMPRESSOR_GAIN < 0) print 0; else if ($COMPRESSOR_GAIN > 24) print 24; else print $COMPRESSOR_GAIN}")
  append_filter "ladspa-sc4m-1916-so-sc4m \
    threshold-level=$COMPRESSOR_THRESHOLD \
    ratio=$COMPRESSOR_RATIO \
    attack-time=$COMPRESSOR_ATTACK \
    release-time=$COMPRESSOR_RELEASE \
    makeup-gain=$COMPRESSOR_GAIN"
fi

# Limiter - requires 2 channels input. Outputs 2 channels.
# Always convert to 2 channels BEFORE the limiter, and convert back to main CHANNELS after if needed.
if [ "$(get_cfg "limiter_enabled" "false")" = "true" ]; then
  THRESH=$(get_cfg "limiter_threshold" "-0.2")
  RELEASE_MS=$(get_cfg "limiter_release_time" "60")
  RELEASE_S=$(awk "BEGIN {print $RELEASE_MS / 1000}")
  RELEASE_S=$(awk "BEGIN {if ($RELEASE_S > 2) print 2; else if ($RELEASE_S < 0.01) print 0.01; else print $RELEASE_S}")
  THRESH=$(awk "BEGIN {if ($THRESH < -20) print -20; else if ($THRESH > 0) print 0; else print $THRESH}")

  # Convert to 2 channels for the limiter, regardless of CURRENT_CHANNELS
  append_filter "audioconvert ! audio/x-raw,channels=2"
  
  append_filter "ladspa-fast-lookahead-limiter-1913-so-fastlookaheadlimiter limit=$THRESH release-time=$RELEASE_S"
  
  # Convert back to the desired CHANNELS (from config) after the limiter, if it's not 2.
  if [ "$CHANNELS" -ne 2 ]; then
    append_filter "audioconvert ! audio/x-raw,channels=$CHANNELS"
  fi
fi

# --- Compose the full GStreamer pipeline ---

# Start with the actual source format and rate, then convert to the desired pipeline format
PIPELINE="pulsesrc device=$DEFAULT_SOURCE ! audioconvert ! audioresample ! audio/x-raw,rate=$SAMPLE_RATE,channels=$CHANNELS"

# Add all collected filters
if [ -n "$FILTER_CHAIN" ]; then
  PIPELINE="$PIPELINE ! $FILTER_CHAIN"
fi

# Handle monitoring to speakers or direct output to virtual mic
if [ "$MONITOR_TO_SPEAKERS" = "true" ]; then
  # Tee splits the main processed stream. The stream coming here is at $SAMPLE_RATE, $CHANNELS
  PIPELINE="$PIPELINE ! tee name=t"

  # Branch for Virtual Mic: always outputs to the configured SAMPLE_RATE and CHANNELS
  # No need for extra audioconvert/audioresample if the pipeline is already in desired format
  # unless s16le format is strictly required by the null-sink, which is often the case.
  PIPELINE="$PIPELINE t. ! queue ! audioconvert ! audioresample ! audio/x-raw,format=s16le,rate=$SAMPLE_RATE,channels=$CHANNELS ! pulsesink device=$VIRTUAL_MIC_NAME"

  # Branch for Physical Speakers: converts to native sink format
  PIPELINE="$PIPELINE t. ! queue ! audioconvert ! audioresample ! audio/x-raw,format=$SINK_FORMAT,rate=$SINK_RATE,channels=$SINK_CHANNELS ! pulsesink device=$DEFAULT_SINK"

  echo "[INFO] Output will be routed to both virtual mic and speakers"
else
  # If not monitoring to speakers, output directly to virtual mic
  # Ensure format is s16le, rate=$SAMPLE_RATE, channels=$CHANNELS for virtual mic
  PIPELINE="$PIPELINE ! audioconvert ! audioresample ! audio/x-raw,format=s16le,rate=$SAMPLE_RATE,channels=$CHANNELS ! pulsesink device=$VIRTUAL_MIC_NAME"
fi

echo "[INFO] Launching GStreamer pipeline: $PIPELINE"
exec gst-launch-1.0 $PIPELINE