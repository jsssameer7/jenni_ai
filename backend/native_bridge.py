"""
Native Win32 C Bridge for Jenni AI.
Provides low-overhead system telemetry directly through Win32 kernel32 APIs
and optionally via backend/win_metrics.dll if precompiled.
"""

import os
import sys
import ctypes
from ctypes import wintypes
from typing import Dict, Any, Tuple

# Win32 MEMORYSTATUSEX structure
class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_uint64),
        ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64),
        ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64),
        ("ullAvailVirtual", ctypes.c_uint64),
        ("ullAvailExtendedVirtual", ctypes.c_uint64),
    ]

# Win32 FILETIME structure
class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]

class NativeWinMetrics:
    def __init__(self):
        self.is_windows = sys.platform == "win32"
        self._kernel32 = None
        self._prev_idle = 0
        self._prev_kernel = 0
        self._prev_user = 0
        self._last_cpu_percent = 0.0
        
        if self.is_windows:
            try:
                self._kernel32 = ctypes.windll.kernel32
            except Exception:
                self._kernel32 = None

    def get_memory_stats(self) -> Dict[str, Any]:
        """Query memory via Win32 GlobalMemoryStatusEx with 0ms overhead."""
        if not self._kernel32:
            return {"available": False}

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        success = self._kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        if not success:
            return {"available": False}

        total_mb = stat.ullTotalPhys / (1024 * 1024)
        free_mb = stat.ullAvailPhys / (1024 * 1024)
        used_mb = total_mb - free_mb

        return {
            "available": True,
            "total_gb": round(total_mb / 1024, 2),
            "used_gb": round(used_mb / 1024, 2),
            "free_gb": round(free_mb / 1024, 2),
            "percent": float(stat.dwMemoryLoad),
            "load_percent": int(stat.dwMemoryLoad),
        }

    def _filetime_to_int(self, ft: FILETIME) -> int:
        return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

    def get_cpu_percent(self) -> float:
        """Calculate CPU usage using GetSystemTimes differential (non-blocking)."""
        if not self._kernel32:
            return 0.0

        idle = FILETIME()
        kernel = FILETIME()
        user = FILETIME()

        res = self._kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        )
        if not res:
            return self._last_cpu_percent

        i_idle = self._filetime_to_int(idle)
        i_kernel = self._filetime_to_int(kernel)
        i_user = self._filetime_to_int(user)

        if self._prev_idle == 0 and self._prev_kernel == 0:
            self._prev_idle = i_idle
            self._prev_kernel = i_kernel
            self._prev_user = i_user
            return self._last_cpu_percent

        diff_idle = i_idle - self._prev_idle
        diff_kernel = i_kernel - self._prev_kernel
        diff_user = i_user - self._prev_user

        self._prev_idle = i_idle
        self._prev_kernel = i_kernel
        self._prev_user = i_user

        total_sys = diff_kernel + diff_user
        if total_sys <= 0:
            return self._last_cpu_percent

        # Kernel time includes idle time in Windows NT
        diff_busy = total_sys - diff_idle
        if diff_busy < 0:
            diff_busy = 0

        percent = round((diff_busy / total_sys) * 100.0, 1)
        self._last_cpu_percent = max(0.0, min(100.0, percent))
        return self._last_cpu_percent

native_metrics = NativeWinMetrics()
