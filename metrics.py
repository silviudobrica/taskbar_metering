import ctypes
import json
import logging
import re
import struct
import subprocess
import threading
import time

import psutil

# Initialize NVML for Nvidia GPU stats
nvml_initialized = False
try:
    import pynvml

    pynvml.nvmlInit()
    nvml_initialized = True
except Exception:
    pass

logger = logging.getLogger(__name__)


class _HwinfoSharedMemoryReader:
    """Best-effort reader for HWiNFO shared memory (SM2 / SM)."""

    FILE_MAP_READ = 0x0004
    MAPPING_NAMES = [
        "Global\\HWiNFO_SENS_SM2",
        "Global\\HWiNFO_SENS_SM",
    ]
    SIGNATURE = 0x48574953  # 'HWiS'

    def __init__(self):
        self._cache_readings = []
        self._cache_ts = 0.0
        self._cache_ttl = 1.0
        self._lock = threading.Lock()

    def get_readings(self):
        with self._lock:
            now = time.time()
            if (now - self._cache_ts) <= self._cache_ttl and self._cache_readings:
                return self._cache_readings

            parsed = []
            for name in self.MAPPING_NAMES:
                blob = self._read_mapping_blob(name)
                if not blob:
                    continue
                parsed = self._parse_blob(blob)
                if parsed:
                    break

            self._cache_readings = parsed
            self._cache_ts = now
            return parsed

    def _read_mapping_blob(self, map_name):
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.OpenFileMappingW.restype = ctypes.c_void_p
        kernel32.MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t]
        kernel32.MapViewOfFile.restype = ctypes.c_void_p
        kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        kernel32.UnmapViewOfFile.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int

        h_map = kernel32.OpenFileMappingW(self.FILE_MAP_READ, 0, map_name)
        if not h_map:
            return None

        p_view = None
        try:
            p_view = kernel32.MapViewOfFile(h_map, self.FILE_MAP_READ, 0, 0, 0)
            if not p_view:
                return None

            # Read a generous slice. The mapping is small in practice.
            return ctypes.string_at(p_view, 2 * 1024 * 1024)
        except Exception:
            return None
        finally:
            if p_view:
                kernel32.UnmapViewOfFile(p_view)
            kernel32.CloseHandle(h_map)

    def _parse_blob(self, blob):
        if len(blob) < 44:
            return []

        try:
            h = struct.unpack_from("<IIIqIIIIII", blob, 0)
        except struct.error:
            return []

        sig = h[0]
        offset_sensor = h[4]
        size_sensor = h[5]
        num_sensor = h[6]
        offset_read = h[7]
        size_read = h[8]
        num_read = h[9]

        if sig not in (self.SIGNATURE, 0):
            logger.debug("Unexpected HWiNFO shared memory signature: 0x%08X", sig)

        if not self._header_bounds_ok(len(blob), offset_sensor, size_sensor, num_sensor, offset_read, size_read, num_read):
            return []

        readings = self._parse_sm2_like(blob, offset_sensor, size_sensor, num_sensor, offset_read, size_read, num_read)
        if readings:
            return readings
        return self._parse_classic(blob, offset_sensor, size_sensor, num_sensor, offset_read, size_read, num_read)

    def _header_bounds_ok(self, blob_len, offset_sensor, size_sensor, num_sensor, offset_read, size_read, num_read):
        if size_sensor <= 0 or size_read <= 0:
            return False
        if num_sensor < 0 or num_sensor > 2048:
            return False
        if num_read < 0 or num_read > 20000:
            return False

        end_sensor = offset_sensor + (size_sensor * num_sensor)
        end_read = offset_read + (size_read * num_read)
        if offset_sensor < 0 or offset_read < 0:
            return False
        if end_sensor <= 0 or end_read <= 0:
            return False
        if end_sensor > blob_len or end_read > blob_len:
            return False
        return True

    def _decode_utf16z(self, raw_bytes):
        if not raw_bytes:
            return ""
        try:
            return raw_bytes.decode("utf-16-le", errors="ignore").split("\x00", 1)[0].strip()
        except Exception:
            return ""

    def _decode_ascii_z(self, raw_bytes):
        if not raw_bytes:
            return ""
        try:
            return raw_bytes.decode("ascii", errors="ignore").split("\x00", 1)[0].strip()
        except Exception:
            return ""

    def _parse_classic(self, blob, offset_sensor, size_sensor, num_sensor, offset_read, size_read, num_read):
        sensors = []
        for i in range(num_sensor):
            base = offset_sensor + (i * size_sensor)
            chunk = blob[base : base + size_sensor]
            if len(chunk) < 8:
                sensors.append("")
                continue

            # HWiNFO SM2 currently exposes classic sensor names in ANSI buffers.
            name_orig = self._decode_ascii_z(chunk[8 : 8 + 128])
            name_user = self._decode_ascii_z(chunk[136 : 136 + 128])
            if not name_orig and len(chunk) >= 520:
                # Fallback for UTF-16 variants.
                name_orig = self._decode_utf16z(chunk[8 : 8 + 256])
                name_user = self._decode_utf16z(chunk[264 : 264 + 256])
            sensors.append(name_user or name_orig)

        readings = []
        for i in range(num_read):
            base = offset_read + (i * size_read)
            chunk = blob[base : base + size_read]
            if len(chunk) < 316:
                continue

            parsed = self._parse_classic_reading(chunk)
            if not parsed:
                continue

            sensor_idx = parsed["sensor_index"]
            sensor_name = sensors[sensor_idx] if 0 <= sensor_idx < len(sensors) else ""
            parsed["sensor"] = sensor_name
            readings.append(parsed)

        return readings

    def _parse_classic_reading(self, chunk):
        # Live HWiNFO SM2 layout observed on this system:
        # [u32 id][u32 sensor_idx][u32 sensor_inst]
        # [char label_orig[128]][char label_user[128]][char unit[16]]
        # [double value][double min][double max][double avg] ...
        if len(chunk) >= 316:
            try:
                _, sensor_idx, _ = struct.unpack_from("<III", chunk, 0)

                label_orig = self._decode_ascii_z(chunk[12 : 12 + 128])
                label_user = self._decode_ascii_z(chunk[140 : 140 + 128])
                unit = self._decode_ascii_z(chunk[268 : 268 + 16])
                value = struct.unpack_from("<d", chunk, 284)[0]

                return {
                    "sensor_index": int(sensor_idx),
                    "label": label_user or label_orig,
                    "unit": unit,
                    "value": float(value),
                }
            except Exception:
                pass

        if len(chunk) >= 588:
            try:
                # Fallback for UTF-16 variants.
                _, sensor_idx, _ = struct.unpack_from("<III", chunk, 0)
                label_orig = self._decode_utf16z(chunk[12 : 12 + 256])
                label_user = self._decode_utf16z(chunk[268 : 268 + 256])
                unit = self._decode_utf16z(chunk[524 : 524 + 32])
                value, _, _, _ = struct.unpack_from("<dddd", chunk, 556)
                return {
                    "sensor_index": int(sensor_idx),
                    "label": label_user or label_orig,
                    "unit": unit,
                    "value": float(value),
                }
            except Exception:
                pass

        return None

    def _parse_sm2_like(self, blob, offset_sensor, size_sensor, num_sensor, offset_read, size_read, num_read):
        if len(blob) < 56:
            return []

        try:
            h2 = struct.unpack_from("<IIIqIIIIIIIII", blob, 0)
            offset_str = h2[10]
            size_str = h2[11]
            num_str = h2[12]
        except struct.error:
            return []

        if size_str <= 0 or num_str <= 0:
            return []

        if (offset_str + (size_str * num_str)) > len(blob):
            return []

        def resolve_string(ref):
            if ref <= 0:
                return ""
            candidates = [
                offset_str + ref,
                ref,
                offset_str + (ref * size_str),
            ]
            for c in candidates:
                if c < offset_str or c >= len(blob):
                    continue
                max_len = min(size_str, len(blob) - c)
                text = self._decode_utf16z(blob[c : c + max_len])
                if text:
                    return text
            return ""

        sensors = []
        for i in range(num_sensor):
            base = offset_sensor + (i * size_sensor)
            chunk = blob[base : base + size_sensor]
            if len(chunk) < 16:
                sensors.append("")
                continue
            try:
                _, _, name_orig_ref, name_user_ref = struct.unpack_from("<IIII", chunk, 0)
                name_orig = resolve_string(name_orig_ref)
                name_user = resolve_string(name_user_ref)
                sensors.append(name_user or name_orig)
            except Exception:
                sensors.append("")

        readings = []
        for i in range(num_read):
            base = offset_read + (i * size_read)
            chunk = blob[base : base + size_read]
            if len(chunk) < 40:
                continue

            parsed = self._parse_sm2_reading(chunk, resolve_string)
            if not parsed:
                continue

            sensor_idx = parsed["sensor_index"]
            parsed["sensor"] = sensors[sensor_idx] if 0 <= sensor_idx < len(sensors) else ""
            readings.append(parsed)

        return readings

    def _parse_sm2_reading(self, chunk, resolve_string):
        try:
            dwords = struct.unpack_from("<IIIIIII", chunk, 0)
        except struct.error:
            return None

        sensor_idx = int(dwords[1])
        label_orig_ref = int(dwords[4])
        label_user_ref = int(dwords[5])
        unit_ref = int(dwords[6])

        value = None
        for value_offset in (28, 32):
            if (value_offset + 32) > len(chunk):
                continue
            try:
                v, _, _, _ = struct.unpack_from("<dddd", chunk, value_offset)
                if not (-10000.0 < v < 10000.0):
                    continue
                value = float(v)
                break
            except Exception:
                continue

        if value is None:
            return None

        label_orig = resolve_string(label_orig_ref)
        label_user = resolve_string(label_user_ref)
        unit = resolve_string(unit_ref)

        if not unit and unit_ref > 0:
            c = unit_ref
            if 0 <= c < len(chunk):
                unit = self._decode_ascii_z(chunk[c : c + 16])

        return {
            "sensor_index": sensor_idx,
            "label": label_user or label_orig,
            "unit": unit,
            "value": value,
        }


_hwinfo_reader = _HwinfoSharedMemoryReader()

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


def _get_hwinfo_readings():
    return _hwinfo_reader.get_readings()


def _is_temp_reading(reading):
    unit = str(reading.get("unit", "")).strip().upper()
    if unit in ("C", "°C"):
        return True
    label_l = str(reading.get("label", "")).lower()
    return "temp" in label_l or "temperature" in label_l or "tdie" in label_l or "tctl" in label_l


def _normalize_temp(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not (0.0 < v < 150.0):
        return None
    return round(v, 1)


def _score_cpu_temp(label_l, sensor_l):
    name = f"{sensor_l} {label_l}"
    if "asus" in sensor_l and "cpu (peci)" in label_l:
        return 320
    if "cpu (peci calibrated)" in name:
        return 300
    if "cpu (peci)" in name or name.endswith("peci"):
        return 290
    if "tctl" in name or "tdie" in name:
        return 250
    if "tsi0" in name and "cpu" in name:
        return 280
    if "cpu package" in name:
        return 260
    if "cpu die (average)" in name:
        return 240
    if label_l == "cpu":
        return 180
    if "cpu" in name:
        return 170
    return -1


def get_cpu_usage():
    try:
        return psutil.cpu_percent(interval=None)
    except Exception:
        return 0.0


def get_cpu_temp():
    readings = _get_hwinfo_readings()
    best = None

    for r in readings:
        if not _is_temp_reading(r):
            continue

        label_l = str(r.get("label", "")).strip().lower()
        sensor_l = str(r.get("sensor", "")).strip().lower()
        score = _score_cpu_temp(label_l, sensor_l)
        if score < 0:
            continue

        temp = _normalize_temp(r.get("value"))
        if temp is None:
            continue

        if best is None or score > best[0]:
            best = (score, temp)

    if best is not None:
        return best[1]

    logger.warning("HWiNFO temperature source unavailable: CPU temperature not found")
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
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "while($true) { Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk | Select-Object Name, PercentIdleTime | ConvertTo-Json -Compress; Start-Sleep -Seconds 1 }",
        ]

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
                    idle = float(item.get("PercentIdleTime", 100))
                    busy = max(0.0, min(100.0, 100.0 - idle))
                    disks.append({"device": name, "percent": round(busy, 1)})

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

        for _ in range(20):
            if _disk_usage_cache:
                break
            time.sleep(0.1)

    return _disk_usage_cache


def _score_disk_temp(label_l):
    if "drive temperature 2" in label_l:
        return 110
    if "drive temperature" in label_l:
        return 100
    if "temperature 2" in label_l:
        return 90
    return 80


def get_drive_temp(device_name):
    readings = _get_hwinfo_readings()

    drive_letters = set(re.findall(r"\b([A-Z]):", str(device_name).upper()))
    disk_num_match = re.search(r"^(\d+)", str(device_name).strip())
    disk_num = disk_num_match.group(1) if disk_num_match else None

    best = None
    for r in readings:
        if not _is_temp_reading(r):
            continue

        label = str(r.get("label", ""))
        sensor = str(r.get("sensor", ""))
        text_u = f"{sensor} {label}".upper()
        label_l = label.lower()

        matched = False
        if drive_letters:
            for letter in drive_letters:
                if f"[{letter}:" in text_u or f" {letter}:" in text_u:
                    matched = True
                    break
        if not matched and disk_num and f"DISK {disk_num}" in text_u:
            matched = True
        if not matched:
            continue

        temp = _normalize_temp(r.get("value"))
        if temp is None:
            continue

        score = _score_disk_temp(label_l)
        if best is None or score > best[0]:
            best = (score, temp)

    if best is not None:
        return best[1]

    logger.warning("HWiNFO temperature source unavailable: disk temperature not found for %s", device_name)
    return None


def get_ram_temperatures():
    # Return list like: [{"label": "DIMM #1", "temp": 41.0}, ...]
    readings = _get_hwinfo_readings()
    dimm_map = {}

    for r in readings:
        if not _is_temp_reading(r):
            continue

        label = str(r.get("label", ""))
        sensor = str(r.get("sensor", ""))
        name_l = f"{sensor} {label}".lower()

        if "gpu" in name_l:
            continue

        if "dimm" not in name_l and "ddr" not in name_l and "dram" not in name_l and "memory" not in name_l:
            continue

        temp = _normalize_temp(r.get("value"))
        if temp is None:
            continue

        m = re.search(r"dimm\s*#?\s*(\d+)", name_l)
        if m:
            idx = int(m.group(1))
            dimm_map[idx] = {"label": f"DIMM #{idx}", "temp": temp}
            continue

        # Fallback bucket for memory sensors without clear DIMM index.
        idx = 999
        if idx not in dimm_map:
            dimm_map[idx] = {"label": label or sensor or "RAM", "temp": temp}

    ordered = [dimm_map[k] for k in sorted(dimm_map.keys())]
    return ordered
