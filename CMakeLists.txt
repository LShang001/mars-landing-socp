# =============================================================================
# CMakeLists.txt
# ECOS Mars Landing Trajectory Optimization
# Dual-build: AVX / Scalar (Intel N150 / Alder Lake-N optimized)
# =============================================================================

cmake_minimum_required(VERSION 3.15)

project(ecos-cn-n150 C)

# -----------------------------------------------------------------------------
# 1. 基础配置
# -----------------------------------------------------------------------------
set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# 默认 Release
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# -----------------------------------------------------------------------------
# 2. 编译器检测
# -----------------------------------------------------------------------------
if(NOT CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    message(FATAL_ERROR "Only GCC or Clang is supported")
endif()

message(STATUS "Compiler: ${CMAKE_C_COMPILER_ID} ${CMAKE_C_COMPILER_VERSION}")
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")

# -----------------------------------------------------------------------------
# 3. 通用编译选项（数值安全 + 高性能）
# -----------------------------------------------------------------------------
set(COMMON_COMPILE_OPTIONS
    -O3
    -march=native

    # 数值安全（ECOS 必须）
    -fno-finite-math-only
    -fno-unsafe-math-optimizations
    -fno-math-errno

    # 性能/链接
    -fno-semantic-interposition

    # 警告
    -Wall
    -Wextra
    -Wno-unused-parameter
)

# -----------------------------------------------------------------------------
# 4. LTO（Link Time Optimization）
# -----------------------------------------------------------------------------
include(CheckIPOSupported)
check_ipo_supported(RESULT LTO_SUPPORTED OUTPUT LTO_OUTPUT)

if(LTO_SUPPORTED)
    message(STATUS "LTO supported: enabled")
else()
    message(WARNING "LTO not supported: ${LTO_OUTPUT}")
endif()

# -----------------------------------------------------------------------------
# 5. 头文件路径
# -----------------------------------------------------------------------------
include_directories(
    "${PROJECT_SOURCE_DIR}/MarsLanding"
    "${PROJECT_SOURCE_DIR}/ecos/include"
    "${PROJECT_SOURCE_DIR}/ecos/external/SuiteSparse_config"
    "${PROJECT_SOURCE_DIR}/ecos/external/amd/include"
    "${PROJECT_SOURCE_DIR}/ecos/external/ldl/include"
)

# -----------------------------------------------------------------------------
# 6. 源文件
# -----------------------------------------------------------------------------
file(GLOB ECOS_CORE_SOURCES "ecos/src/*.c")
file(GLOB AMD_SOURCES       "ecos/external/amd/src/*.c")
set(LDL_SOURCES             "ecos/external/ldl/src/ldl.c")

set(USER_SOURCES
    "MarsLanding/MarsLanding.c"
    "MarsLanding/CRM2CCM.c"
)

set(ALL_SOURCES
    ${ECOS_CORE_SOURCES}
    ${AMD_SOURCES}
    ${LDL_SOURCES}
    ${USER_SOURCES}
)

# -----------------------------------------------------------------------------
# 7. AVX 版本（低频 / 高 IPC）
# -----------------------------------------------------------------------------
add_executable(ecos_avx ${ALL_SOURCES})

target_compile_options(ecos_avx PRIVATE
    ${COMMON_COMPILE_OPTIONS}
    -mfma
)

target_compile_definitions(ecos_avx PRIVATE
    ECOS_USE_AVX=1
    ECOS_ALIGNMENT=32
    PROFILING=2
    CTRLC=0
)

target_link_libraries(ecos_avx PRIVATE m)

if(LTO_SUPPORTED)
    set_property(TARGET ecos_avx PROPERTY INTERPROCEDURAL_OPTIMIZATION TRUE)
endif()

# -----------------------------------------------------------------------------
# 8. 非 AVX 版本（高频 / 低功耗）
# -----------------------------------------------------------------------------
add_executable(ecos_scalar ${ALL_SOURCES})

target_compile_options(ecos_scalar PRIVATE
    ${COMMON_COMPILE_OPTIONS}
    -mno-avx
    -mno-avx2
    -mno-fma
)

target_compile_definitions(ecos_scalar PRIVATE
    ECOS_USE_AVX=0
    ECOS_ALIGNMENT=32
    PROFILING=2
    CTRLC=0
)

target_link_libraries(ecos_scalar PRIVATE m)

if(LTO_SUPPORTED)
    set_property(TARGET ecos_scalar PROPERTY INTERPROCEDURAL_OPTIMIZATION TRUE)
endif()

# -----------------------------------------------------------------------------
# 9. 输出目录
# -----------------------------------------------------------------------------
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

foreach(t ecos_avx ecos_scalar)
    set_target_properties(${t} PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}
    )
endforeach()

# -----------------------------------------------------------------------------
# 10. 配置摘要
# -----------------------------------------------------------------------------
message(STATUS "--------------------------------------------------")
message(STATUS "Targets:")
message(STATUS "  ecos_avx     : AVX2/FMA enabled (lower freq, high IPC)")
message(STATUS "  ecos_scalar  : AVX disabled (higher freq, lower power)")
message(STATUS "Architecture : Intel Alder Lake-N (Gracemont)")
message(STATUS "Optimization : -O3 -march=native")
message(STATUS "LTO           : ${LTO_SUPPORTED}")
message(STATUS "Output dir    : ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}")
message(STATUS "--------------------------------------------------")
