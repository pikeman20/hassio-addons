#ifndef OBS_PIPELINE_H
#define OBS_PIPELINE_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Export/Import macros for Windows DLL
#ifdef _WIN32
    #ifdef OBS_MIC_FILTER_EXPORTS
        #define OBS_MIC_FILTER_API __declspec(dllexport)
    #else
        #define OBS_MIC_FILTER_API __declspec(dllimport)
    #endif
#else
    #define OBS_MIC_FILTER_API __attribute__((visibility("default")))
#endif

// Forward declarations
typedef struct obs_pipeline obs_pipeline_t;

// Audio data structure - abstracts OBS obs_audio_data
typedef struct {
    float **data;           // Planar float buffers, one per channel
    uint32_t frames;        // Number of frames per channel
    uint32_t channels;      // Number of audio channels
    uint32_t sample_rate;   // Sample rate in Hz
    uint64_t timestamp;     // Timestamp in nanoseconds
} obs_audio_buffer_t;

// Audio filter types available in the pipeline (based on OBS obs-filters)
typedef enum {
    OBS_FILTER_GAIN,                    // Gain adjustment (-30dB to +30dB)
    OBS_FILTER_NOISE_SUPPRESS,          // Noise suppression (Speex/RNNoise/NVAFX)
    OBS_FILTER_NOISE_GATE,              // Noise gate with threshold control
    OBS_FILTER_COMPRESSOR,              // Audio compressor with ratio/threshold
    OBS_FILTER_LIMITER,                 // Audio limiter with threshold
    OBS_FILTER_EXPANDER,                // Audio expander/gate
    OBS_FILTER_UPWARD_COMPRESSOR,       // Upward compressor
    OBS_FILTER_EQUALIZER_3BAND,         // 3-band equalizer (Low/Mid/High)
    OBS_FILTER_INVERT_POLARITY,         // Invert audio polarity
    OBS_FILTER_COUNT
} obs_filter_type_t;

// Noise suppression methods
typedef enum {
    OBS_NOISE_SUPPRESS_SPEEX,           // Speex (low CPU, low quality)
    OBS_NOISE_SUPPRESS_RNNOISE,         // RNNoise (good quality, more CPU)
    OBS_NOISE_SUPPRESS_NVAFX_DENOISER,  // NVIDIA Noise Removal
    OBS_NOISE_SUPPRESS_NVAFX_DEREVERB,  // NVIDIA Room Echo Removal
    OBS_NOISE_SUPPRESS_NVAFX_BOTH       // NVIDIA Noise + Echo Removal
} obs_noise_suppress_method_t;

// Expander detection modes
typedef enum {
    OBS_EXPANDER_DETECT_RMS,            // RMS detection
    OBS_EXPANDER_DETECT_PEAK            // Peak detection
} obs_expander_detect_t;

// Expander presets
typedef enum {
    OBS_EXPANDER_PRESET_EXPANDER,       // Standard expander
    OBS_EXPANDER_PRESET_GATE            // Gate mode
} obs_expander_preset_t;

// Filter parameters structure
typedef struct {
    obs_filter_type_t type;
    bool enabled;
    union {
        struct {
            float gain_db;              // Gain in decibels (-30.0 to 30.0)
        } gain;
        
        struct {
            int suppress_level;         // Suppression level in dB (-60 to 0)
            obs_noise_suppress_method_t method;
            float intensity;            // NVAFX intensity (0.0 to 1.0)
        } noise_suppress;
        
        struct {
            float open_threshold;       // Open threshold in dB
            float close_threshold;      // Close threshold in dB
            uint32_t attack_time;       // Attack time in ms
            uint32_t hold_time;         // Hold time in ms
            uint32_t release_time;      // Release time in ms
        } noise_gate;
        
        struct {
            float ratio;                // Compression ratio (1.0 to 20.0)
            float threshold;            // Threshold in dB
            float attack_time;          // Attack time in ms
            float release_time;         // Release time in ms
            float output_gain;          // Output gain in dB
        } compressor;
        
        struct {
            float threshold;            // Threshold in dB
            float release_time;         // Release time in ms
        } limiter;
        
        struct {
            float ratio;                // Expansion ratio
            float threshold;            // Threshold in dB
            float attack_time;          // Attack time in ms
            float release_time;         // Release time in ms
            float output_gain;          // Output gain in dB
            float knee_width;           // Knee width
            obs_expander_detect_t detector; // Detection mode
            obs_expander_preset_t preset;   // Preset mode
        } expander;
        
        struct {
            float ratio;                // Compression ratio for upward compression
            float threshold;            // Threshold in dB
            float attack_time;          // Attack time in ms
            float release_time;         // Release time in ms
            float output_gain;          // Output gain in dB
        } upward_compressor;
        
        struct {
            float low;                  // Low band gain in dB
            float mid;                  // Mid band gain in dB
            float high;                 // High band gain in dB
        } equalizer_3band;
        
        struct {
            // No parameters - simply inverts polarity
            bool invert;                // Enable/disable inversion
        } invert_polarity;
    } params;
} obs_filter_params_t;

// Result codes
typedef enum {
    OBS_PIPELINE_SUCCESS = 0,
    OBS_PIPELINE_ERROR_INVALID_PARAMS = -1,
    OBS_PIPELINE_ERROR_OUT_OF_MEMORY = -2,
    OBS_PIPELINE_ERROR_FILTER_NOT_FOUND = -3,
    OBS_PIPELINE_ERROR_UNSUPPORTED_FORMAT = -4,
    OBS_PIPELINE_ERROR_INITIALIZATION_FAILED = -5,
    OBS_PIPELINE_ERROR_INVALID_FILTER_TYPE = -6,
    OBS_PIPELINE_ERROR_LIBRARY_NOT_AVAILABLE = -7
} obs_pipeline_result_t;

// Pipeline configuration
typedef struct {
    uint32_t sample_rate;       // Audio sample rate (e.g., 48000)
    uint32_t channels;          // Number of channels (1-8)
    uint32_t buffer_size_ms;    // Buffer size in milliseconds (default: 10)
    uint32_t max_filters;       // Maximum number of filters in pipeline (default: 16)
} obs_pipeline_config_t;

// Public API Functions

/**
 * Create a new audio processing pipeline
 * @param config Pipeline configuration
 * @return Pipeline handle or NULL on failure
 */
OBS_MIC_FILTER_API obs_pipeline_t* obs_pipeline_create(const obs_pipeline_config_t* config);

/**
 * Destroy an audio processing pipeline and free all resources
 * @param pipeline Pipeline handle
 */
OBS_MIC_FILTER_API void obs_pipeline_destroy(obs_pipeline_t* pipeline);

/**
 * Process audio data through the pipeline
 * @param pipeline Pipeline handle
 * @param audio Input/output audio buffer
 * @return Result code
 */
OBS_MIC_FILTER_API obs_pipeline_result_t obs_pipeline_process(obs_pipeline_t* pipeline, obs_audio_buffer_t* audio);

/**
 * Add or update a filter in the pipeline
 * @param pipeline Pipeline handle
 * @param filter_id Unique identifier for the filter (0-based index)
 * @param params Filter parameters
 * @return Result code
 */
OBS_MIC_FILTER_API obs_pipeline_result_t obs_pipeline_update_filter(obs_pipeline_t* pipeline, 
                                                                    uint32_t filter_id, 
                                                                    const obs_filter_params_t* params);

/**
 * Remove a filter from the pipeline
 * @param pipeline Pipeline handle
 * @param filter_id Filter identifier
 * @return Result code
 */
OBS_MIC_FILTER_API obs_pipeline_result_t obs_pipeline_remove_filter(obs_pipeline_t* pipeline, uint32_t filter_id);

/**
 * Get the current latency of the pipeline in nanoseconds
 * @param pipeline Pipeline handle
 * @return Latency in nanoseconds, or 0 if pipeline is NULL
 */
OBS_MIC_FILTER_API uint64_t obs_pipeline_get_latency(obs_pipeline_t* pipeline);

/**
 * Reset the pipeline state (clear all buffers)
 * @param pipeline Pipeline handle
 * @return Result code
 */
OBS_MIC_FILTER_API obs_pipeline_result_t obs_pipeline_reset(obs_pipeline_t* pipeline);

/**
 * Get default configuration for a pipeline
 * @param config Output configuration structure
 */
OBS_MIC_FILTER_API void obs_pipeline_get_default_config(obs_pipeline_config_t* config);

/**
 * Get default parameters for a specific filter type
 * @param type Filter type
 * @param params Output parameters structure
 * @return Result code
 */
OBS_MIC_FILTER_API obs_pipeline_result_t obs_pipeline_get_default_filter_params(obs_filter_type_t type, 
                                                                                obs_filter_params_t* params);

/**
 * Check if a filter type is supported in this build
 * @param type Filter type to check
 * @return true if supported, false otherwise
 */
OBS_MIC_FILTER_API bool obs_pipeline_is_filter_supported(obs_filter_type_t type);

/**
 * Get human-readable name for a filter type
 * @param type Filter type
 * @return Filter name string (do not free)
 */
OBS_MIC_FILTER_API const char* obs_pipeline_get_filter_name(obs_filter_type_t type);

#ifdef __cplusplus
}
#endif

#endif // OBS_PIPELINE_H