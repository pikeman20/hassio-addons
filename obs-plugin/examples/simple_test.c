#include "obs_pipeline.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

// Simple test program to demonstrate the DLL usage
int main()
{
    printf("OBS Mic Filter DLL Test\n");
    printf("========================\n\n");

    // Get default configuration
    obs_pipeline_config_t config;
    obs_pipeline_get_default_config(&config);
    
    printf("Default Configuration:\n");
    printf("  Sample Rate: %d Hz\n", config.sample_rate);
    printf("  Channels: %d\n", config.channels);
    printf("  Buffer Size: %d ms\n", config.buffer_size_ms);
    printf("  Max Filters: %d\n\n", config.max_filters);

    // Create pipeline
    obs_pipeline_t* pipeline = obs_pipeline_create(&config);
    if (!pipeline) {
        printf("ERROR: Failed to create pipeline\n");
        return 1;
    }
    printf("Pipeline created successfully\n");

    // Test filter support
    printf("\nSupported Filters:\n");
    for (int i = 0; i < OBS_FILTER_COUNT; i++) {
        const char* name = obs_pipeline_get_filter_name((obs_filter_type_t)i);
        bool supported = obs_pipeline_is_filter_supported((obs_filter_type_t)i);
        printf("  %s: %s\n", name, supported ? "YES" : "NO");
    }

    // Add a gain filter
    obs_filter_params_t filter_params;
    obs_pipeline_result_t result = obs_pipeline_get_default_filter_params(OBS_FILTER_GAIN, &filter_params);
    if (result == OBS_PIPELINE_SUCCESS) {
        // Set gain to +6dB
        filter_params.params.gain.gain_db = 6.0f;
        
        result = obs_pipeline_update_filter(pipeline, 0, &filter_params);
        if (result == OBS_PIPELINE_SUCCESS) {
            printf("\nGain filter added successfully (+6dB)\n");
        } else {
            printf("\nERROR: Failed to add gain filter (code: %d)\n", result);
        }
    }

    // Create test audio buffer
    const uint32_t test_frames = 480; // 10ms at 48kHz
    float* channel_data[2];
    channel_data[0] = (float*)malloc(test_frames * sizeof(float));
    channel_data[1] = (float*)malloc(test_frames * sizeof(float));

    // Fill with test tone (sine wave at 1kHz)
    for (uint32_t i = 0; i < test_frames; i++) {
        float sample = 0.1f * sinf(2.0f * 3.14159f * 1000.0f * i / config.sample_rate);
        channel_data[0][i] = sample;
        channel_data[1][i] = sample;
    }

    obs_audio_buffer_t audio_buffer = {
        .data = channel_data,
        .frames = test_frames,
        .channels = config.channels,
        .sample_rate = config.sample_rate,
        .timestamp = 0
    };

    // Process audio
    result = obs_pipeline_process(pipeline, &audio_buffer);
    if (result == OBS_PIPELINE_SUCCESS) {
        printf("Audio processed successfully\n");
    } else {
        printf("ERROR: Failed to process audio (code: %d)\n", result);
    }

    // Get pipeline latency
    uint64_t latency = obs_pipeline_get_latency(pipeline);
    printf("Pipeline latency: %llu ns\n", (unsigned long long)latency);

    // Cleanup
    free(channel_data[0]);
    free(channel_data[1]);
    obs_pipeline_destroy(pipeline);
    
    printf("\nTest completed successfully\n");
    return 0;
}