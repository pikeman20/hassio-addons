#include "filter_wrapper_expander.h"
#include "memory_utils.h"
#include "audio_utils.h"
#include <math.h>
#include <string.h>

#define MAX_CHANNELS 8

typedef struct {
    obs_pipeline_config_t config;
    float ratio;
    float threshold;
    float attack_time;
    float release_time;
    float output_gain;
    float knee_width;
    obs_expander_detect_t detector;
    obs_expander_preset_t preset;

    // DSP state
    float *envelope_buf[MAX_CHANNELS];
    size_t envelope_buf_len;
    float *runaverage[MAX_CHANNELS];
    size_t runaverage_len;
    float *env_in;
    size_t env_in_len;
    float *gain_db[MAX_CHANNELS];
    size_t gain_db_len;
    float envelope[MAX_CHANNELS];
    float runave[MAX_CHANNELS];
    float gain_db_buf[MAX_CHANNELS];

    // Cached params
    float attack_coeff;
    float release_coeff;
    float slope;
} expander_filter_data_t;

static void resize_buffer(float **buf, size_t *len, size_t new_len) {
    if (*len != new_len) {
        float *new_buf = obs_realloc(*buf, new_len * sizeof(float));
        if (!new_buf) return;
        *buf = new_buf;
        *len = new_len;
    }
}

static void resize_channel_buffers(float **bufs, size_t *len, size_t new_len, int channels) {
    for (int i = 0; i < channels; ++i) {
        float *new_buf = obs_realloc(bufs[i], new_len * sizeof(float));
        if (!new_buf) continue;
        bufs[i] = new_buf;
    }
    *len = new_len;
}

static float gain_coefficient(float sample_rate, float time_ms) {
    return expf(-1.0f / (sample_rate * (time_ms / 1000.0f)));
}

void* filter_wrapper_expander_create(const obs_pipeline_config_t* config)
{
    if (!config) return NULL;

    expander_filter_data_t* data = obs_calloc(sizeof(expander_filter_data_t));
    if (!data) return NULL;

    data->config = *config;
    data->ratio = 2.0f;
    data->threshold = -30.0f;
    data->attack_time = 10.0f;
    data->release_time = 50.0f;
    data->output_gain = 0.0f;
    data->knee_width = 1.0f;
    data->detector = OBS_EXPANDER_DETECT_RMS;
    data->preset = OBS_EXPANDER_PRESET_EXPANDER;

    data->envelope_buf_len = 0;
    data->runaverage_len = 0;
    data->env_in_len = 0;
    data->gain_db_len = 0;
    data->env_in = NULL;

    for (int i = 0; i < MAX_CHANNELS; ++i) {
        data->envelope_buf[i] = NULL;
        data->runaverage[i] = NULL;
        data->gain_db[i] = NULL;
        data->envelope[i] = 0.0f;
        data->runave[i] = 0.0f;
        data->gain_db_buf[i] = 0.0f;
    }

    // Precompute coefficients
    float sr = (float)config->sample_rate;
    data->attack_coeff = gain_coefficient(sr, data->attack_time);
    data->release_coeff = gain_coefficient(sr, data->release_time);
    data->slope = 1.0f - data->ratio;

    return data;
}

void filter_wrapper_expander_destroy(void* filter_data)
{
    if (!filter_data) return;
    expander_filter_data_t* data = (expander_filter_data_t*)filter_data;
    for (int i = 0; i < MAX_CHANNELS; ++i) {
        obs_free(data->envelope_buf[i]);
        obs_free(data->runaverage[i]);
        obs_free(data->gain_db[i]);
    }
    obs_free(data->env_in);
    obs_free(data);
}

obs_pipeline_result_t filter_wrapper_expander_update(void* filter_data, const expander_filter_params_t* params)
{
    if (!filter_data || !params) return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    expander_filter_data_t* data = (expander_filter_data_t*)filter_data;

    data->ratio = params->ratio;
    data->threshold = params->threshold;
    data->attack_time = params->attack_time;
    data->release_time = params->release_time;
    data->output_gain = params->output_gain;
    data->knee_width = params->knee_width;
    data->detector = params->detector;
    data->preset = params->preset;

    float sr = (float)data->config.sample_rate;
    data->attack_coeff = gain_coefficient(sr, data->attack_time);
    data->release_coeff = gain_coefficient(sr, data->release_time);
    data->slope = 1.0f - data->ratio;

    return OBS_PIPELINE_SUCCESS;
}

static void analyze_envelope(expander_filter_data_t* data, float **samples, uint32_t num_samples, int channels)
{
    if (data->envelope_buf_len < num_samples)
        resize_channel_buffers(data->envelope_buf, &data->envelope_buf_len, num_samples, channels);
    if (data->runaverage_len < num_samples)
        resize_channel_buffers(data->runaverage, &data->runaverage_len, num_samples, channels);
    if (data->env_in_len < num_samples)
        resize_buffer(&data->env_in, &data->env_in_len, num_samples);

    float rmscoef = exp2f(-100.0f / data->config.sample_rate);

    for (int i = 0; i < channels; ++i) {
        memset(data->envelope_buf[i], 0, num_samples * sizeof(float));
        memset(data->runaverage[i], 0, num_samples * sizeof(float));
    }
    memset(data->env_in, 0, num_samples * sizeof(float));

    for (int chan = 0; chan < channels; ++chan) {
        if (!samples[chan]) continue;
        float *envelope_buf = data->envelope_buf[chan];
        float *runave = data->runaverage[chan];
        float *env_in = data->env_in;

        if (data->detector == OBS_EXPANDER_DETECT_RMS) {
            runave[0] = rmscoef * data->runave[chan] + (1 - rmscoef) * samples[chan][0] * samples[chan][0];
            env_in[0] = sqrtf(fmaxf(runave[0], 0));
            for (uint32_t i = 1; i < num_samples; ++i) {
                runave[i] = rmscoef * runave[i - 1] + (1 - rmscoef) * samples[chan][i] * samples[chan][i];
                env_in[i] = sqrtf(runave[i]);
            }
        } else {
            for (uint32_t i = 0; i < num_samples; ++i) {
                runave[i] = samples[chan][i] * samples[chan][i];
                env_in[i] = fabsf(samples[chan][i]);
            }
        }

        data->runave[chan] = runave[num_samples - 1];
        for (uint32_t i = 0; i < num_samples; ++i)
            envelope_buf[i] = fmaxf(envelope_buf[i], env_in[i]);
        data->envelope[chan] = envelope_buf[num_samples - 1];
    }
}

static inline float db_to_mul(float db) {
    return powf(10.0f, db / 20.0f);
}

static inline float mul_to_db(float mul) {
    if (mul <= 0.000001f) return -120.0f;
    return 20.0f * log10f(mul);
}

static void process_expansion(expander_filter_data_t* data, float **samples, uint32_t num_samples, int channels)
{
    if (data->gain_db_len < num_samples)
        resize_channel_buffers(data->gain_db, &data->gain_db_len, num_samples, channels);

    for (int i = 0; i < channels; ++i)
        memset(data->gain_db[i], 0, num_samples * sizeof(float));

    float attack_gain = data->attack_coeff;
    float release_gain = data->release_coeff;
    float inv_attack_gain = 1.0f - attack_gain;
    float inv_release_gain = 1.0f - release_gain;
    float threshold = data->threshold;
    float slope = data->slope;
    float output_gain = db_to_mul(data->output_gain);
    float knee = data->knee_width;

    for (int chan = 0; chan < channels; ++chan) {
        float *channel_samples = samples[chan];
        float *env_buf = data->envelope_buf[chan];
        float *gain_db = data->gain_db[chan];
        float channel_gain = data->gain_db_buf[chan];

        for (uint32_t i = 0; i < num_samples; ++i) {
            float env_db = mul_to_db(env_buf[i]);
            float diff = threshold - env_db;
            float gain = 0.0f;
            float prev_gain = i > 0 ? gain_db[i - 1] : channel_gain;

            gain = diff > 0.0f ? fmaxf(slope * diff, -60.0f) : 0.0f;

            // Ballistics
            if (gain > prev_gain)
                gain_db[i] = attack_gain * prev_gain + inv_attack_gain * gain;
            else
                gain_db[i] = release_gain * prev_gain + inv_release_gain * gain;

            // Output
            float out_gain = db_to_mul(fminf(0, gain_db[i]));
            channel_samples[i] *= out_gain * output_gain;
        }
        data->gain_db_buf[chan] = gain_db[num_samples - 1];
    }
}

obs_pipeline_result_t filter_wrapper_expander_process(void* filter_data, obs_audio_buffer_t* audio)
{
    if (!filter_data || !audio) return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    expander_filter_data_t* data = (expander_filter_data_t*)filter_data;

    int channels = data->config.channels;
    uint32_t num_samples = audio->frames;
    if (!audio_buffer_validate(audio, channels, data->config.sample_rate))
        return OBS_PIPELINE_ERROR_UNSUPPORTED_FORMAT;

    float **samples = (float **)audio->data;
    analyze_envelope(data, samples, num_samples, channels);
    process_expansion(data, samples, num_samples, channels);

    return OBS_PIPELINE_SUCCESS;
}

void filter_wrapper_expander_reset(void* filter_data)
{
    if (!filter_data) return;
    expander_filter_data_t* data = (expander_filter_data_t*)filter_data;
    for (int i = 0; i < MAX_CHANNELS; ++i) {
        data->envelope[i] = 0.0f;
        data->runave[i] = 0.0f;
        data->gain_db_buf[i] = 0.0f;
    }
}