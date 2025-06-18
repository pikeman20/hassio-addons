#ifndef FILTER_WRAPPER_NOISE_SUPPRESS_H
#define FILTER_WRAPPER_NOISE_SUPPRESS_H

#include "obs_pipeline.h"

#ifdef __cplusplus
extern "C" {
#endif

// Noise suppression filter parameters
typedef struct {
    int suppress_level;
    obs_noise_suppress_method_t method;
    float intensity;
} noise_suppress_filter_params_t;

void* filter_wrapper_noise_suppress_create(const obs_pipeline_config_t* config);
void filter_wrapper_noise_suppress_destroy(void* filter_data);
obs_pipeline_result_t filter_wrapper_noise_suppress_update(void* filter_data, const noise_suppress_filter_params_t* params);
obs_pipeline_result_t filter_wrapper_noise_suppress_process(void* filter_data, obs_audio_buffer_t* audio);
void filter_wrapper_noise_suppress_reset(void* filter_data);

#ifdef __cplusplus
}
#endif

#endif // FILTER_WRAPPER_NOISE_SUPPRESS_H