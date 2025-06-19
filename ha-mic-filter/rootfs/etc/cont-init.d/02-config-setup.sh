#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Community Add-on: Real-time Microphone Filter
# Setup configuration from Home Assistant options
# ==============================================================================

bashio::log.info "Setting up configuration from Home Assistant..."

# Read configuration from Home Assistant options
declare input_device
declare output_device
declare monitoring_device
declare virtual_mic_name
declare sample_rate
declare channels
declare buffer_size_ms
declare auto_start
declare log_level
declare monitor_to_speakers

input_device=$(bashio::config 'input_device')
output_device=$(bashio::config 'output_device')
monitoring_device=$(bashio::config 'monitoring_device')
virtual_mic_name=$(bashio::config 'virtual_mic_name')
sample_rate=$(bashio::config 'sample_rate')
channels=$(bashio::config 'channels')
buffer_size_ms=$(bashio::config 'buffer_size_ms')
auto_start=$(bashio::config 'auto_start')
log_level=$(bashio::config 'log_level')
monitor_to_speakers=$(bashio::config 'monitor_to_speakers')

# Set environment variables for the Python service
export INPUT_DEVICE="${input_device}"
export OUTPUT_DEVICE="${output_device}"
export MONITORING_DEVICE="${monitoring_device}"
export VIRTUAL_MIC_NAME="${virtual_mic_name}"
export SAMPLE_RATE="${sample_rate}"
export CHANNELS="${channels}"
export BUFFER_SIZE_MS="${buffer_size_ms}"
export AUTO_START="${auto_start}"
export LOG_LEVEL="${log_level^^}"
export MONITOR_TO_SPEAKERS="${monitor_to_speakers}"

# Make the MONITOR_TO_SPEAKERS available for the PulseAudio setup script
echo "export MONITOR_TO_SPEAKERS=\"${monitor_to_speakers}\"" >> /etc/profile

# Read audio pipeline configuration
declare noise_suppression_enabled
declare noise_suppression_method
declare noise_suppression_intensity
declare noise_suppression_suppress_level

noise_suppression_enabled=$(bashio::config 'noise_suppression_enabled')
noise_suppression_method=$(bashio::config 'noise_suppression_method')
noise_suppression_intensity=$(bashio::config 'noise_suppression_intensity')
noise_suppression_suppress_level=$(bashio::config 'noise_suppression_suppress_level')

export NOISE_SUPPRESSION_ENABLED="${noise_suppression_enabled}"
export NOISE_SUPPRESSION_METHOD="${noise_suppression_method}"
export NOISE_SUPPRESSION_INTENSITY="${noise_suppression_intensity}"
export NOISE_SUPPRESSION_SUPPRESS_LEVEL="${noise_suppression_suppress_level}"

# Continue for other filters...
declare gain_enabled
declare gain_db

gain_enabled=$(bashio::config 'gain_enabled')
gain_db=$(bashio::config 'gain_db')

export GAIN_ENABLED="${gain_enabled}"
export GAIN_DB="${gain_db}"

declare eq_enabled
declare eq_low_db
declare eq_mid_db
declare eq_high_db

eq_enabled=$(bashio::config 'equalizer_enabled')
eq_low_db=$(bashio::config 'equalizer_low_db')
eq_mid_db=$(bashio::config 'equalizer_mid_db')
eq_high_db=$(bashio::config 'equalizer_high_db')

export EQ_ENABLED="${eq_enabled}"
export EQ_LOW_DB="${eq_low_db}"
export EQ_MID_DB="${eq_mid_db}"
export EQ_HIGH_DB="${eq_high_db}"

declare exp_enabled
declare exp_ratio
declare exp_threshold
declare exp_attack_time
declare exp_release_time
declare exp_output_gain

exp_enabled=$(bashio::config 'expander_enabled')
exp_ratio=$(bashio::config 'expander_ratio')
exp_threshold=$(bashio::config 'expander_threshold')
exp_attack_time=$(bashio::config 'expander_attack_time')
exp_release_time=$(bashio::config 'expander_release_time')
exp_output_gain=$(bashio::config 'expander_output_gain')

export EXP_ENABLED="${exp_enabled}"
export EXP_RATIO="${exp_ratio}"
export EXP_THRESHOLD="${exp_threshold}"
export EXP_ATTACK_TIME="${exp_attack_time}"
export EXP_RELEASE_TIME="${exp_release_time}"
export EXP_OUTPUT_GAIN="${exp_output_gain}"

declare comp_enabled
declare comp_ratio
declare comp_threshold
declare comp_attack_time
declare comp_release_time
declare comp_output_gain

comp_enabled=$(bashio::config 'compressor_enabled')
comp_ratio=$(bashio::config 'compressor_ratio')
comp_threshold=$(bashio::config 'compressor_threshold')
comp_attack_time=$(bashio::config 'compressor_attack_time')
comp_release_time=$(bashio::config 'compressor_release_time')
comp_output_gain=$(bashio::config 'compressor_output_gain')

export COMP_ENABLED="${comp_enabled}"
export COMP_RATIO="${comp_ratio}"
export COMP_THRESHOLD="${comp_threshold}"
export COMP_ATTACK_TIME="${comp_attack_time}"
export COMP_RELEASE_TIME="${comp_release_time}"
export COMP_OUTPUT_GAIN="${comp_output_gain}"

declare lim_enabled
declare lim_threshold
declare lim_release_time

lim_enabled=$(bashio::config 'limiter_enabled')
lim_threshold=$(bashio::config 'limiter_threshold')
lim_release_time=$(bashio::config 'limiter_release_time')

export LIM_ENABLED="${lim_enabled}"
export LIM_THRESHOLD="${lim_threshold}"
export LIM_RELEASE_TIME="${lim_release_time}"

bashio::log.info "Configuration environment variables set successfully"
bashio::log.info "Virtual microphone name: ${virtual_mic_name}"
bashio::log.info "Sample rate: ${sample_rate}Hz, Channels: ${channels}"
bashio::log.info "Auto-start: ${auto_start}"