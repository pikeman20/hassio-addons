#include "memory_utils.h"
#include <stdlib.h>
#include <string.h>

void* obs_malloc(size_t size)
{
    if (size == 0) {
        return NULL;
    }
    
    return malloc(size);
}

void obs_free(void* ptr)
{
    if (ptr) {
        free(ptr);
    }
}

void* obs_realloc(void* ptr, size_t size)
{
    if (size == 0) {
        obs_free(ptr);
        return NULL;
    }
    
    return realloc(ptr, size);
}

void* obs_calloc(size_t size)
{
    if (size == 0) {
        return NULL;
    }
    
    void* ptr = malloc(size);
    if (ptr) {
        memset(ptr, 0, size);
    }
    
    return ptr;
}