cmake_minimum_required(VERSION 3.16)

# The application version is baked into esp_app_desc_t and is what the device
# reports and what OTA validates. Pass -DXIAOYI_FW_VERSION=x.y.z to build a release.
if(NOT DEFINED XIAOYI_FW_VERSION)
    set(XIAOYI_FW_VERSION "1.3.1")
endif()
set(PROJECT_VER "${XIAOYI_FW_VERSION}")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(xiaoyi-node)
