#ifndef FILTER_WRAPPER_COMPRESSOR_H
#define FILTER_WRAPPER_COMPRESSOR_H

#include "obs_pipeline.h"

#ifdef __cplusplus
extern "C" {
#endif

// Compressor filter parameters
typedef struct {
    float ratio;
    float threshold;
    float attack_time;
    float release_time;
    float output_gain;
} compressor_filter_params_t;

void* filter_wrapper_compressor_create(const obs_pipeline_config_t* config);
void filter_wrapper_compressor_destroy(void* filter_data);
obs_pipeline_result_t filter_wrapper_compressor_update(void* filter_data, const compressor_filter_params_t* params);
obs_pipeline_result_t filter_wrapper_compressor_process(void* filter_data, obs_audio_buffer_t* audio);
void filter_wrapper_compressor_reset(void* filter_data);

#ifdef __cplusplus
}
#endif

#endif // FILTER_WRAPPER_COMPRESSOR_H