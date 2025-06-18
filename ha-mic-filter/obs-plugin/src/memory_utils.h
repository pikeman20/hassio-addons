#ifndef MEMORY_UTILS_H
#define MEMORY_UTILS_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Allocate memory with zero initialization
 * @param size Size in bytes to allocate
 * @return Allocated memory pointer or NULL on failure
 */
void* obs_malloc(size_t size);

/**
 * Free memory allocated with obs_malloc
 * @param ptr Pointer to free
 */
void obs_free(void* ptr);

/**
 * Reallocate memory
 * @param ptr Existing pointer (can be NULL)
 * @param size New size in bytes
 * @return Reallocated memory pointer or NULL on failure
 */
void* obs_realloc(void* ptr, size_t size);

/**
 * Allocate memory with zero initialization (equivalent to calloc)
 * @param size Size in bytes to allocate
 * @return Allocated and zeroed memory pointer or NULL on failure
 */
void* obs_calloc(size_t size);

#ifdef __cplusplus
}
#endif

#endif // MEMORY_UTILS_H