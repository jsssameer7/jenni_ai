// win_metrics.c
// High-Performance Native Win32 System Metrics C Bridge for Jenni AI
// Compiled as a DLL or callable via Win32 ctypes in Python.

#include <windows.h>

#ifdef __cplusplus
extern "C" {
#endif

// Fast memory stats directly from Windows Kernel
__declspec(dllexport) void get_memory_stats(unsigned long long* total_mb, unsigned long long* free_mb, unsigned long long* used_mb, unsigned int* load_percent) {
    MEMORYSTATUSEX memInfo;
    memInfo.dwLength = sizeof(MEMORYSTATUSEX);
    if (GlobalMemoryStatusEx(&memInfo)) {
        if (total_mb) *total_mb = memInfo.ullTotalPhys / (1024 * 1024);
        if (free_mb) *free_mb = memInfo.ullAvailPhys / (1024 * 1024);
        if (used_mb) *used_mb = (memInfo.ullTotalPhys - memInfo.ullAvailPhys) / (1024 * 1024);
        if (load_percent) *load_percent = memInfo.dwMemoryLoad;
    }
}

// Low-overhead CPU time query via Win32 GetSystemTimes
__declspec(dllexport) int get_cpu_times(unsigned long long* idle_time, unsigned long long* kernel_time, unsigned long long* user_time) {
    FILETIME idle, kernel, user;
    if (GetSystemTimes(&idle, &kernel, &user)) {
        ULARGE_INTEGER li_idle, li_kernel, li_user;
        li_idle.LowPart = idle.dwLowDateTime;
        li_idle.HighPart = idle.dwHighDateTime;
        li_kernel.LowPart = kernel.dwLowDateTime;
        li_kernel.HighPart = kernel.dwHighDateTime;
        li_user.LowPart = user.dwLowDateTime;
        li_user.HighPart = user.dwHighDateTime;

        if (idle_time) *idle_time = li_idle.QuadPart;
        if (kernel_time) *kernel_time = li_kernel.QuadPart;
        if (user_time) *user_time = li_user.QuadPart;
        return 1;
    }
    return 0;
}

#ifdef __cplusplus
}
#endif
