#ifndef FILTER_WRAPPER_VST_H
#define FILTER_WRAPPER_VST_H

#include "../include/obs_pipeline.h"

#ifdef __cplusplus
extern "C" {
#endif

// VST 2.x filter parameters
typedef struct {
    char plugin_path[512];    // Path to VST plugin (.dll/.so/.vst)
    int program_number;       // VST program/preset number
    float parameters[128];    // VST parameter values (0.0-1.0)
    int parameter_count;      // Number of parameters used
    char chunk_data[8192];    // VST state data (base64 encoded)
} vst_filter_params_t;

// VST filter wrapper functions
void* filter_wrapper_vst_create(const obs_pipeline_config_t* config);
void filter_wrapper_vst_destroy(void* filter_data);
obs_pipeline_result_t filter_wrapper_vst_update(void* filter_data, const vst_filter_params_t* params);
obs_pipeline_result_t filter_wrapper_vst_process(void* filter_data, obs_audio_buffer_t* audio);
void filter_wrapper_vst_reset(void* filter_data);

// VST-specific functions
obs_pipeline_result_t filter_wrapper_vst_load_plugin(void* filter_data, const char* plugin_path);
obs_pipeline_result_t filter_wrapper_vst_set_parameter(void* filter_data, int index, float value);
float filter_wrapper_vst_get_parameter(void* filter_data, int index);
obs_pipeline_result_t filter_wrapper_vst_set_program(void* filter_data, int program);
int filter_wrapper_vst_get_program(void* filter_data);
bool filter_wrapper_vst_has_editor(void* filter_data);

#ifdef __cplusplus
}
#endif

#endif // FILTER_WRAPPER_VST_H