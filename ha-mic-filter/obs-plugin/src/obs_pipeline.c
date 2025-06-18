#include "obs_pipeline.h"
#include "pipeline_manager.h"
#include "memory_utils.h"
#include "audio_utils.h"
#include <stdlib.h>
#include <string.h>

// Internal pipeline structure
struct obs_pipeline {
    obs_pipeline_config_t config;
    struct pipeline_manager* manager;
    bool initialized;
};

// Default configuration values
static const obs_pipeline_config_t default_config = {
    .sample_rate = 48000,
    .channels = 2,
    .buffer_size_ms = 10,
    .max_filters = 16
};

// Filter names for display
static const char* filter_names[OBS_FILTER_COUNT] = {
    [OBS_FILTER_GAIN] = "Gain",
    [OBS_FILTER_NOISE_SUPPRESS] = "Noise Suppression",
    [OBS_FILTER_NOISE_GATE] = "Noise Gate",
    [OBS_FILTER_COMPRESSOR] = "Compressor",
    [OBS_FILTER_LIMITER] = "Limiter",
    [OBS_FILTER_EXPANDER] = "Expander",
    [OBS_FILTER_UPWARD_COMPRESSOR] = "Upward Compressor",
    [OBS_FILTER_EQUALIZER_3BAND] = "3-Band Equalizer",
    [OBS_FILTER_INVERT_POLARITY] = "Invert Polarity"
};

obs_pipeline_t* obs_pipeline_create(const obs_pipeline_config_t* config)
{
    if (!config) {
        return NULL;
    }

    // Validate configuration
    if (config->sample_rate == 0 || config->channels == 0 || 
        config->channels > 8 || config->buffer_size_ms == 0 ||
        config->max_filters == 0) {
        return NULL;
    }

    obs_pipeline_t* pipeline = obs_malloc(sizeof(obs_pipeline_t));
    if (!pipeline) {
        return NULL;
    }

    // Copy configuration
    pipeline->config = *config;
    pipeline->initialized = false;

    // Create pipeline manager
    pipeline->manager = pipeline_manager_create(&pipeline->config);
    if (!pipeline->manager) {
        obs_free(pipeline);
        return NULL;
    }

    pipeline->initialized = true;
    return pipeline;
}

void obs_pipeline_destroy(obs_pipeline_t* pipeline)
{
    if (!pipeline) {
        return;
    }

    if (pipeline->manager) {
        pipeline_manager_destroy(pipeline->manager);
    }

    obs_free(pipeline);
}

obs_pipeline_result_t obs_pipeline_process(obs_pipeline_t* pipeline, obs_audio_buffer_t* audio)
{
    if (!pipeline || !audio || !pipeline->initialized) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    // Validate audio buffer
    if (!audio->data || audio->frames == 0 || audio->channels == 0) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    // Check if audio format matches pipeline configuration
    if (audio->channels != pipeline->config.channels ||
        audio->sample_rate != pipeline->config.sample_rate) {
        return OBS_PIPELINE_ERROR_UNSUPPORTED_FORMAT;
    }

    // Process through pipeline manager
    return pipeline_manager_process(pipeline->manager, audio);
}

obs_pipeline_result_t obs_pipeline_update_filter(obs_pipeline_t* pipeline, 
                                                 uint32_t filter_id, 
                                                 const obs_filter_params_t* params)
{
    if (!pipeline || !params || !pipeline->initialized) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    if (filter_id >= pipeline->config.max_filters) {
        return OBS_PIPELINE_ERROR_FILTER_NOT_FOUND;
    }

    if (params->type >= OBS_FILTER_COUNT) {
        return OBS_PIPELINE_ERROR_INVALID_FILTER_TYPE;
    }

    return pipeline_manager_update_filter(pipeline->manager, filter_id, params);
}

obs_pipeline_result_t obs_pipeline_remove_filter(obs_pipeline_t* pipeline, uint32_t filter_id)
{
    if (!pipeline || !pipeline->initialized) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    if (filter_id >= pipeline->config.max_filters) {
        return OBS_PIPELINE_ERROR_FILTER_NOT_FOUND;
    }

    return pipeline_manager_remove_filter(pipeline->manager, filter_id);
}

uint64_t obs_pipeline_get_latency(obs_pipeline_t* pipeline)
{
    if (!pipeline || !pipeline->initialized) {
        return 0;
    }

    return pipeline_manager_get_latency(pipeline->manager);
}

obs_pipeline_result_t obs_pipeline_reset(obs_pipeline_t* pipeline)
{
    if (!pipeline || !pipeline->initialized) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    return pipeline_manager_reset(pipeline->manager);
}

void obs_pipeline_get_default_config(obs_pipeline_config_t* config)
{
    if (config) {
        *config = default_config;
    }
}

obs_pipeline_result_t obs_pipeline_get_default_filter_params(obs_filter_type_t type, 
                                                            obs_filter_params_t* params)
{
    if (!params || type >= OBS_FILTER_COUNT) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    // Clear the structure first
    memset(params, 0, sizeof(obs_filter_params_t));
    
    params->type = type;
    params->enabled = true;

    // Set default parameters based on filter type
    switch (type) {
        case OBS_FILTER_GAIN:
            params->params.gain.gain_db = 0.0f;
            break;

        case OBS_FILTER_NOISE_SUPPRESS:
            params->params.noise_suppress.suppress_level = -30;
            params->params.noise_suppress.method = OBS_NOISE_SUPPRESS_RNNOISE;
            params->params.noise_suppress.intensity = 1.0f;
            break;

        case OBS_FILTER_NOISE_GATE:
            params->params.noise_gate.open_threshold = -26.0f;
            params->params.noise_gate.close_threshold = -32.0f;
            params->params.noise_gate.attack_time = 25;
            params->params.noise_gate.hold_time = 200;
            params->params.noise_gate.release_time = 150;
            break;

        case OBS_FILTER_COMPRESSOR:
            params->params.compressor.ratio = 10.0f;
            params->params.compressor.threshold = -18.0f;
            params->params.compressor.attack_time = 6.0f;
            params->params.compressor.release_time = 60.0f;
            params->params.compressor.output_gain = 0.0f;
            break;

        case OBS_FILTER_LIMITER:
            params->params.limiter.threshold = -6.0f;
            params->params.limiter.release_time = 60.0f;
            break;

        case OBS_FILTER_EXPANDER:
            params->params.expander.ratio = 2.0f;
            params->params.expander.threshold = -30.0f;
            params->params.expander.attack_time = 10.0f;
            params->params.expander.release_time = 50.0f;
            params->params.expander.output_gain = 0.0f;
            params->params.expander.knee_width = 1.0f;
            params->params.expander.detector = OBS_EXPANDER_DETECT_RMS;
            params->params.expander.preset = OBS_EXPANDER_PRESET_EXPANDER;
            break;

        case OBS_FILTER_UPWARD_COMPRESSOR:
            params->params.upward_compressor.ratio = 2.0f;
            params->params.upward_compressor.threshold = -30.0f;
            params->params.upward_compressor.attack_time = 10.0f;
            params->params.upward_compressor.release_time = 50.0f;
            params->params.upward_compressor.output_gain = 0.0f;
            break;

        case OBS_FILTER_EQUALIZER_3BAND:
            params->params.equalizer_3band.low = 0.0f;
            params->params.equalizer_3band.mid = 0.0f;
            params->params.equalizer_3band.high = 0.0f;
            break;

        case OBS_FILTER_INVERT_POLARITY:
            params->params.invert_polarity.invert = true;
            break;

        default:
            return OBS_PIPELINE_ERROR_INVALID_FILTER_TYPE;
    }

    return OBS_PIPELINE_SUCCESS;
}

bool obs_pipeline_is_filter_supported(obs_filter_type_t type)
{
    if (type >= OBS_FILTER_COUNT) {
        return false;
    }

    // Check for library dependencies
    switch (type) {
        case OBS_FILTER_NOISE_SUPPRESS:
#ifndef LIBRNNOISE_ENABLED
            return false;  // RNNoise not available
#endif
            break;

        default:
            break;
    }

    return true;
}

const char* obs_pipeline_get_filter_name(obs_filter_type_t type)
{
    if (type >= OBS_FILTER_COUNT) {
        return "Unknown";
    }

    return filter_names[type];
}