#ifndef FILTER_WRAPPER_GAIN_H
#define FILTER_WRAPPER_GAIN_H

#include "obs_pipeline.h"

#ifdef __cplusplus
extern "C" {
#endif

// Gain filter parameters structure
typedef struct {
    float gain_db;
} gain_filter_params_t;

/**
 * Create a gain filter instance
 * @param config Pipeline configuration
 * @return Filter instance or NULL on failure
 */
void* filter_wrapper_gain_create(const obs_pipeline_config_t* config);

/**
 * Destroy a gain filter instance
 * @param filter_data Filter instance
 */
void filter_wrapper_gain_destroy(void* filter_data);

/**
 * Update gain filter parameters
 * @param filter_data Filter instance
 * @param params Filter parameters
 * @return Result code
 */
obs_pipeline_result_t filter_wrapper_gain_update(void* filter_data, const gain_filter_params_t* params);

/**
 * Process audio through gain filter
 * @param filter_data Filter instance
 * @param audio Audio buffer to process
 * @return Result code
 */
obs_pipeline_result_t filter_wrapper_gain_process(void* filter_data, obs_audio_buffer_t* audio);

/**
 * Reset gain filter state
 * @param filter_data Filter instance
 */
void filter_wrapper_gain_reset(void* filter_data);

#ifdef __cplusplus
}
#endif

#endif // FILTER_WRAPPER_GAIN_H