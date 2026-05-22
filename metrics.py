import os
import subprocess
import psutil

# Initialize NVML for Nvidia GPU stats
nvml_initialized = False
try:
    import pynvml
    pynvml.nvmlInit()
    nvml_initialized = True
except Exception:
    pass

def cleanup_metrics():
    global nvml_initialized
    if nvml_initialized:
        try:
            import pynvml
            pynvml.nvmlShutdown()
        except Exception:
            pass
        nvml_initialized = False

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

def get_disk_usage():
    # Returns a list of dicts: [{"device": "C:", "percent": 35.4}]
    disks = []
    try:
        for part in psutil.disk_partitions(all=False):
            if 'fixed' in part.opts or part.fstype:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disks.append({
                        "device": part.mountpoint.strip("\\"),
                        "percent": usage.percent
                    })
                except Exception:
                    pass
    except Exception:
        pass
    # Default to C: if none found
    if not disks:
        try:
            usage = psutil.disk_usage('C:\\')
            disks.append({"device": "C:", "percent": usage.percent})
        except Exception:
            disks.append({"device": "C:", "percent": 0.0})
    return disks

def get_drive_temp(drive_letter):
    # Get physical disk temperature for the partition drive letter (e.g. "C:" or "D:")
    letter = drive_letter.strip("\\").strip(":").strip()
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        cmd = ["powershell", "-NoProfile", "-Command",
               f"Get-Partition -DriveLetter {letter} | Get-Disk | Get-PhysicalDisk | Get-StorageReliabilityCounter | Select-Object -ExpandProperty Temperature"]
        
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

