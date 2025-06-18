#include "pipeline_manager.h"
#include "memory_utils.h"
#include "audio_utils.h"
#include "filter_wrapper_gain.h"
#include "filter_wrapper_noise_suppress.h"
#include "filter_wrapper_eq.h"
#include "filter_wrapper_compressor.h"
#include "filter_wrapper_expander.h"
#include <string.h>

// Maximum number of filters per pipeline
#define MAX_PIPELINE_FILTERS 32

// Filter instance structure
typedef struct {
    obs_filter_type_t type;
    bool enabled;
    bool allocated;
    void* filter_data;  // Filter-specific data
    uint64_t latency;   // Filter latency in nanoseconds
} filter_instance_t;

// Pipeline manager structure
struct pipeline_manager {
    obs_pipeline_config_t config;
    filter_instance_t filters[MAX_PIPELINE_FILTERS];
    uint32_t filter_count;
    uint64_t total_latency;
    
    // Working buffers for audio processing
    float** temp_buffers;
    uint32_t temp_buffer_frames;
};

struct pipeline_manager* pipeline_manager_create(const obs_pipeline_config_t* config)
{
    if (!config) {
        return NULL;
    }

    struct pipeline_manager* manager = obs_calloc(sizeof(struct pipeline_manager));
    if (!manager) {
        return NULL;
    }

    manager->config = *config;
    manager->filter_count = 0;
    manager->total_latency = 0;

    // Calculate buffer size for 10ms segments
    uint32_t frames_per_buffer = (config->sample_rate * config->buffer_size_ms) / 1000;
    manager->temp_buffer_frames = frames_per_buffer;

    // Allocate temporary buffers for processing
    manager->temp_buffers = obs_malloc(config->channels * sizeof(float*));
    if (!manager->temp_buffers) {
        obs_free(manager);
        return NULL;
    }

    for (uint32_t i = 0; i < config->channels; i++) {
        manager->temp_buffers[i] = obs_malloc(frames_per_buffer * sizeof(float));
        if (!manager->temp_buffers[i]) {
            // Cleanup on failure
            for (uint32_t j = 0; j < i; j++) {
                obs_free(manager->temp_buffers[j]);
            }
            obs_free(manager->temp_buffers);
            obs_free(manager);
            return NULL;
        }
    }

    return manager;
}

void pipeline_manager_destroy(struct pipeline_manager* manager)
{
    if (!manager) {
        return;
    }

    // Destroy all filters
    for (uint32_t i = 0; i < MAX_PIPELINE_FILTERS; i++) {
        if (manager->filters[i].allocated) {
            pipeline_manager_remove_filter(manager, i);
        }
    }

    // Free temporary buffers
    if (manager->temp_buffers) {
        for (uint32_t i = 0; i < manager->config.channels; i++) {
            obs_free(manager->temp_buffers[i]);
        }
        obs_free(manager->temp_buffers);
    }

    obs_free(manager);
}

obs_pipeline_result_t pipeline_manager_process(struct pipeline_manager* manager, obs_audio_buffer_t* audio)
{
    if (!manager || !audio) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    // Validate audio buffer
    if (!audio_buffer_validate(audio, manager->config.channels, manager->config.sample_rate)) {
        return OBS_PIPELINE_ERROR_UNSUPPORTED_FORMAT;
    }

    // Process through each enabled filter in order
    for (uint32_t i = 0; i < MAX_PIPELINE_FILTERS; i++) {
        filter_instance_t* filter = &manager->filters[i];
        
        if (!filter->allocated || !filter->enabled) {
            continue;
        }

        obs_pipeline_result_t result = OBS_PIPELINE_SUCCESS;

        // Call appropriate filter processing function based on type
        switch (filter->type) {
            case OBS_FILTER_GAIN:
                result = filter_wrapper_gain_process(filter->filter_data, audio);
                break;

            case OBS_FILTER_NOISE_SUPPRESS:
                result = filter_wrapper_noise_suppress_process(filter->filter_data, audio);
                break;

            case OBS_FILTER_EQUALIZER_3BAND:
                result = filter_wrapper_eq_process(filter->filter_data, audio);
                break;

            case OBS_FILTER_COMPRESSOR:
                result = filter_wrapper_compressor_process(filter->filter_data, audio);
                break;

            case OBS_FILTER_EXPANDER:
            case OBS_FILTER_UPWARD_COMPRESSOR:
                result = filter_wrapper_expander_process(filter->filter_data, audio);
                break;

            case OBS_FILTER_NOISE_GATE:
            case OBS_FILTER_LIMITER:
            case OBS_FILTER_INVERT_POLARITY:
                // TODO: Implement these filters
                result = OBS_PIPELINE_SUCCESS;
                break;

            default:
                result = OBS_PIPELINE_ERROR_INVALID_FILTER_TYPE;
                break;
        }

        if (result != OBS_PIPELINE_SUCCESS) {
            return result;
        }
    }

    return OBS_PIPELINE_SUCCESS;
}

obs_pipeline_result_t pipeline_manager_update_filter(struct pipeline_manager* manager, 
                                                     uint32_t filter_id, 
                                                     const obs_filter_params_t* params)
{
    if (!manager || !params || filter_id >= MAX_PIPELINE_FILTERS) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    filter_instance_t* filter = &manager->filters[filter_id];
    obs_pipeline_result_t result = OBS_PIPELINE_SUCCESS;

    // If filter exists and type changed, destroy it first
    if (filter->allocated && filter->type != params->type) {
        pipeline_manager_remove_filter(manager, filter_id);
    }

    // Create new filter if not allocated
    if (!filter->allocated) {
        switch (params->type) {
            case OBS_FILTER_GAIN:
                filter->filter_data = filter_wrapper_gain_create(&manager->config);
                break;

            case OBS_FILTER_NOISE_SUPPRESS:
                filter->filter_data = filter_wrapper_noise_suppress_create(&manager->config);
                break;

            case OBS_FILTER_EQUALIZER_3BAND:
                filter->filter_data = filter_wrapper_eq_create(&manager->config);
                break;

            case OBS_FILTER_COMPRESSOR:
                filter->filter_data = filter_wrapper_compressor_create(&manager->config);
                break;

            case OBS_FILTER_EXPANDER:
            case OBS_FILTER_UPWARD_COMPRESSOR:
                filter->filter_data = filter_wrapper_expander_create(&manager->config);
                break;

            default:
                return OBS_PIPELINE_ERROR_INVALID_FILTER_TYPE;
        }

        if (!filter->filter_data) {
            return OBS_PIPELINE_ERROR_INITIALIZATION_FAILED;
        }

        filter->type = params->type;
        filter->allocated = true;
        filter->latency = 0; // TODO: Calculate actual latency
        manager->filter_count++;
    }

    // Update filter parameters
    switch (params->type) {
        case OBS_FILTER_GAIN:
            result = filter_wrapper_gain_update(filter->filter_data, &params->params.gain);
            break;

        case OBS_FILTER_NOISE_SUPPRESS:
            result = filter_wrapper_noise_suppress_update(filter->filter_data, &params->params.noise_suppress);
            break;

        case OBS_FILTER_EQUALIZER_3BAND:
            result = filter_wrapper_eq_update(filter->filter_data, &params->params.equalizer_3band);
            break;

        case OBS_FILTER_COMPRESSOR:
            result = filter_wrapper_compressor_update(filter->filter_data, &params->params.compressor);
            break;

        case OBS_FILTER_EXPANDER:
        case OBS_FILTER_UPWARD_COMPRESSOR:
            result = filter_wrapper_expander_update(filter->filter_data, &params->params.expander);
            break;

        default:
            result = OBS_PIPELINE_ERROR_INVALID_FILTER_TYPE;
            break;
    }

    filter->enabled = params->enabled;
    
    // Recalculate total latency
    manager->total_latency = 0;
    for (uint32_t i = 0; i < MAX_PIPELINE_FILTERS; i++) {
        if (manager->filters[i].allocated && manager->filters[i].enabled) {
            manager->total_latency += manager->filters[i].latency;
        }
    }

    return result;
}

obs_pipeline_result_t pipeline_manager_remove_filter(struct pipeline_manager* manager, uint32_t filter_id)
{
    if (!manager || filter_id >= MAX_PIPELINE_FILTERS) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    filter_instance_t* filter = &manager->filters[filter_id];
    
    if (!filter->allocated) {
        return OBS_PIPELINE_ERROR_FILTER_NOT_FOUND;
    }

    // Destroy filter based on type
    switch (filter->type) {
        case OBS_FILTER_GAIN:
            filter_wrapper_gain_destroy(filter->filter_data);
            break;

        case OBS_FILTER_NOISE_SUPPRESS:
            filter_wrapper_noise_suppress_destroy(filter->filter_data);
            break;

        case OBS_FILTER_EQUALIZER_3BAND:
            filter_wrapper_eq_destroy(filter->filter_data);
            break;

        case OBS_FILTER_COMPRESSOR:
            filter_wrapper_compressor_destroy(filter->filter_data);
            break;

        case OBS_FILTER_EXPANDER:
        case OBS_FILTER_UPWARD_COMPRESSOR:
            filter_wrapper_expander_destroy(filter->filter_data);
            break;

        default:
            break;
    }

    // Clear filter instance
    memset(filter, 0, sizeof(filter_instance_t));
    manager->filter_count--;

    // Recalculate total latency
    manager->total_latency = 0;
    for (uint32_t i = 0; i < MAX_PIPELINE_FILTERS; i++) {
        if (manager->filters[i].allocated && manager->filters[i].enabled) {
            manager->total_latency += manager->filters[i].latency;
        }
    }

    return OBS_PIPELINE_SUCCESS;
}

uint64_t pipeline_manager_get_latency(struct pipeline_manager* manager)
{
    if (!manager) {
        return 0;
    }

    return manager->total_latency;
}

obs_pipeline_result_t pipeline_manager_reset(struct pipeline_manager* manager)
{
    if (!manager) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    // Reset each filter's state
    for (uint32_t i = 0; i < MAX_PIPELINE_FILTERS; i++) {
        filter_instance_t* filter = &manager->filters[i];
        
        if (!filter->allocated) {
            continue;
        }

        // Call reset function for each filter type
        switch (filter->type) {
            case OBS_FILTER_GAIN:
                filter_wrapper_gain_reset(filter->filter_data);
                break;

            case OBS_FILTER_NOISE_SUPPRESS:
                filter_wrapper_noise_suppress_reset(filter->filter_data);
                break;

            case OBS_FILTER_EQUALIZER_3BAND:
                filter_wrapper_eq_reset(filter->filter_data);
                break;

            case OBS_FILTER_COMPRESSOR:
                filter_wrapper_compressor_reset(filter->filter_data);
                break;

            case OBS_FILTER_EXPANDER:
            case OBS_FILTER_UPWARD_COMPRESSOR:
                filter_wrapper_expander_reset(filter->filter_data);
                break;

            default:
                break;
        }
    }

    return OBS_PIPELINE_SUCCESS;
}