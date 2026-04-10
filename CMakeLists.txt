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

# Build whisper.cpp submodule
add_subdirectory(whisper.cpp)

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

    set(TARGET talk-llama-custom)

    # Our custom source files
    # Note: console.cpp is #included in talk-llama.cpp, not compiled separately
    # LLM inference is handled by llama-server over HTTP (no embedded llama.cpp)
    add_executable(${TARGET}
        custom/talk-llama/talk-llama.cpp
        custom/talk-llama/tts-socket.c
        custom/talk-llama/tts-request.c
        custom/talk-llama/tool-system.cpp
        custom/talk-llama/tool-parser.cpp
        custom/talk-llama/wyoming-client.cpp
    )

    # Include directories (order matters - local files before system)
    target_include_directories(${TARGET} BEFORE PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/custom/talk-llama
        ${CMAKE_CURRENT_SOURCE_DIR}/whisper.cpp/examples
        ${CMAKE_CURRENT_SOURCE_DIR}/whisper.cpp
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

    include(whisper.cpp/cmake/DefaultTargetOptions.cmake)

    # Wyoming client test program
    add_executable(test-wyoming-client
        custom/talk-llama/test-wyoming-client.cpp
        custom/talk-llama/wyoming-client.cpp
    )
    set_target_properties(test-wyoming-client PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    )
endif()
