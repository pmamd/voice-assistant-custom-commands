cmake_minimum_required(VERSION 3.12)
project(voice-assistant-custom-commands)

# Enable building whisper.cpp examples (needed for common and common-sdl libraries)
set(WHISPER_BUILD_EXAMPLES ON CACHE BOOL "Build whisper examples" FORCE)

# AMD VitisAI NPU support (optional, for target machine with FlexML runtime)
option(WHISPER_VITISAI "Enable VitisAI NPU backend for whisper.cpp" OFF)

if(WHISPER_VITISAI)
    # FlexML runtime paths (for target .22 machine)
    set(FLEXMLRT_ROOT "/home/amd/RyzenAI-Full" CACHE PATH "FlexML runtime root directory")

    # Set up FlexML include and library paths
    set(CMAKE_PREFIX_PATH "${FLEXMLRT_ROOT}/lib/python3.12/site-packages/flexmlrt;${FLEXMLRT_ROOT}/deployment;${CMAKE_PREFIX_PATH}")

    # Add FlexML include directory
    include_directories("${FLEXMLRT_ROOT}/lib/python3.12/site-packages/flexmlrt/include")

    # Add FlexML library directory
    link_directories("${FLEXMLRT_ROOT}/deployment/lib")

    message(STATUS "VitisAI NPU support: ENABLED")
    message(STATUS "FlexML runtime: ${FLEXMLRT_ROOT}")
endif()

# Patch VitisAI verbose output (silence "inference completed" message)
if(WHISPER_VITISAI)
    set(VITISAI_ENCODER_FILE "${CMAKE_SOURCE_DIR}/external/whisper.cpp/src/vitisai/whisper-vitisai-encoder.cpp")
    if(EXISTS ${VITISAI_ENCODER_FILE})
        # Check if already patched
        file(READ ${VITISAI_ENCODER_FILE} VITISAI_CONTENT)
        string(FIND "${VITISAI_CONTENT}" "std::fprintf(stdout, \"%s: Vitis AI model inference completed" VERBOSE_LINE_POS)
        if(NOT VERBOSE_LINE_POS EQUAL -1)
            message(STATUS "Patching VitisAI encoder to silence verbose output...")
            execute_process(
                COMMAND sed -i "s|std::fprintf(stdout, \"%s: Vitis AI model inference completed|// &|g" ${VITISAI_ENCODER_FILE}
                RESULT_VARIABLE PATCH_RESULT
            )
            if(PATCH_RESULT EQUAL 0)
                message(STATUS "VitisAI verbose output silenced")
            else()
                message(WARNING "Failed to patch VitisAI encoder")
            endif()
        else()
            message(STATUS "VitisAI encoder already patched (verbose output silenced)")
        endif()
    endif()
endif()

# Optional llama.cpp build (for llama-server binary)
option(BUILD_LLAMA_SERVER "Build llama-server from submodule" OFF)

if(BUILD_LLAMA_SERVER)
    # Configure llama.cpp with same GPU/NPU flags as whisper
    if(GGML_HIP)
        set(LLAMA_HIPBLAS ON CACHE BOOL "Enable hipBLAS" FORCE)
    endif()

    if(WHISPER_VITISAI)
        # Note: llama.cpp uses LLAMA_VITISAI flag, not WHISPER_VITISAI
        set(LLAMA_VITISAI ON CACHE BOOL "Enable VitisAI NPU backend" FORCE)
    endif()

    add_subdirectory(external/llama.cpp)
    message(STATUS "llama-server will be built from submodule")
else()
    message(STATUS "llama-server not being built - use external installation")
endif()

# Build whisper.cpp submodule
add_subdirectory(external/whisper.cpp)

# Build our custom talk-llama with modifications
if (WHISPER_SDL2)
    # Find SDL2 (required for talk-llama)
    find_package(SDL2 REQUIRED)
    message(STATUS "SDL2_INCLUDE_DIRS = ${SDL2_INCLUDE_DIRS}")
    message(STATUS "SDL2_LIBRARIES    = ${SDL2_LIBRARIES}")

    # Find CURL for TTS communication
    find_package(CURL REQUIRED)
    message(STATUS "CURL_INCLUDE_DIRS = ${CURL_INCLUDE_DIRS}")
    message(STATUS "CURL_LIBRARIES    = ${CURL_LIBRARIES}")

    # Find cJSON for TTS request encoding
    find_library(CJSON_LIBRARY cjson)
    if(NOT CJSON_LIBRARY)
        message(FATAL_ERROR "cJSON library not found. Install with: sudo apt-get install libcjson-dev")
    endif()
    message(STATUS "CJSON_LIBRARY = ${CJSON_LIBRARY}")

    set(TARGET voice-assistant)

    # Our custom source files
    # Note: console.cpp is #included in talk-llama.cpp, not compiled separately
    # LLM inference is handled by llama-server over HTTP (no embedded llama.cpp)
    add_executable(${TARGET}
        src/talk-llama.cpp
        src/tts-socket.c
        src/tts-request.c
        src/tool-system.cpp
        src/tool-parser.cpp
        src/wyoming-client.cpp
    )

    # Include directories (order matters - local files before system)
    target_include_directories(${TARGET} BEFORE PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src
        ${CMAKE_CURRENT_SOURCE_DIR}/external/whisper.cpp/examples
        ${CMAKE_CURRENT_SOURCE_DIR}/external/whisper.cpp
    )

    target_include_directories(${TARGET} PRIVATE
        ${SDL2_INCLUDE_DIRS}
        ${CURL_INCLUDE_DIRS}
    )

    # Link whisper libraries
    if (WHISPER_CLBLAST)
        set(CLBLAST_LIBNAME clblast)
    endif()

    target_link_libraries(${TARGET} PRIVATE
        common
        common-sdl
        whisper
        ${SDL2_LIBRARIES}
        ${CURL_LIBRARIES}
        ${CJSON_LIBRARY}
        ${CLBLAST_LIBNAME}
        ${CMAKE_THREAD_LIBS_INIT}
    )

    # Link FlexML runtime if VitisAI is enabled
    if(WHISPER_VITISAI)
        target_link_libraries(${TARGET} PRIVATE flexmlrt)
        # Set rpath so runtime can find libflexmlrt.so without LD_LIBRARY_PATH
        set_target_properties(${TARGET} PROPERTIES
            INSTALL_RPATH "${FLEXMLRT_ROOT}/deployment/lib"
            BUILD_RPATH "${FLEXMLRT_ROOT}/deployment/lib"
        )
    endif()

    if(WIN32)
        # Windows 8.1 or later for PrefetchVirtualMemory
        target_compile_definitions(${TARGET} PRIVATE -D_WIN32_WINNT=0x0602)
    endif()

    include(external/whisper.cpp/cmake/DefaultTargetOptions.cmake)

    # Wyoming client test program
    add_executable(test-wyoming-client
        src/test-wyoming-client.cpp
        src/wyoming-client.cpp
    )
    set_target_properties(test-wyoming-client PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    )
endif()
