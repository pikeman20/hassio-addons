#ifndef FILTER_WRAPPER_EXPANDER_H
#define FILTER_WRAPPER_EXPANDER_H

#include "obs_pipeline.h"

#ifdef __cplusplus
extern "C" {
#endif

// Expander filter parameters
typedef struct {
    float ratio;
    float threshold;
    float attack_time;
    float release_time;
    float output_gain;
    float knee_width;
    obs_expander_detect_t detector;
    obs_expander_preset_t preset;
} expander_filter_params_t;

void* filter_wrapper_expander_create(const obs_pipeline_config_t* config);
void filter_wrapper_expander_destroy(void* filter_data);
obs_pipeline_result_t filter_wrapper_expander_update(void* filter_data, const expander_filter_params_t* params);
obs_pipeline_result_t filter_wrapper_expander_process(void* filter_data, obs_audio_buffer_t* audio);
void filter_wrapper_expander_reset(void* filter_data);

#ifdef __cplusplus
}
#endif

#endif // FILTER_WRAPPER_EXPANDER_H