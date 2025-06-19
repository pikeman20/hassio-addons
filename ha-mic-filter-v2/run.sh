#!/bin/bash

set -e

export PULSE_SERVER=unix:/run/audio/pulse.sock

echo "[INFO] Waiting for PulseAudio to be ready..."
sleep 5

CONFIG=/data/options.json

# Helper: get value or default
get_cfg() { jq -r --arg k "$1" --arg d "$2" '.[$k] // $d' "$CONFIG"; }

VIRTUAL_MIC_NAME=$(get_cfg "virtual_mic_name" "HA_Filtered_Mic")
MONITOR_TO_SPEAKERS=$(get_cfg "monitor_to_speakers" "false")
SAMPLE_RATE=$(get_cfg "sample_rate" "48000")
CHANNELS=$(get_cfg "channels" "1")

# Create virtual sink for filtered mic
echo "[INFO] Creating virtual sink: $VIRTUAL_MIC_NAME"
pactl load-module module-null-sink sink_name="$VIRTUAL_MIC_NAME" sink_properties=device.description="$VIRTUAL_MIC_NAME"

# Build filter chain
FILTER_CHAIN=""

# Noise suppression (rnnoise LADSPA)
if [ "$(get_cfg "noise_suppression_enabled" "false")" = "true" ] && [ "$(get_cfg "noise_suppression_method" "rnnoise")" = "rnnoise" ]; then
  FILTER_CHAIN="$FILTER_CHAIN ladspa-rnnoise.so:Rnnoise"
fi

# Gain
if [ "$(get_cfg "gain_enabled" "false")" = "true" ]; then
  GAIN_DB=$(get_cfg "gain_db" "0")
  FILTER_CHAIN="$FILTER_CHAIN audioamplify amplification=$(awk "BEGIN {print 10^($GAIN_DB/20)}")"
fi

# 3-band EQ
if [ "$(get_cfg "equalizer_enabled" "false")" = "true" ]; then
  LOW=$(get_cfg "equalizer_low_db" "0")
  MID=$(get_cfg "equalizer_mid_db" "0")
  HIGH=$(get_cfg "equalizer_high_db" "0")
  FILTER_CHAIN="$FILTER_CHAIN equalizer-3bands band0=$LOW band1=$MID band2=$HIGH"
fi

# Expander
if [ "$(get_cfg "expander_enabled" "false")" = "true" ]; then
  RATIO=$(get_cfg "expander_ratio" "1")
  THRESH=$(get_cfg "expander_threshold" "-60")
  ATTACK=$(get_cfg "expander_attack_time" "1")
  RELEASE=$(get_cfg "expander_release_time" "75")
  GAIN=$(get_cfg "expander_output_gain" "0")
  FILTER_CHAIN="$FILTER_CHAIN audioexpander ratio=$RATIO threshold=$THRESH attack=$ATTACK release=$RELEASE makeup-gain=$GAIN"
fi

# Compressor
if [ "$(get_cfg "compressor_enabled" "false")" = "true" ]; then
  RATIO=$(get_cfg "compressor_ratio" "1")
  THRESH=$(get_cfg "compressor_threshold" "-10")
  ATTACK=$(get_cfg "compressor_attack_time" "1")
  RELEASE=$(get_cfg "compressor_release_time" "75")
  GAIN=$(get_cfg "compressor_output_gain" "0")
  FILTER_CHAIN="$FILTER_CHAIN audiocompressor ratio=$RATIO threshold=$THRESH attack=$ATTACK release=$RELEASE makeup-gain=$GAIN"
fi

# Limiter
if [ "$(get_cfg "limiter_enabled" "false")" = "true" ]; then
  THRESH=$(get_cfg "limiter_threshold" "-0.2")
  RELEASE=$(get_cfg "limiter_release_time" "60")
  FILTER_CHAIN="$FILTER_CHAIN audiolimiter threshold=$THRESH release=$RELEASE"
fi

# Compose pipeline
PIPELINE="pulsesrc device=default ! audioresample ! audio/x-raw,rate=$SAMPLE_RATE,channels=$CHANNELS $FILTER_CHAIN ! pulsesink device=$VIRTUAL_MIC_NAME"

# Monitor to speakers if enabled
if [ "$MONITOR_TO_SPEAKERS" = "true" ]; then
  PIPELINE="pulsesrc device=default ! audioresample ! audio/x-raw,rate=$SAMPLE_RATE,channels=$CHANNELS $FILTER_CHAIN tee name=t t. ! queue ! pulsesink device=$VIRTUAL_MIC_NAME t. ! queue ! pulsesink"
  echo "[INFO] Output will be routed to both virtual mic and speakers"
fi

echo "[INFO] Launching GStreamer pipeline: $PIPELINE"
exec gst-launch-1.0 $PIPELINE