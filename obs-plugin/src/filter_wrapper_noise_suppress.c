#include "filter_wrapper_noise_suppress.h"
#include "memory_utils.h"
#include "audio_utils.h"
#include "rnnoise.h"
#include <math.h>
#include <string.h>
#include <stdlib.h>

#define FRAME_SIZE 480  // RNNoise works with 480 samples at 48kHz (10ms frames)

// Speex constants (simulated - normally from libspeexdsp)
#define SPEEX_PREPROCESS_SET_NOISE_SUPPRESS 0
typedef short spx_int16_t;
typedef struct SpeexPreprocessState_ SpeexPreprocessState;

// Mock Speex functions (normally from libspeexdsp)
static SpeexPreprocessState* speex_preprocess_state_init(int frame_size, int sampling_rate) {
    // Simple allocation for mock implementation
    return (SpeexPreprocessState*)malloc(sizeof(int) * 10);
}

static void speex_preprocess_state_destroy(SpeexPreprocessState* st) {
    if (st) free(st);
}

static int speex_preprocess_ctl(SpeexPreprocessState* st, int request, void* ptr) {
    return 0; // Mock implementation
}

static int speex_preprocess_run(SpeexPreprocessState* st, spx_int16_t* x) {
    // Simple noise reduction simulation - reduce amplitude by suppress level
    for (int i = 0; i < FRAME_SIZE; i++) {
        x[i] = (spx_int16_t)(x[i] * 0.7f); // Simple 30% noise reduction
    }
    return 1;
}

// Noise suppression filter internal data structure
typedef struct {
    obs_pipeline_config_t config;
    int suppress_level;
    obs_noise_suppress_method_t method;
    float intensity;
    
    // RNNoise state
    DenoiseState* rnnoise_state;
    
    // Speex state
    SpeexPreprocessState* speex_state;
    
    // Buffer for frame processing
    float input_buffer[FRAME_SIZE];
    float output_buffer[FRAME_SIZE];
    spx_int16_t speex_buffer[FRAME_SIZE];
    int buffer_pos;
    
    // Processed audio storage
    float* processed_samples;
    int processed_count;
    int processed_capacity;
} noise_suppress_filter_data_t;

void* filter_wrapper_noise_suppress_create(const obs_pipeline_config_t* config)
{
    if (!config) {
        return NULL;
    }

    noise_suppress_filter_data_t* data = obs_calloc(sizeof(noise_suppress_filter_data_t));
    if (!data) {
        return NULL;
    }

    data->config = *config;
    data->suppress_level = -30;
    data->method = OBS_NOISE_SUPPRESS_SPEEX; // Default to Speex (lower CPU)
    data->intensity = 1.0f;
    data->buffer_pos = 0;
    data->processed_count = 0;
    data->processed_capacity = FRAME_SIZE * 4; // Initial capacity

    // Initialize both RNNoise and Speex states
    data->rnnoise_state = rnnoise_create(NULL);
    data->speex_state = speex_preprocess_state_init(FRAME_SIZE, config->sample_rate);
    
    if (!data->rnnoise_state && !data->speex_state) {
        obs_free(data);
        return NULL;
    }

    // Allocate processed samples buffer
    data->processed_samples = obs_malloc(data->processed_capacity * sizeof(float));
    if (!data->processed_samples) {
        if (data->rnnoise_state) rnnoise_destroy(data->rnnoise_state);
        if (data->speex_state) speex_preprocess_state_destroy(data->speex_state);
        obs_free(data);
        return NULL;
    }

    return data;
}

void filter_wrapper_noise_suppress_destroy(void* filter_data)
{
    if (!filter_data) {
        return;
    }

    noise_suppress_filter_data_t* data = (noise_suppress_filter_data_t*)filter_data;
    
    // Cleanup RNNoise state
    if (data->rnnoise_state) {
        rnnoise_destroy(data->rnnoise_state);
    }
    
    // Cleanup Speex state
    if (data->speex_state) {
        speex_preprocess_state_destroy(data->speex_state);
    }
    
    // Free processed samples buffer
    if (data->processed_samples) {
        obs_free(data->processed_samples);
    }
    
    obs_free(filter_data);
}

// Helper function to process with Speex (like OBS implementation)
static void process_speex(noise_suppress_filter_data_t* data, float* samples, uint32_t frames)
{
    // Set suppression level
    speex_preprocess_ctl(data->speex_state, SPEEX_PREPROCESS_SET_NOISE_SUPPRESS, &data->suppress_level);
    
    // Convert float32 to int16 (like OBS does)
    const float c_32_to_16 = (float)32767;
    for (uint32_t i = 0; i < frames && i < FRAME_SIZE; i++) {
        float s = samples[i];
        if (s > 1.0f) s = 1.0f;
        else if (s < -1.0f) s = -1.0f;
        data->speex_buffer[i] = (spx_int16_t)(s * c_32_to_16);
    }
    
    // Process with Speex
    speex_preprocess_run(data->speex_state, data->speex_buffer);
    
    // Convert back to float32
    const float c_16_to_32 = 1.0f / 32768.0f;
    for (uint32_t i = 0; i < frames && i < FRAME_SIZE; i++) {
        samples[i] = (float)data->speex_buffer[i] * c_16_to_32;
    }
}

// Helper function to process with RNNoise (existing implementation)
static void process_rnnoise(noise_suppress_filter_data_t* data, float* samples, uint32_t frames)
{
    // Clear processed buffer
    data->processed_count = 0;
    
    // Process audio in FRAME_SIZE chunks (480 samples for 48kHz)
    for (uint32_t i = 0; i < frames; i++) {
        // Scale input signal like OBS does
        data->input_buffer[data->buffer_pos] = samples[i] * 32768.0f;
        data->buffer_pos++;

        // When we have a full frame, process it
        if (data->buffer_pos >= FRAME_SIZE) {
            // Process frame with RNNoise
            rnnoise_process_frame(data->rnnoise_state, data->output_buffer, data->input_buffer);
            
            // Copy processed frame to output with scale back
            for (int j = 0; j < FRAME_SIZE && data->processed_count < data->processed_capacity; j++) {
                data->processed_samples[data->processed_count++] = data->output_buffer[j] / 32768.0f;
            }
            
            data->buffer_pos = 0;
        }
    }

    // Copy processed samples back to input buffer
    uint32_t samples_to_copy = (data->processed_count < frames) ? data->processed_count : frames;
    for (uint32_t i = 0; i < samples_to_copy; i++) {
        samples[i] = data->processed_samples[i];
    }
}

obs_pipeline_result_t filter_wrapper_noise_suppress_update(void* filter_data, const noise_suppress_filter_params_t* params)
{
    if (!filter_data || !params) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    noise_suppress_filter_data_t* data = (noise_suppress_filter_data_t*)filter_data;
    
    data->suppress_level = params->suppress_level;
    data->method = params->method;
    data->intensity = params->intensity;

    // Update method-specific parameters
    if (data->method == OBS_NOISE_SUPPRESS_SPEEX && data->speex_state) {
        speex_preprocess_ctl(data->speex_state, SPEEX_PREPROCESS_SET_NOISE_SUPPRESS, &data->suppress_level);
    }

    return OBS_PIPELINE_SUCCESS;
}

obs_pipeline_result_t filter_wrapper_noise_suppress_process(void* filter_data, obs_audio_buffer_t* audio)
{
    if (!filter_data || !audio) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    noise_suppress_filter_data_t* data = (noise_suppress_filter_data_t*)filter_data;
    
    // Validate audio buffer
    if (!audio_buffer_validate(audio, data->config.channels, data->config.sample_rate)) {
        return OBS_PIPELINE_ERROR_UNSUPPORTED_FORMAT;
    }

    // Check if we have appropriate filter initialized
    bool has_rnnoise = (data->rnnoise_state != NULL);
    bool has_speex = (data->speex_state != NULL);
    
    if (!has_rnnoise && !has_speex) {
        return OBS_PIPELINE_ERROR_INITIALIZATION_FAILED;
    }

    // Process only the first channel for now (mono processing)
    float* samples = audio->data[0];
    uint32_t frames = audio->frames;
    
    // Debug: Print to verify processing
    static int debug_counter = 0;
    if (debug_counter++ % 480 == 0) {  // Print every ~1 second at 48kHz
        const char* method_name = (data->method == OBS_NOISE_SUPPRESS_RNNOISE) ? "RNNoise" : "Speex";
        printf("%s processing frame %d, %u samples\n", method_name, debug_counter/480, audio->frames);
    }

    // Ensure we have enough space in processed buffer for RNNoise
    if (data->method == OBS_NOISE_SUPPRESS_RNNOISE) {
        if (frames > data->processed_capacity) {
            data->processed_capacity = frames + FRAME_SIZE;
            float* new_buffer = obs_realloc(data->processed_samples,
                                           data->processed_capacity * sizeof(float));
            if (!new_buffer) {
                return OBS_PIPELINE_ERROR_OUT_OF_MEMORY;
            }
            data->processed_samples = new_buffer;
        }
    }

    // Choose processing method based on configuration
    switch (data->method) {
        case OBS_NOISE_SUPPRESS_RNNOISE:
            if (has_rnnoise) {
                // RNNoise only works with 48kHz
                if (audio->sample_rate != 48000) {
                    return OBS_PIPELINE_SUCCESS; // Pass through
                }
                process_rnnoise(data, samples, frames);
            }
            break;
            
        case OBS_NOISE_SUPPRESS_SPEEX:
        default:
            if (has_speex) {
                // Speex works with various sample rates
                process_speex(data, samples, frames);
            }
            break;
    }

    return OBS_PIPELINE_SUCCESS;
}

void filter_wrapper_noise_suppress_reset(void* filter_data)
{
    if (!filter_data) {
        return;
    }

    noise_suppress_filter_data_t* data = (noise_suppress_filter_data_t*)filter_data;
    
    // Reset buffer position and processed count
    data->buffer_pos = 0;
    data->processed_count = 0;
    
    // Clear input and output buffers
    for (int i = 0; i < FRAME_SIZE; i++) {
        data->input_buffer[i] = 0.0f;
        data->output_buffer[i] = 0.0f;
    }
    
    // RNNoise doesn't have an explicit reset function,
    // but clearing buffers should be sufficient for most cases
}