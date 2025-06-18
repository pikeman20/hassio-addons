#ifndef PIPELINE_MANAGER_H
#define PIPELINE_MANAGER_H

#include "obs_pipeline.h"

#ifdef __cplusplus
extern "C" {
#endif

// Forward declaration
struct pipeline_manager;

/**
 * Create a pipeline manager instance
 * @param config Pipeline configuration
 * @return Pipeline manager handle or NULL on failure
 */
struct pipeline_manager* pipeline_manager_create(const obs_pipeline_config_t* config);

/**
 * Destroy a pipeline manager and free all resources
 * @param manager Pipeline manager handle
 */
void pipeline_manager_destroy(struct pipeline_manager* manager);

/**
 * Process audio through the filter pipeline
 * @param manager Pipeline manager handle
 * @param audio Audio buffer to process
 * @return Result code
 */
obs_pipeline_result_t pipeline_manager_process(struct pipeline_manager* manager, obs_audio_buffer_t* audio);

/**
 * Update or add a filter in the pipeline
 * @param manager Pipeline manager handle
 * @param filter_id Filter identifier
 * @param params Filter parameters
 * @return Result code
 */
obs_pipeline_result_t pipeline_manager_update_filter(struct pipeline_manager* manager, 
                                                     uint32_t filter_id, 
                                                     const obs_filter_params_t* params);

/**
 * Remove a filter from the pipeline
 * @param manager Pipeline manager handle
 * @param filter_id Filter identifier
 * @return Result code
 */
obs_pipeline_result_t pipeline_manager_remove_filter(struct pipeline_manager* manager, uint32_t filter_id);

/**
 * Get the total latency of the pipeline
 * @param manager Pipeline manager handle
 * @return Latency in nanoseconds
 */
uint64_t pipeline_manager_get_latency(struct pipeline_manager* manager);

/**
 * Reset the pipeline state
 * @param manager Pipeline manager handle
 * @return Result code
 */
obs_pipeline_result_t pipeline_manager_reset(struct pipeline_manager* manager);

#ifdef __cplusplus
}
#endif

#endif // PIPELINE_MANAGER_H