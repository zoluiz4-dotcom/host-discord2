import time

import psutil


def get_system_stats() -> dict:
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    boot_time = psutil.boot_time()

    return {
        "cpu_percent": cpu,
        "ram_percent": mem.percent,
        "ram_used_mb": mem.used / (1024 * 1024),
        "ram_total_mb": mem.total / (1024 * 1024),
        "disk_percent": disk.percent,
        "disk_used_gb": disk.used / (1024 * 1024 * 1024),
        "disk_total_gb": disk.total / (1024 * 1024 * 1024),
        "server_uptime_seconds": time.time() - boot_time,
    }
