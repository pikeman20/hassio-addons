#!/bin/bash

set -e
export PULSE_SERVER='unix:/run/audio/pulse.sock'

# No need for bc, using awk for floating-point math and comparisons

# Đợi PulseAudio sẵn sàng
for i in {1..10}; do
  if pactl info > /dev/null 2>&1; then break; fi
  echo "[INFO] Waiting for PulseAudio..."
  sleep 1
done

if ! pactl info > /dev/null 2>&1; then
  echo "[ERROR] Cannot connect to PulseAudio."
  exit 1
fi

CONFIG=/data/options.json

# Helper: get value or default
get_cfg() { jq -r --arg k "$1" --arg d "$2" '.[$k] // $d' "$CONFIG"; }

VIRTUAL_MIC_NAME=$(get_cfg "virtual_mic_name" "HA_Filtered_Mic")
MONITOR_TO_SPEAKERS=$(get_cfg "monitor_to_speakers" "false")
SAMPLE_RATE=$(get_cfg "sample_rate" "48000")
CHANNELS=$(get_cfg "channels" "1")

# Create virtual sink for filtered mic
echo "[INFO] Creating virtual sink: HA_Filtered_Mic"
pacmd load-module module-null-sink sink_name=HA_Filtered_Mic sink_properties=device.description="HA_Filtered_Mic" > /dev/null
if [ $? -eq 0 ]; then
    MODULE_ID=$(pacmd list-modules | grep -B 1 "sink_name: HA_Filtered_Mic" | head -n 1 | awk '{print $2}')
    echo "[INFO] Loaded null-sink with module ID $MODULE_ID"
else
    echo "[ERROR] Failed to load null-sink module. It might already exist or there's a PulseAudio issue."
    exit 1
fi

sleep 2

# Cleanup khi thoát
cleanup() {
  echo "[INFO] Cleaning up sink $MODULE_ID..."
  pactl unload-module "$MODULE_ID"
}
trap cleanup EXIT

# Kiểm tra plugin GStreamer
check_plugin() {
  if ! gst-inspect-1.0 "$1" > /dev/null 2>&1; then
    echo "[ERROR] GStreamer plugin $1 not found. Please install it."
    exit 1
  fi
}

# Kiểm tra plugin LADSPA
check_ladspa_plugin() {
  local plugin_label="$1"
  if ! gst-inspect-1.0 ladspa | grep -q "$plugin_label"; then
    echo "[ERROR] LADSPA plugin $plugin_label not found. Please install it."
    exit 1
  fi
}

# Kiểm tra các plugin cần thiết
check_plugin pulsesrc
check_plugin audioresample
check_plugin pulsesink
check_plugin ladspa
check_ladspa_plugin "noise-suppressor-mono"
check_ladspa_plugin "mbeq"
check_ladspa_plugin "sc4"
check_ladspa_plugin "fastlookaheadlimiter"

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

# Gain (sử dụng ladspa-amp-1181-so-amp thay thế volume)
if [ "$(get_cfg "gain_enabled" "false")" = "true" ]; then
  GAIN_DB=$(get_cfg "gain_db" "0")
  # Kiểm tra và giới hạn GAIN_DB trong phạm vi [-70, 70]
  if [ "$(awk "BEGIN {print ($GAIN_DB > 70)}")" -eq 1 ]; then
      GAIN_DB=70
  elif [ "$(awk "BEGIN {print ($GAIN_DB < -70)}")" -eq 1 ]; then
      GAIN_DB=-70
  fi
  append_filter "ladspa-amp-1181-so-amp amps-gain=$GAIN_DB"
fi

# 3-band EQ (sử dụng multiband_eq từ swh-plugins)
if [ "$(get_cfg "equalizer_enabled" "false")" = "true" ]; then
  LOW_GAIN=$(get_cfg "equalizer_low_db" "0")
  MID_GAIN=$(get_cfg "equalizer_mid_db" "0")
  HIGH_GAIN=$(get_cfg "equalizer_high_db" "0")

  # Clamp values to the LADSPA plugin's range: -70 to 30 dB
  LOW_GAIN=$(awk "BEGIN {if ($LOW_GAIN < -70) print -70; else if ($LOW_GAIN > 30) print 30; else print $LOW_GAIN}")
  MID_GAIN=$(awk "BEGIN {if ($MID_GAIN < -70) print -70; else if ($MID_GAIN > 30) print 30; else print $MID_GAIN}")
  HIGH_GAIN=$(awk "BEGIN {if ($HIGH_GAIN < -70) print -70; else if ($HIGH_GAIN > 30) print 30; else print $HIGH_GAIN}")

  # Construct the LADSPA filter string
  # Assign LOW_GAIN to frequencies below or around 800Hz
  # Assign MID_GAIN to frequencies between 800Hz and 5000Hz
  # Assign HIGH_GAIN to frequencies above 5000Hz

  # Note: The 'ladspa-mbeq-1197-so-mbeq' plugin actually has 15 bands, not 10,
  # based on the gst-inspect-1.0 output.
  # We will map them to approximate your 3-band logic.
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

# Expander (sử dụng lsp-plugins-expander-mono)
if [ "$(get_cfg "expander_enabled" "false")" = "true" ]; then
  # Lấy giá trị cấu hình
  EXPANDER_RATIO=$(get_cfg "expander_ratio" "4.0")
  EXPANDER_THRESHOLD_DB=$(get_cfg "expander_threshold" "-55.0") # Giữ lại là dB để dễ đọc
  EXPANDER_ATTACK=$(get_cfg "expander_attack_time" "4.0")
  EXPANDER_RELEASE=$(get_cfg "expander_release_time" "75.0")
  EXPANDER_GAIN_DB=$(get_cfg "expander_output_gain" "2.0") # Giữ lại là dB để dễ đọc

  # --- Chuyển đổi giá trị dB sang tuyến tính (linear gain) cho các tham số LSP Expander ---
  # LSP Expander sử dụng tỷ lệ tuyến tính cho threshold và gain.
  # Công thức: linear_gain = 10^(dB_value / 20)
  
  # Chuyển đổi Threshold từ dB sang linear (attack-threshold)
  # Phạm vi của attack-threshold là 0.001 - 1
  EXPANDER_THRESHOLD=$(awk "BEGIN {val = 10^($EXPANDER_THRESHOLD_DB / 20); if (val < 0.001) print 0.001; else if (val > 1) print 1; else print val}")
  
  # Chuyển đổi Makeup Gain từ dB sang linear (makeup-gain)
  # Phạm vi của makeup-gain là 0.001 - 1000
  EXPANDER_GAIN=$(awk "BEGIN {val = 10^($EXPANDER_GAIN_DB / 20); if (val < 0.001) print 0.001; else if (val > 1000) print 1000; else print val}")

  # --- Kẹp các giá trị khác vào phạm vi chấp nhận được của LSP Expander ---
  # ratio: 1 to 100
  EXPANDER_RATIO=$(awk "BEGIN {if ($EXPANDER_RATIO < 1) print 1; else if ($EXPANDER_RATIO > 100) print 100; else print $EXPANDER_RATIO}")

  # attack-time: 0 to 2000 ms
  EXPANDER_ATTACK=$(awk "BEGIN {if ($EXPANDER_ATTACK < 0) print 0; else if ($EXPANDER_ATTACK > 2000) print 2000; else print $EXPANDER_ATTACK}")

  # release-time: 0 to 5000 ms
  EXPANDER_RELEASE=$(awk "BEGIN {if ($EXPANDER_RELEASE < 0) print 0; else if ($EXPANDER_RELEASE > 5000) print 5000; else print $EXPANDER_RELEASE}")

  # Gán các giá trị đã lấy và kiểm tra vào plugin
  append_filter "ladspa-lsp-plugins-ladspa-1-2-5-so-http---lsp-plug-in-plugins-ladspa-expander-mono \
    attack-threshold=$EXPANDER_THRESHOLD \
    attack-time=$EXPANDER_ATTACK \
    release-time=$EXPANDER_RELEASE \
    ratio=$EXPANDER_RATIO \
    makeup-gain=$EXPANDER_GAIN"
fi

# Compressor (sử dụng sc4 từ swh-plugins)
if [ "$(get_cfg "compressor_enabled" "false")" = "true" ]; then
  # Lấy giá trị cấu hình
  COMPRESSOR_RATIO=$(get_cfg "compressor_ratio" "1")
  COMPRESSOR_THRESHOLD=$(get_cfg "compressor_threshold" "-10")
  COMPRESSOR_ATTACK=$(get_cfg "compressor_attack_time" "1")
  COMPRESSOR_RELEASE=$(get_cfg "compressor_release_time" "75")
  COMPRESSOR_GAIN=$(get_cfg "compressor_output_gain" "0")

  # Đảm bảo các giá trị nằm trong phạm vi chấp nhận được của plugin SC4m (phiên bản mono)
  # Dựa trên gst-inspect-1.0 ladspa-sc4m-1916-so-sc4m
  
  # threshold-level: -30 to 0 dB
  COMPRESSOR_THRESHOLD=$(awk "BEGIN {if ($COMPRESSOR_THRESHOLD < -30) print -30; else if ($COMPRESSOR_THRESHOLD > 0) print 0; else print $COMPRESSOR_THRESHOLD}")
  
  # ratio: 1 to 20
  COMPRESSOR_RATIO=$(awk "BEGIN {if ($COMPRESSOR_RATIO < 1) print 1; else if ($COMPRESSOR_RATIO > 20) print 20; else print $COMPRESSOR_RATIO}")
  
  # attack-time: 1.5 to 400 ms
  COMPRESSOR_ATTACK=$(awk "BEGIN {if ($COMPRESSOR_ATTACK < 1.5) print 1.5; else if ($COMPRESSOR_ATTACK > 400) print 400; else print $COMPRESSOR_ATTACK}")
  
  # release-time: 2 to 800 ms
  COMPRESSOR_RELEASE=$(awk "BEGIN {if ($COMPRESSOR_RELEASE < 2) print 2; else if ($COMPRESSOR_RELEASE > 800) print 800; else print $COMPRESSOR_RELEASE}")
  
  # makeup-gain: 0 to 24 dB
  COMPRESSOR_GAIN=$(awk "BEGIN {if ($COMPRESSOR_GAIN < 0) print 0; else if ($COMPRESSOR_GAIN > 24) print 24; else print $COMPRESSOR_GAIN}")

  # Gán các giá trị đã lấy và kiểm tra vào plugin
  # Cập nhật tên plugin từ ladspa-sc4-1882-so-sc4 thành ladspa-sc4m-1916-so-sc4m
  append_filter "ladspa-sc4m-1916-so-sc4m \
    threshold-level=$COMPRESSOR_THRESHOLD \
    ratio=$COMPRESSOR_RATIO \
    attack-time=$COMPRESSOR_ATTACK \
    release-time=$COMPRESSOR_RELEASE \
    makeup-gain=$COMPRESSOR_GAIN"
fi

# Limiter (sử dụng fastlookaheadlimiter từ swh-plugins)
if [ "$(get_cfg "limiter_enabled" "false")" = "true" ]; then
  THRESH=$(get_cfg "limiter_threshold" "-0.2")
  RELEASE_MS=$(get_cfg "limiter_release_time" "60")

  # Chuyển đổi RELEASE từ mili giây sang giây (như plugin yêu cầu)
  RELEASE_S=$(awk "BEGIN {print $RELEASE_MS / 1000}")

  # Kiểm tra và giới hạn RELEASE_S trong phạm vi của ladspa-fast-lookahead-limiter
  # release-time (s): Range: 0.01 - 2
  if [ "$(awk "BEGIN {print ($RELEASE_S > 2)}")" -eq 1 ]; then
      RELEASE_S=2
  elif [ "$(awk "BEGIN {print ($RELEASE_S < 0.01)}")" -eq 1 ]; then
      RELEASE_S=0.01
  fi

  # Đảm bảo THRESH nằm trong phạm vi của ladspa-fast-lookahead-limiter
  # limit (dB): Range: -20 - 0
  THRESH=$(awk "BEGIN {if ($THRESH < -20) print -20; else if ($THRESH > 0) print 0; else print $THRESH}")

  # Thêm bộ chuyển đổi kênh (audioconvert) trước limiter để đảm bảo tương thích
  # Sau đó, thêm Fast Lookahead Limiter với các tham số của bạn.
  append_filter "audioconvert ! audio/x-raw,channels=2 ! \
    ladspa-fast-lookahead-limiter-1913-so-fastlookaheadlimiter limit=$THRESH release-time=$RELEASE_S ! \
    audioconvert ! audio/x-raw,channels=1"
fi

# Compose pipeline
PIPELINE="pulsesrc device=default ! audioresample ! audio/x-raw,rate=$SAMPLE_RATE,channels=$CHANNELS"

if [ -n "$FILTER_CHAIN" ]; then
  PIPELINE="$PIPELINE ! $FILTER_CHAIN"
fi

PIPELINE="$PIPELINE ! pulsesink device=$VIRTUAL_MIC_NAME"

# Monitor to speakers if enabled
if [ "$MONITOR_TO_SPEAKERS" = "true" ]; then
  PIPELINE="pulsesrc device=default ! audioresample ! audio/x-raw,rate=$SAMPLE_RATE,channels=$CHANNELS"
  if [ -n "$FILTER_CHAIN" ]; then
    PIPELINE="$PIPELINE ! $FILTER_CHAIN"
  fi
  PIPELINE="$PIPELINE ! tee name=t t. ! queue ! pulsesink device=$VIRTUAL_MIC_NAME t. ! queue ! pulsesink"
  echo "[INFO] Output will be routed to both virtual mic and speakers"
fi

echo "[INFO] Launching GStreamer pipeline: $PIPELINE"
exec gst-launch-1.0 $PIPELINE