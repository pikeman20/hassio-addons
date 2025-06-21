#include "filter_wrapper_compressor.h"
#include "memory_utils.h"
#include "audio_utils.h"
#include <math.h>
#include <string.h>

// Compressor filter internal data structure
typedef struct {
    obs_pipeline_config_t config;
    float ratio;
    float threshold;
    float attack_time;
    float release_time;
    float output_gain;

    // Envelope follower state
    float envelope;
    float attack_coeff;
    float release_coeff;
} compressor_filter_data_t;

static inline float db_to_mul(float db) {
    return powf(10.0f, db / 20.0f);
}

static inline float mul_to_db(float mul) {
    return 20.0f * log10f(mul + 1e-20f);
}

void* filter_wrapper_compressor_create(const obs_pipeline_config_t* config)
{
    if (!config) {
        return NULL;
    }

    compressor_filter_data_t* data = obs_calloc(sizeof(compressor_filter_data_t));
    if (!data) {
        return NULL;
    }

    data->config = *config;
    data->ratio = 10.0f;
    data->threshold = -18.0f;
    data->attack_time = 6.0f;
    data->release_time = 60.0f;
    data->output_gain = 0.0f;

    // Initialize envelope state
    data->envelope = 0.0f;
    float sample_rate = (float)data->config.sample_rate;
    data->attack_coeff = expf(-1.0f / (sample_rate * (data->attack_time / 1000.0f)));
    data->release_coeff = expf(-1.0f / (sample_rate * (data->release_time / 1000.0f)));

    return data;
}

void filter_wrapper_compressor_destroy(void* filter_data)
{
    if (filter_data) {
        obs_free(filter_data);
    }
}

obs_pipeline_result_t filter_wrapper_compressor_update(void* filter_data, const compressor_filter_params_t* params)
{
    if (!filter_data || !params) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    compressor_filter_data_t* data = (compressor_filter_data_t*)filter_data;

    data->ratio = params->ratio;
    data->threshold = params->threshold;
    data->attack_time = params->attack_time;
    data->release_time = params->release_time;
    data->output_gain = params->output_gain;

    // Update attack/release coefficients if times changed
    float sample_rate = (float)data->config.sample_rate;
    data->attack_coeff = expf(-1.0f / (sample_rate * (data->attack_time / 1000.0f)));
    data->release_coeff = expf(-1.0f / (sample_rate * (data->release_time / 1000.0f)));

    return OBS_PIPELINE_SUCCESS;
}

obs_pipeline_result_t filter_wrapper_compressor_process(void* filter_data, obs_audio_buffer_t* audio)
{
    if (!filter_data || !audio) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    compressor_filter_data_t* data = (compressor_filter_data_t*)filter_data;

    // Validate audio buffer
    if (!audio_buffer_validate(audio, data->config.channels, data->config.sample_rate)) {
        return OBS_PIPELINE_ERROR_UNSUPPORTED_FORMAT;
    }

    float threshold_db = data->threshold;
    float ratio = data->ratio;
    float slope = 1.0f - (1.0f / ratio);
    float output_gain = db_to_mul(data->output_gain);

    // OBS-style: compute max envelope across all channels for each sample
    size_t channels = audio->channels;
    size_t frames = audio->frames;
    float* max_envelope_buf = (float*)alloca(sizeof(float) * frames);
    memset(max_envelope_buf, 0, sizeof(float) * frames);

    // Envelope analysis (OBS logic)
    for (size_t c = 0; c < channels; ++c) {
        float* buf = audio->data[c];
        if (!buf) continue;
        float env = data->envelope;
        for (size_t i = 0; i < frames; ++i) {
            float in = fabsf(buf[i]);
            if (env < in)
                env = in + data->attack_coeff * (env - in);
            else
                env = in + data->release_coeff * (env - in);
            if (env > max_envelope_buf[i])
                max_envelope_buf[i] = env;
        }
        data->envelope = env;
    }

    // Apply gain reduction using max envelope (OBS logic)
    for (size_t c = 0; c < channels; ++c) {
        float* buf = audio->data[c];
        if (!buf) continue;
        for (size_t i = 0; i < frames; ++i) {
            float env_db = mul_to_db(max_envelope_buf[i]);
            float gain_db = slope * (threshold_db - env_db);
            float gain = db_to_mul(fminf(0.0f, gain_db));
            buf[i] *= gain * output_gain;
        }
    }

    return OBS_PIPELINE_SUCCESS;
}

void filter_wrapper_compressor_reset(void* filter_data)
{
    if (!filter_data) {
        return;
    }
    compressor_filter_data_t* data = (compressor_filter_data_t*)filter_data;
    data->envelope = 0.0f;
}