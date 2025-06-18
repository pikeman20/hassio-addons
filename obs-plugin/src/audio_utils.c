#include "audio_utils.h"
#include <math.h>
#include <string.h>

float db_to_mul(float db)
{
    return powf(10.0f, db / 20.0f);
}

float mul_to_db(float mul)
{
    if (mul <= 0.0f) {
        return -INFINITY;
    }
    return 20.0f * log10f(mul);
}

bool audio_buffer_validate(const obs_audio_buffer_t* audio, 
                          uint32_t expected_channels, 
                          uint32_t expected_sample_rate)
{
    if (!audio || !audio->data) {
        return false;
    }

    if (audio->frames == 0 || audio->channels == 0) {
        return false;
    }

    if (expected_channels > 0 && audio->channels != expected_channels) {
        return false;
    }

    if (expected_sample_rate > 0 && audio->sample_rate != expected_sample_rate) {
        return false;
    }

    // Check that all channel pointers are valid
    for (uint32_t i = 0; i < audio->channels; i++) {
        if (!audio->data[i]) {
            return false;
        }
    }

    return true;
}

void audio_buffer_copy(float** dst, float** src, uint32_t frames, uint32_t channels)
{
    if (!dst || !src || frames == 0 || channels == 0) {
        return;
    }

    for (uint32_t c = 0; c < channels; c++) {
        if (dst[c] && src[c]) {
            memcpy(dst[c], src[c], frames * sizeof(float));
        }
    }
}

void audio_buffer_clear(obs_audio_buffer_t* audio)
{
    if (!audio || !audio->data) {
        return;
    }

    for (uint32_t c = 0; c < audio->channels; c++) {
        if (audio->data[c]) {
            memset(audio->data[c], 0, audio->frames * sizeof(float));
        }
    }
}

float audio_calculate_rms(const float* data, uint32_t frames)
{
    if (!data || frames == 0) {
        return 0.0f;
    }

    double sum = 0.0;
    for (uint32_t i = 0; i < frames; i++) {
        double sample = (double)data[i];
        sum += sample * sample;
    }

    return (float)sqrt(sum / (double)frames);
}

float audio_calculate_peak(const float* data, uint32_t frames)
{
    if (!data || frames == 0) {
        return 0.0f;
    }

    float peak = 0.0f;
    for (uint32_t i = 0; i < frames; i++) {
        float abs_sample = fabsf(data[i]);
        if (abs_sample > peak) {
            peak = abs_sample;
        }
    }

    return peak;
}