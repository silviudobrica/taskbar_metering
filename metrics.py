import os
import subprocess
import psutil
import threading
import json

# Initialize NVML for Nvidia GPU stats
nvml_initialized = False
try:
    import pynvml
    pynvml.nvmlInit()
    nvml_initialized = True
except Exception:
    pass

_disk_usage_cache = []
_disk_usage_thread = None
_disk_usage_proc = None

def cleanup_metrics():
    global nvml_initialized, _disk_usage_proc
    if nvml_initialized:
        try:
            import pynvml
            pynvml.nvmlShutdown()
        except Exception:
            pass
        nvml_initialized = False
        
    if _disk_usage_proc is not None:
        try:
            _disk_usage_proc.kill()
        except Exception:
            pass
        _disk_usage_proc = None

def get_cpu_usage():
    try:
        # non-blocking CPU percentage call
        return psutil.cpu_percent(interval=None)
    except Exception:
        return 0.0

def get_cpu_temp():
    # Reading CPU temperature on Windows without admin is extremely restricted.
    # We will attempt a PowerShell query to MSAcpi_ThermalZoneTemperature (WMI).
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        # Query WMI via PowerShell (tenth of Kelvin units)
        cmd = ["powershell", "-NoProfile", "-Command", 
               "Get-CimInstance -Namespace root/wmi -ClassName MsAcpi_ThermalZoneTemperature | Select-Object -ExpandProperty CurrentTemperature"]
        
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5, startupinfo=startupinfo)
        if proc.returncode == 0 and proc.stdout.strip():
            # WMI returns values in tenths of Kelvin. Convert to Celsius.
            # Example: 3000 -> 300K -> 26.85C
            try:
                raw_temp = float(proc.stdout.strip())
                cel_temp = (raw_temp / 10.0) - 273.15
                if 0 < cel_temp < 150: # sensible limits
                    return round(cel_temp, 1)
            except ValueError:
                pass
    except Exception:
        pass
    return None

def get_ram_usage():
    try:
        return psutil.virtual_memory().percent
    except Exception:
        return 0.0

def get_gpu_metrics():
    # Returns (usage_percentage, temperature_celsius) or (None, None)
    if not nvml_initialized:
        return None, None
    try:
        import pynvml
        device_count = pynvml.nvmlDeviceGetCount()
        if device_count > 0:
            # Monitor the primary GPU (index 0)
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            return util.gpu, temp
    except Exception:
        pass
    return None, None

def _update_disk_usage():
    global _disk_usage_cache, _disk_usage_proc
    try:
        cmd = ["powershell", "-NoProfile", "-Command",
               "while($true) { Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk | Select-Object Name, PercentDiskTime | ConvertTo-Json -Compress; Start-Sleep -Seconds 1 }"]
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        _disk_usage_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, startupinfo=startupinfo)
        
        for line in _disk_usage_proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    data = [data]
                
                disks = []
                for item in data:
                    name = item.get("Name", "")
                    if name == "_Total":
                        continue
                    val = item.get("PercentDiskTime", 0)
                    # Name is usually something like "0 C: D:"
                    disks.append({
                        "device": name,
                        "percent": float(val)
                    })
                
                if disks:
                    _disk_usage_cache = disks
            except Exception:
                pass
    except Exception:
        pass

def get_disk_usage():
    # Returns a list of dicts: [{"device": "0 C: D:", "percent": 35.4}]
    global _disk_usage_thread, _disk_usage_cache
    if _disk_usage_thread is None or not _disk_usage_thread.is_alive():
        _disk_usage_thread = threading.Thread(target=_update_disk_usage, daemon=True)
        _disk_usage_thread.start()
        
        # Block until the first result is populated
        import time
        for _ in range(20):
            if _disk_usage_cache:
                break
            time.sleep(0.1)
        
    return _disk_usage_cache

def get_drive_temp(device_name):
    import re
    # Extract the disk number (first integer in the string, e.g. "0 C: D:")
    match = re.search(r'^(\d+)', device_name)
    if not match:
        return None
    disk_num = match.group(1)
    
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        cmd = ["powershell", "-NoProfile", "-Command",
               f"Get-PhysicalDisk | Where-Object DeviceId -eq {disk_num} | Get-StorageReliabilityCounter | Select-Object -ExpandProperty Temperature"]
        
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5, startupinfo=startupinfo)
        if proc.returncode == 0 and proc.stdout.strip():
            temp_str = proc.stdout.strip()
            # If multiple devices or lines returned, take the first non-zero number
            for val in temp_str.split():
                if val.isdigit() and val != "0":
                    temp_val = float(val)
                    if 0 < temp_val < 120:
                        return temp_val
    except Exception:
        pass
    return None

