#include "filter_wrapper_gain.h"
#include "memory_utils.h"
#include "audio_utils.h"

// Gain filter internal data structure
typedef struct {
    obs_pipeline_config_t config;
    float gain_multiplier;
} gain_filter_data_t;

void* filter_wrapper_gain_create(const obs_pipeline_config_t* config)
{
    if (!config) {
        return NULL;
    }

    gain_filter_data_t* data = obs_calloc(sizeof(gain_filter_data_t));
    if (!data) {
        return NULL;
    }

    data->config = *config;
    data->gain_multiplier = 1.0f; // 0 dB default

    return data;
}

void filter_wrapper_gain_destroy(void* filter_data)
{
    if (filter_data) {
        obs_free(filter_data);
    }
}

obs_pipeline_result_t filter_wrapper_gain_update(void* filter_data, const gain_filter_params_t* params)
{
    if (!filter_data || !params) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    gain_filter_data_t* data = (gain_filter_data_t*)filter_data;
    
    // Convert dB to linear multiplier
    data->gain_multiplier = db_to_mul(params->gain_db);

    return OBS_PIPELINE_SUCCESS;
}

obs_pipeline_result_t filter_wrapper_gain_process(void* filter_data, obs_audio_buffer_t* audio)
{
    if (!filter_data || !audio) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    gain_filter_data_t* data = (gain_filter_data_t*)filter_data;
    
    // Validate audio buffer
    if (!audio_buffer_validate(audio, data->config.channels, data->config.sample_rate)) {
        return OBS_PIPELINE_ERROR_UNSUPPORTED_FORMAT;
    }

    // Apply gain to each channel
    for (uint32_t c = 0; c < audio->channels; c++) {
        if (audio->data[c]) {
            for (uint32_t i = 0; i < audio->frames; i++) {
                audio->data[c][i] *= data->gain_multiplier;
            }
        }
    }

    return OBS_PIPELINE_SUCCESS;
}

void filter_wrapper_gain_reset(void* filter_data)
{
    // Gain filter has no internal state to reset
    (void)filter_data;
}