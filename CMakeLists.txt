cmake_minimum_required(VERSION 3.16)
project(blender_cpp_hub)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_BUILD_TYPE Release)

# Shared library — loaded by Blender's Python via ctypes
add_library(hub_core SHARED hub_core.cpp)

target_compile_options(hub_core PRIVATE
    -O3 -ffast-math -fvisibility=default
    -Wall -Wno-deprecated-declarations
)

set_target_properties(hub_core PROPERTIES
    OUTPUT_NAME "hub_core"
    PREFIX      ""
    SUFFIX      ".dylib"
)

# Install next to the Blender add-on
install(TARGETS hub_core DESTINATION ${CMAKE_SOURCE_DIR})
