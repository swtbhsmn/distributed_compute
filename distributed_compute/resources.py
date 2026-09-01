from __future__ import annotations

import os
import time
from pathlib import Path

try:
    import psutil as _psutil
except Exception:  # Android builds of psutil can fail during import, not just installation.
    _psutil = None


PROC_STAT = Path("/proc/stat")
PROC_MEMINFO = Path("/proc/meminfo")


def is_android_termux() -> bool:
    prefix = os.environ.get("PREFIX", "")
    return bool(
        os.environ.get("TERMUX_VERSION")
        or os.environ.get("ANDROID_ROOT")
        or os.environ.get("ANDROID_DATA")
        or "com.termux" in prefix
    )


def os_name() -> str:
    if is_android_termux():
        return "Android/Termux"
    import platform

    return platform.system() or "unknown"


def _read_proc_cpu_times(path: Path = PROC_STAT) -> tuple[int, int] | None:
    try:
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        fields = first_line.split()
        if not fields or fields[0] != "cpu":
            return None
        values = [int(value) for value in fields[1:]]
        if len(values) < 4:
            return None
        total = sum(values)
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return total, idle
    except (OSError, ValueError, IndexError):
        return None


def _cpu_percent_without_psutil(sample_interval: float, cores: int) -> float:
    first = _read_proc_cpu_times()
    if first is not None:
        time.sleep(sample_interval)
        second = _read_proc_cpu_times()
        if second is not None:
            total_delta = second[0] - first[0]
            idle_delta = second[1] - first[1]
            if total_delta > 0:
                return max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta)))
    try:
        one_minute_load = os.getloadavg()[0]
        return max(0.0, min(100.0, 100.0 * one_minute_load / cores))
    except (AttributeError, OSError):
        return 0.0


def _available_ram_from_proc(path: Path = PROC_MEMINFO) -> int | None:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _available_ram_without_psutil() -> int:
    proc_value = _available_ram_from_proc()
    if proc_value is not None:
        return proc_value
    try:
        pages = int(os.sysconf("SC_AVPHYS_PAGES"))
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        return max(0, pages * page_size)
    except (AttributeError, OSError, TypeError, ValueError):
        return 0


def resource_snapshot(sample_interval: float = 0.1) -> dict[str, int | float]:
    cores = os.cpu_count() or 1
    if _psutil is not None:
        try:
            return {
                "logical_cpu_cores": _psutil.cpu_count(logical=True) or cores,
                "available_ram_bytes": max(0, int(_psutil.virtual_memory().available)),
                "cpu_usage_percent": max(
                    0.0,
                    min(100.0, float(_psutil.cpu_percent(interval=sample_interval))),
                ),
            }
        except Exception:
            # A partially working Android psutil package must not prevent startup.
            pass
    return {
        "logical_cpu_cores": cores,
        "available_ram_bytes": _available_ram_without_psutil(),
        "cpu_usage_percent": _cpu_percent_without_psutil(sample_interval, cores),
    }


def resource_backend() -> str:
    return "psutil" if _psutil is not None else "native"
