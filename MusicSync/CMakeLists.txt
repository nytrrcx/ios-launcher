cmake_minimum_required(VERSION 3.21)
project(ProMotionMusicSync VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_VISIBILITY_PRESET hidden)
add_library(${PROJECT_NAME} SHARED src/main.cpp)
if(NOT DEFINED ENV{GEODE_SDK})
    message(FATAL_ERROR "Set GEODE_SDK to the Geode 5.11.2 SDK")
endif()
add_subdirectory($ENV{GEODE_SDK} ${CMAKE_CURRENT_BINARY_DIR}/geode)
# The pinned iOS bindings generate standalone FMOD C entry points. SDK 5.11.2's
# generated-source prelude does not include their types before these definitions.
# Use the SDK's own declarations, keeping their C linkage and native signatures.
if(GEODE_TARGET_PLATFORM STREQUAL "iOS")
    target_compile_options(GeodeBindings PRIVATE
        -include "$ENV{GEODE_SDK}/loader/include/Geode/fmod/fmod.h")
    # This audio-only mod has no GL calls. Do not pull Apple's EAGL classes
    # into an ANGLE session merely because the SDK lists the framework.
    target_link_options(${PROJECT_NAME} PRIVATE -Wl,-dead_strip_dylibs)
endif()
setup_geode_mod(${PROJECT_NAME})
