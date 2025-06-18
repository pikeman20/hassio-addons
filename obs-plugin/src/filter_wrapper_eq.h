#ifndef FILTER_WRAPPER_EQ_H
#define FILTER_WRAPPER_EQ_H

#include "obs_pipeline.h"

#ifdef __cplusplus
extern "C" {
#endif

// 3-Band EQ filter parameters
typedef struct {
    float low;
    float mid;
    float high;
} eq_filter_params_t;

void* filter_wrapper_eq_create(const obs_pipeline_config_t* config);
void filter_wrapper_eq_destroy(void* filter_data);
obs_pipeline_result_t filter_wrapper_eq_update(void* filter_data, const eq_filter_params_t* params);
obs_pipeline_result_t filter_wrapper_eq_process(void* filter_data, obs_audio_buffer_t* audio);
void filter_wrapper_eq_reset(void* filter_data);

#ifdef __cplusplus
}
#endif

#endif // FILTER_WRAPPER_EQ_H