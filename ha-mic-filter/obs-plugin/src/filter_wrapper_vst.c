#include "filter_wrapper_vst.h"
#include "memory_utils.h"
#include "audio_utils.h"
#include <string.h>
#include <math.h>
#include <stdlib.h>

#ifdef _WIN32
#include <windows.h>
#elif __linux__
#include <dlfcn.h>
#elif __APPLE__
#include <CoreFoundation/CoreFoundation.h>
#endif

// VST 2.x SDK constants and structures (minimal implementation)
#define VST_MAGIC 0x56737450  // 'VstP' as 32-bit integer
#define VST_VERSION 2400

typedef struct AEffect AEffect;
typedef intptr_t VstIntPtr;

// VST opcodes
enum {
    effOpen = 0,
    effClose,
    effSetProgram,
    effGetProgram,
    effSetProgramName,
    effGetProgramName,
    effGetParamLabel,
    effGetParamDisplay,
    effGetParamName,
    effSetSampleRate = 10,
    effSetBlockSize,
    effMainsChanged,
    effEditGetRect,
    effEditOpen,
    effEditClose,
    effProcessReplacing = 23,
    effGetChunk = 23,
    effSetChunk,
    effCanDo = 51
};

// Host callback opcodes
enum {
    audioMasterVersion = 1,
    audioMasterCurrentId,
    audioMasterIdle,
    audioMasterGetTime = 7,
    audioMasterGetSampleRate = 11,
    audioMasterGetBlockSize,
    audioMasterGetCurrentProcessLevel,
    audioMasterGetAutomationState
};

// VST time info flags
enum {
    kVstTransportPlaying = 1 << 1,
    kVstPpqPosValid = 1 << 9,
    kVstTempoValid = 1 << 10,
    kVstTimeSigValid = 1 << 13
};

typedef struct VstTimeInfo {
    double samplePos;
    double sampleRate;
    double nanoSeconds;
    double ppqPos;
    double tempo;
    int timeSigNumerator;
    int timeSigDenominator;
    int flags;
} VstTimeInfo;

typedef VstIntPtr (*DispatcherProc)(AEffect* effect, int32_t opcode, int32_t index, VstIntPtr value, void* ptr, float opt);
typedef void (*ProcessProc)(AEffect* effect, float** inputs, float** outputs, int32_t sampleFrames);
typedef void (*SetParameterProc)(AEffect* effect, int32_t index, float parameter);
typedef float (*GetParameterProc)(AEffect* effect, int32_t index);

// VST AEffect structure (simplified)
typedef struct AEffect {
    int32_t magic;
    DispatcherProc dispatcher;
    ProcessProc process;
    SetParameterProc setParameter;
    GetParameterProc getParameter;
    int32_t numPrograms;
    int32_t numParams;
    int32_t numInputs;
    int32_t numOutputs;
    int32_t flags;
    VstIntPtr resvd1;
    VstIntPtr resvd2;
    int32_t initialDelay;
    int32_t realQualities;
    int32_t offQualities;
    float ioRatio;
    void* object;
    void* user;
    int32_t uniqueID;
    int32_t version;
    ProcessProc processReplacing;
    ProcessProc processDoubleReplacing;
    char future[56];
} AEffect;

// VST plugin main function type
typedef AEffect* (*VstPluginMain)(VstIntPtr (*hostCallback)(AEffect* effect, int32_t opcode, int32_t index, VstIntPtr value, void* ptr, float opt));

// VST filter internal data structure
typedef struct {
    obs_pipeline_config_t config;
    char plugin_path[512];
    
    // VST plugin data
    AEffect* effect;
    VstPluginMain plugin_main;
    bool plugin_loaded;
    
    // Library handle
#ifdef _WIN32
    HMODULE dll_handle;
#elif __linux__
    void* so_handle;
#elif __APPLE__
    CFBundleRef bundle;
#endif
    
    // Audio buffers
    float** input_buffers;
    float** output_buffers;
    int buffer_size;
    
    // VST state
    int current_program;
    float parameters[128];
    int parameter_count;
    
    // Time info
    VstTimeInfo time_info;
    double sample_position;
    
} vst_filter_data_t;

// Host callback function (simplified)
static VstIntPtr host_callback(AEffect* effect, int32_t opcode, int32_t index, VstIntPtr value, void* ptr, float opt)
{
    vst_filter_data_t* data = (vst_filter_data_t*)effect->user;
    
    switch (opcode) {
        case audioMasterVersion:
            return VST_VERSION;
            
        case audioMasterGetSampleRate:
            return (VstIntPtr)data->config.sample_rate;
            
        case audioMasterGetBlockSize:
            return data->buffer_size;
            
        case audioMasterGetTime:
            // Update time info
            data->time_info.samplePos = data->sample_position;
            data->time_info.sampleRate = data->config.sample_rate;
            data->time_info.flags = kVstPpqPosValid | kVstTempoValid | kVstTimeSigValid;
            data->time_info.ppqPos = 0.0;
            data->time_info.tempo = 120.0;
            data->time_info.timeSigNumerator = 4;
            data->time_info.timeSigDenominator = 4;
            return (VstIntPtr)&data->time_info;
            
        case audioMasterIdle:
            return 0;
            
        default:
            return 0;
    }
}

// Load VST plugin library
static bool load_vst_library(vst_filter_data_t* data, const char* path)
{
#ifdef _WIN32
    data->dll_handle = LoadLibraryA(path);
    if (!data->dll_handle) {
        return false;
    }
    data->plugin_main = (VstPluginMain)GetProcAddress(data->dll_handle, "VSTPluginMain");
    if (!data->plugin_main) {
        data->plugin_main = (VstPluginMain)GetProcAddress(data->dll_handle, "main");
    }
#elif __linux__
    data->so_handle = dlopen(path, RTLD_LAZY);
    if (!data->so_handle) {
        return false;
    }
    data->plugin_main = (VstPluginMain)dlsym(data->so_handle, "VSTPluginMain");
    if (!data->plugin_main) {
        data->plugin_main = (VstPluginMain)dlsym(data->so_handle, "main");
    }
#elif __APPLE__
    // macOS bundle loading (simplified)
    CFStringRef plugin_path_string = CFStringCreateWithCString(NULL, path, kCFStringEncodingUTF8);
    CFURLRef plugin_url = CFURLCreateWithFileSystemPath(NULL, plugin_path_string, kCFURLPOSIXPathStyle, false);
    data->bundle = CFBundleCreate(NULL, plugin_url);
    
    CFRelease(plugin_path_string);
    CFRelease(plugin_url);
    
    if (!data->bundle) {
        return false;
    }
    
    data->plugin_main = (VstPluginMain)CFBundleGetFunctionPointerForName(data->bundle, CFSTR("VSTPluginMain"));
    if (!data->plugin_main) {
        data->plugin_main = (VstPluginMain)CFBundleGetFunctionPointerForName(data->bundle, CFSTR("main_macho"));
    }
#endif
    
    return data->plugin_main != NULL;
}

// Unload VST library
static void unload_vst_library(vst_filter_data_t* data)
{
#ifdef _WIN32
    if (data->dll_handle) {
        FreeLibrary(data->dll_handle);
        data->dll_handle = NULL;
    }
#elif __linux__
    if (data->so_handle) {
        dlclose(data->so_handle);
        data->so_handle = NULL;
    }
#elif __APPLE__
    if (data->bundle) {
        CFRelease(data->bundle);
        data->bundle = NULL;
    }
#endif
    data->plugin_main = NULL;
}

// Create audio buffers
static bool create_audio_buffers(vst_filter_data_t* data, int buffer_size)
{
    if (!data->effect) return false;
    
    int inputs = data->effect->numInputs;
    int outputs = data->effect->numOutputs;
    
    // Allocate input buffers
    data->input_buffers = (float**)obs_calloc(inputs * sizeof(float*));
    if (!data->input_buffers) return false;
    
    for (int i = 0; i < inputs; i++) {
        data->input_buffers[i] = (float*)obs_calloc(buffer_size * sizeof(float));
        if (!data->input_buffers[i]) return false;
    }
    
    // Allocate output buffers
    data->output_buffers = (float**)obs_calloc(outputs * sizeof(float*));
    if (!data->output_buffers) return false;
    
    for (int i = 0; i < outputs; i++) {
        data->output_buffers[i] = (float*)obs_calloc(buffer_size * sizeof(float));
        if (!data->output_buffers[i]) return false;
    }
    
    data->buffer_size = buffer_size;
    return true;
}

// Free audio buffers
static void free_audio_buffers(vst_filter_data_t* data)
{
    if (data->input_buffers) {
        if (data->effect) {
            for (int i = 0; i < data->effect->numInputs; i++) {
                if (data->input_buffers[i]) {
                    obs_free(data->input_buffers[i]);
                }
            }
        }
        obs_free(data->input_buffers);
        data->input_buffers = NULL;
    }
    
    if (data->output_buffers) {
        if (data->effect) {
            for (int i = 0; i < data->effect->numOutputs; i++) {
                if (data->output_buffers[i]) {
                    obs_free(data->output_buffers[i]);
                }
            }
        }
        obs_free(data->output_buffers);
        data->output_buffers = NULL;
    }
}

void* filter_wrapper_vst_create(const obs_pipeline_config_t* config)
{
    if (!config) {
        return NULL;
    }

    vst_filter_data_t* data = obs_calloc(sizeof(vst_filter_data_t));
    if (!data) {
        return NULL;
    }

    data->config = *config;
    data->plugin_loaded = false;
    data->effect = NULL;
    data->current_program = 0;
    data->parameter_count = 0;
    data->sample_position = 0.0;
    
    // Initialize time info
    memset(&data->time_info, 0, sizeof(VstTimeInfo));
    data->time_info.sampleRate = config->sample_rate;
    
    // Initialize parameters
    for (int i = 0; i < 128; i++) {
        data->parameters[i] = 0.0f;
    }

    return data;
}

void filter_wrapper_vst_destroy(void* filter_data)
{
    if (!filter_data) {
        return;
    }

    vst_filter_data_t* data = (vst_filter_data_t*)filter_data;
    
    // Unload VST effect
    if (data->effect) {
        data->effect->dispatcher(data->effect, effClose, 0, 0, NULL, 0.0f);
    }
    
    // Free audio buffers
    free_audio_buffers(data);
    
    // Unload library
    unload_vst_library(data);
    
    obs_free(filter_data);
}

obs_pipeline_result_t filter_wrapper_vst_load_plugin(void* filter_data, const char* plugin_path)
{
    if (!filter_data || !plugin_path) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    vst_filter_data_t* data = (vst_filter_data_t*)filter_data;
    
    // Unload existing plugin
    if (data->effect) {
        data->effect->dispatcher(data->effect, effClose, 0, 0, NULL, 0.0f);
        data->effect = NULL;
    }
    free_audio_buffers(data);
    unload_vst_library(data);
    
    // Load new plugin
    if (!load_vst_library(data, plugin_path)) {
        return OBS_PIPELINE_ERROR_INITIALIZATION_FAILED;
    }
    
    // Create VST effect
    data->effect = data->plugin_main(host_callback);
    if (!data->effect) {
        unload_vst_library(data);
        return OBS_PIPELINE_ERROR_INITIALIZATION_FAILED;
    }
    
    // Validate VST effect
    if (data->effect->magic != VST_MAGIC) {
        unload_vst_library(data);
        data->effect = NULL;
        return OBS_PIPELINE_ERROR_INITIALIZATION_FAILED;
    }
    
    // Set user data
    data->effect->user = data;
    
    // Initialize effect
    data->effect->dispatcher(data->effect, effOpen, 0, 0, NULL, 0.0f);
    data->effect->dispatcher(data->effect, effSetSampleRate, 0, 0, NULL, (float)data->config.sample_rate);
    data->effect->dispatcher(data->effect, effSetBlockSize, 0, 512, NULL, 0.0f);
    data->effect->dispatcher(data->effect, effMainsChanged, 0, 1, NULL, 0.0f);
    
    // Create audio buffers
    if (!create_audio_buffers(data, 512)) {
        filter_wrapper_vst_destroy(data);
        return OBS_PIPELINE_ERROR_OUT_OF_MEMORY;
    }
    
    // Store path and mark as loaded
    strncpy(data->plugin_path, plugin_path, sizeof(data->plugin_path) - 1);
    data->plugin_loaded = true;
    data->parameter_count = data->effect->numParams < 128 ? data->effect->numParams : 128;
    
    return OBS_PIPELINE_SUCCESS;
}

obs_pipeline_result_t filter_wrapper_vst_update(void* filter_data, const vst_filter_params_t* params)
{
    if (!filter_data || !params) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    vst_filter_data_t* data = (vst_filter_data_t*)filter_data;
    
    // Load plugin if path changed
    if (strcmp(data->plugin_path, params->plugin_path) != 0) {
        obs_pipeline_result_t result = filter_wrapper_vst_load_plugin(data, params->plugin_path);
        if (result != OBS_PIPELINE_SUCCESS) {
            return result;
        }
    }
    
    if (!data->effect) {
        return OBS_PIPELINE_ERROR_INITIALIZATION_FAILED;
    }
    
    // Set program
    if (params->program_number != data->current_program) {
        data->effect->dispatcher(data->effect, effSetProgram, 0, params->program_number, NULL, 0.0f);
        data->current_program = params->program_number;
    }
    
    // Set parameters
    for (int i = 0; i < params->parameter_count && i < data->parameter_count; i++) {
        if (data->parameters[i] != params->parameters[i]) {
            data->effect->setParameter(data->effect, i, params->parameters[i]);
            data->parameters[i] = params->parameters[i];
        }
    }

    return OBS_PIPELINE_SUCCESS;
}

obs_pipeline_result_t filter_wrapper_vst_process(void* filter_data, obs_audio_buffer_t* audio)
{
    if (!filter_data || !audio) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    vst_filter_data_t* data = (vst_filter_data_t*)filter_data;
    
    if (!data->effect || !data->plugin_loaded) {
        return OBS_PIPELINE_SUCCESS; // Pass through
    }
    
    // Validate audio buffer
    if (!audio_buffer_validate(audio, data->config.channels, data->config.sample_rate)) {
        return OBS_PIPELINE_ERROR_UNSUPPORTED_FORMAT;
    }
    
    uint32_t frames = audio->frames;
    if (frames > data->buffer_size) {
        // For simplicity, process only up to buffer size
        frames = data->buffer_size;
    }
    
    // Copy input audio to VST input buffers
    int vst_inputs = data->effect->numInputs;
    int vst_outputs = data->effect->numOutputs;
    
    for (int ch = 0; ch < vst_inputs && ch < audio->channels; ch++) {
        memcpy(data->input_buffers[ch], audio->data[ch], frames * sizeof(float));
    }
    
    // Clear output buffers
    for (int ch = 0; ch < vst_outputs; ch++) {
        memset(data->output_buffers[ch], 0, frames * sizeof(float));
    }
    
    // Process audio through VST
    if (data->effect->processReplacing) {
        data->effect->processReplacing(data->effect, data->input_buffers, data->output_buffers, frames);
    } else if (data->effect->process) {
        // Legacy VST process (add to existing audio)
        for (int ch = 0; ch < vst_outputs; ch++) {
            memcpy(data->output_buffers[ch], data->input_buffers[ch < vst_inputs ? ch : 0], frames * sizeof(float));
        }
        data->effect->process(data->effect, data->input_buffers, data->output_buffers, frames);
    }
    
    // Copy VST output back to audio buffer
    for (int ch = 0; ch < audio->channels && ch < vst_outputs; ch++) {
        memcpy(audio->data[ch], data->output_buffers[ch], frames * sizeof(float));
    }
    
    // Update sample position
    data->sample_position += frames;
    
    return OBS_PIPELINE_SUCCESS;
}

obs_pipeline_result_t filter_wrapper_vst_set_parameter(void* filter_data, int index, float value)
{
    if (!filter_data) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    vst_filter_data_t* data = (vst_filter_data_t*)filter_data;
    
    if (!data->effect || index < 0 || index >= data->parameter_count) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }
    
    // Clamp value to 0.0-1.0 range
    if (value < 0.0f) value = 0.0f;
    if (value > 1.0f) value = 1.0f;
    
    data->effect->setParameter(data->effect, index, value);
    data->parameters[index] = value;
    
    return OBS_PIPELINE_SUCCESS;
}

float filter_wrapper_vst_get_parameter(void* filter_data, int index)
{
    if (!filter_data) {
        return 0.0f;
    }

    vst_filter_data_t* data = (vst_filter_data_t*)filter_data;
    
    if (!data->effect || index < 0 || index >= data->parameter_count) {
        return 0.0f;
    }
    
    return data->effect->getParameter(data->effect, index);
}

obs_pipeline_result_t filter_wrapper_vst_set_program(void* filter_data, int program)
{
    if (!filter_data) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }

    vst_filter_data_t* data = (vst_filter_data_t*)filter_data;
    
    if (!data->effect || program < 0 || program >= data->effect->numPrograms) {
        return OBS_PIPELINE_ERROR_INVALID_PARAMS;
    }
    
    data->effect->dispatcher(data->effect, effSetProgram, 0, program, NULL, 0.0f);
    data->current_program = program;
    
    return OBS_PIPELINE_SUCCESS;
}

int filter_wrapper_vst_get_program(void* filter_data)
{
    if (!filter_data) {
        return 0;
    }

    vst_filter_data_t* data = (vst_filter_data_t*)filter_data;
    
    if (!data->effect) {
        return 0;
    }
    
    return (int)data->effect->dispatcher(data->effect, effGetProgram, 0, 0, NULL, 0.0f);
}

bool filter_wrapper_vst_has_editor(void* filter_data)
{
    if (!filter_data) {
        return false;
    }

    vst_filter_data_t* data = (vst_filter_data_t*)filter_data;
    
    if (!data->effect) {
        return false;
    }
    
    return (data->effect->flags & (1 << 0)) != 0; // effFlagsHasEditor
}

void filter_wrapper_vst_reset(void* filter_data)
{
    if (!filter_data) {
        return;
    }

    vst_filter_data_t* data = (vst_filter_data_t*)filter_data;
    
    if (data->effect) {
        // Reset VST plugin
        data->effect->dispatcher(data->effect, effMainsChanged, 0, 0, NULL, 0.0f);
        data->effect->dispatcher(data->effect, effMainsChanged, 0, 1, NULL, 0.0f);
    }
    
    // Reset sample position
    data->sample_position = 0.0;
}