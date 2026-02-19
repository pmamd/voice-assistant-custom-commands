cmake_minimum_required(VERSION 3.12)
project(voice-assistant-custom-commands)

# Enable building whisper.cpp examples (needed for common and common-sdl libraries)
set(WHISPER_BUILD_EXAMPLES ON CACHE BOOL "Build whisper examples" FORCE)

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

    set(TARGET talk-llama-custom)

    # Our custom source files (includes full llama.cpp from talk-llama-fast)
    add_executable(${TARGET}
        custom/talk-llama/talk-llama.cpp
        custom/talk-llama/console.cpp
        custom/talk-llama/llama.cpp
        custom/talk-llama/unicode.cpp
        custom/talk-llama/unicode-data.cpp
    )

    # Include directories (order matters - local files before system)
    target_include_directories(${TARGET} BEFORE PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/custom/talk-llama
        ${CMAKE_CURRENT_SOURCE_DIR}/whisper.cpp/examples/talk-llama
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
        ${CLBLAST_LIBNAME}
        ${CMAKE_THREAD_LIBS_INIT}
    )

    if(WIN32)
        # Windows 8.1 or later for PrefetchVirtualMemory
        target_compile_definitions(${TARGET} PRIVATE -D_WIN32_WINNT=0x0602)
    endif()

    include(whisper.cpp/cmake/DefaultTargetOptions.cmake)
endif()
