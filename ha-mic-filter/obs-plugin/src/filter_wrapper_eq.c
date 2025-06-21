#include "filter_wrapper_eq.h"
#include "memory_utils.h"
#include "audio_utils.h"
#include <math.h>
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define LOW_FREQ 800.0f
#define HIGH_FREQ 5000.0f
#define EQ_EPSILON (1.0f / 4294967295.0f)

typedef struct {
    float lf_delay0;
    float lf_delay1;
    float lf_delay2;
    float lf_delay3;

    float hf_delay0;
    float hf_delay1;
    float hf_delay2;
    float hf_delay3;

    float sample_delay1;
    float sample_delay2;
    float sample_delay3;
} eq_channel_state_t;

// 3-Band EQ filter internal data structure
typedef struct {
    obs_pipeline_config_t config;
    float lf;
    float hf;
    float low_gain;
    float mid_gain;
    float high_gain;
    eq_channel_state_t* eqs; // Array of per-channel state
} eq_filter_data_t;


void* filter_wrapper_eq_create(const obs_pipeline_config_t* config)
{
    if (!config) {
        return NULL;
    }

    eq_filter_data_t* data = obs_calloc(sizeof(eq_filter_data_t));
    if (!data) {
        return NULL;
    }

    data->config = *config;
    data->low_gain = 1.0f;
    data->mid_gain = 1.0f;
    data->high_gain = 1.0f;

    int channels = config->channels;
    data->eqs = obs_calloc(sizeof(eq_channel_state_t) * channels);

    float freq = (float)config->sample_rate;
    data->lf = 2.0f * sinf((float)M_PI * LOW_FREQ / freq);
    data->hf = 2.0f * sinf((float)M_PI * HIGH_FREQ / freq);

    return data;
}

void filter_wrapper_eq_destroy(void* filter_data)
{
    if (filter_data) {
        eq_filter_data_t* data = (eq_filter_data_t*)filter_data;
        if (data->eqs) {
            obs_free(data->eqs);
        }
        obs_free(filter_data);
    }
}

obs_pipeline_result_t filter_wrapper_eq_update(void* filter_data, const eq_filter_params_t* params)
{
    if (!filter_data || !params) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    eq_filter_data_t* data = (eq_filter_data_t*)filter_data;

    data->low_gain = db_to_mul(params->low);
    data->mid_gain = db_to_mul(params->mid);
    data->high_gain = db_to_mul(params->high);

    // No need to update filter coefficients unless sample rate/freq changes

    return OBS_PIPELINE_SUCCESS;
}

static inline float eq_process(eq_filter_data_t* eq, eq_channel_state_t* c, float sample)
{
    float l, m, h;

    c->lf_delay0 += eq->lf * (sample - c->lf_delay0) + EQ_EPSILON;
    c->lf_delay1 += eq->lf * (c->lf_delay0 - c->lf_delay1);
    c->lf_delay2 += eq->lf * (c->lf_delay1 - c->lf_delay2);
    c->lf_delay3 += eq->lf * (c->lf_delay2 - c->lf_delay3);

    l = c->lf_delay3;

    c->hf_delay0 += eq->hf * (sample - c->hf_delay0) + EQ_EPSILON;
    c->hf_delay1 += eq->hf * (c->hf_delay0 - c->hf_delay1);
    c->hf_delay2 += eq->hf * (c->hf_delay1 - c->hf_delay2);
    c->hf_delay3 += eq->hf * (c->hf_delay2 - c->hf_delay3);

    h = c->sample_delay3 - c->hf_delay3;
    m = c->sample_delay3 - (h + l);

    l *= eq->low_gain;
    m *= eq->mid_gain;
    h *= eq->high_gain;

    c->sample_delay3 = c->sample_delay2;
    c->sample_delay2 = c->sample_delay1;
    c->sample_delay1 = sample;

    return l + m + h;
}

obs_pipeline_result_t filter_wrapper_eq_process(void* filter_data, obs_audio_buffer_t* audio)
{
    if (!filter_data || !audio) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    eq_filter_data_t* data = (eq_filter_data_t*)filter_data;

    if (!audio_buffer_validate(audio, data->config.channels, data->config.sample_rate)) {
        return OBS_PIPELINE_ERROR_UNSUPPORTED_FORMAT;
    }

    int channels = data->config.channels;
    uint32_t frames = audio->frames;

    for (int c = 0; c < channels; ++c) {
        float* adata = (float*)audio->data[c];
        eq_channel_state_t* channel = &data->eqs[c];

        for (uint32_t i = 0; i < frames; ++i) {
            adata[i] = eq_process(data, channel, adata[i]);
        }
    }

    return OBS_PIPELINE_SUCCESS;
}

void filter_wrapper_eq_reset(void* filter_data)
{
    if (!filter_data) {
        return;
    }
    eq_filter_data_t* data = (eq_filter_data_t*)filter_data;
    int channels = data->config.channels;
    for (int c = 0; c < channels; ++c) {
        memset(&data->eqs[c], 0, sizeof(eq_channel_state_t));
    }
}