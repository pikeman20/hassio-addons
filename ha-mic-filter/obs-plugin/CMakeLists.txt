cmake_minimum_required(VERSION 3.16)
project(obs-mic-filter VERSION 1.0.0 LANGUAGES C)

# Only use C language for this project
# Remove C++ standard settings since we only use C

# Check if RNNoise source files exist locally (for ha-mic-filter)
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/./rnnoise/src")
    # Use local RNNoise source files for ha-mic-filter
    set(RNNOISE_SOURCES
        ./rnnoise/src/celt_lpc.c
        ./rnnoise/src/denoise.c
        ./rnnoise/src/kiss_fft.c
        ./rnnoise/src/pitch.c
        ./rnnoise/src/rnn.c
        ./rnnoise/src/rnn_data.c
        ./rnnoise/src/rnn_reader.c
    )
    set(RNNOISE_INCLUDE_DIR ./rnnoise/include)
else()
    # Use OBS Studio RNNoise source files
    set(RNNOISE_SOURCES
        ../obs-studio/plugins/obs-filters/rnnoise/src/celt_lpc.c
        ../obs-studio/plugins/obs-filters/rnnoise/src/denoise.c
        ../obs-studio/plugins/obs-filters/rnnoise/src/kiss_fft.c
        ../obs-studio/plugins/obs-filters/rnnoise/src/pitch.c
        ../obs-studio/plugins/obs-filters/rnnoise/src/rnn.c
        ../obs-studio/plugins/obs-filters/rnnoise/src/rnn_data.c
        ../obs-studio/plugins/obs-filters/rnnoise/src/rnn_reader.c
    )
    set(RNNOISE_INCLUDE_DIR ../obs-studio/plugins/obs-filters/rnnoise/include)
endif()

# Build as shared library (DLL)
add_library(obs-mic-filter SHARED
    src/obs_pipeline.c
    src/filter_wrapper_gain.c
    src/filter_wrapper_noise_suppress.c
    src/filter_wrapper_eq.c
    src/filter_wrapper_compressor.c
    src/filter_wrapper_expander.c
    src/filter_wrapper_vst.c
    src/pipeline_manager.c
    src/memory_utils.c
    src/audio_utils.c
    ${RNNOISE_SOURCES}
)

target_include_directories(obs-mic-filter
    PUBLIC
        include
    PRIVATE
        src
        ${RNNOISE_INCLUDE_DIR}
        ${RNNOISE_INCLUDE_DIR}/../src
)

# Windows DLL configuration
if(WIN32 OR CMAKE_SYSTEM_NAME STREQUAL "Windows")
    # Export all symbols automatically for Windows DLL
    set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)
    
    # Remove lib prefix for DLL output
    set_target_properties(obs-mic-filter PROPERTIES PREFIX "")
    
    # Set output directory for runtime libraries (DLLs)
    set_target_properties(obs-mic-filter PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}
        LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}
        ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}
    )
    
    # Define export symbols for Windows DLL
    target_compile_definitions(obs-mic-filter PRIVATE OBS_MIC_FILTER_EXPORTS)
endif()

# Enable filters for testing (even without actual libraries)
target_compile_definitions(obs-mic-filter PRIVATE
    LIBRNNOISE_ENABLED  # Enable noise suppression filter for testing
    RNNOISE_BUILD       # Enable RNNoise build mode
    COMPILE_OPUS        # Enable opus_fft_c functions in kiss_fft.c
    CUSTOM_MODES        # Enable custom FFT modes
    # Let RNNoise use its own type definitions from opus_types.h
    OPUS_INLINE=inline
)

# Link math library (required for RNNoise)
target_link_libraries(obs-mic-filter PRIVATE m)

# Optional: Link external libraries if available
find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
    pkg_check_modules(RNNOISE QUIET rnnoise)
    if(RNNOISE_FOUND)
        target_link_libraries(obs-mic-filter PRIVATE ${RNNOISE_LIBRARIES})
        target_include_directories(obs-mic-filter PRIVATE ${RNNOISE_INCLUDE_DIRS})
        message(STATUS "Found RNNoise library: ${RNNOISE_LIBRARIES}")
    else()
        message(STATUS "RNNoise library not found, using built-in implementation")
    endif()
else()
    message(STATUS "PkgConfig not found, using built-in RNNoise implementation")
endif()

# Install targets
install(TARGETS obs-mic-filter
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)

install(DIRECTORY include/
    DESTINATION include
    FILES_MATCHING PATTERN "*.h"
)