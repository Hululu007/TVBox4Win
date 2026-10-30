cmake_minimum_required(VERSION 3.16)
project(tvbox2exe C)

set(CMAKE_C_STANDARD 11)

add_executable(tvbox WIN32
    src/main.c
    src/http.c
    src/tvbox.c
    third_party/cjson/cJSON.c
)

target_include_directories(tvbox PRIVATE
    src
    third_party/cjson
    third_party/mpv/include
)

target_link_libraries(tvbox PRIVATE
    ${CMAKE_SOURCE_DIR}/third_party/mpv/libmpv.dll.a
    winhttp
    comctl32
    shlwapi
)

if(MINGW)
    target_link_options(tvbox PRIVATE -municode -static-libgcc)
endif()

# Copy runtime DLL next to exe after build
add_custom_command(TARGET tvbox POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${CMAKE_SOURCE_DIR}/third_party/mpv/libmpv-2.dll
        $<TARGET_FILE_DIR:tvbox>/libmpv-2.dll
)
