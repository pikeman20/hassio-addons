#ifndef AUDIO_UTILS_H
#define AUDIO_UTILS_H

#include "obs_pipeline.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Convert decibels to linear multiplier
 * @param db Value in decibels
 * @return Linear multiplier
 */
float db_to_mul(float db);

/**
 * Convert linear multiplier to decibels
 * @param mul Linear multiplier
 * @return Value in decibels
 */
float mul_to_db(float mul);

/**
 * Validate audio buffer format
 * @param audio Audio buffer to validate
 * @param expected_channels Expected number of channels
 * @param expected_sample_rate Expected sample rate
 * @return true if valid, false otherwise
 */
bool audio_buffer_validate(const obs_audio_buffer_t* audio, 
                          uint32_t expected_channels, 
                          uint32_t expected_sample_rate);

/**
 * Copy audio buffer data
 * @param dst Destination buffer
 * @param src Source buffer
 * @param frames Number of frames to copy
 * @param channels Number of channels
 */
void audio_buffer_copy(float** dst, float** src, uint32_t frames, uint32_t channels);

/**
 * Clear audio buffer data (set to silence)
 * @param audio Audio buffer to clear
 */
void audio_buffer_clear(obs_audio_buffer_t* audio);

/**
 * Calculate RMS level of audio buffer
 * @param data Audio data pointer
 * @param frames Number of frames
 * @return RMS level
 */
float audio_calculate_rms(const float* data, uint32_t frames);

/**
 * Calculate peak level of audio buffer
 * @param data Audio data pointer
 * @param frames Number of frames
 * @return Peak level
 */
float audio_calculate_peak(const float* data, uint32_t frames);

#ifdef __cplusplus
}
#endif

#endif // AUDIO_UTILS_H