# Release Notes — Taskbar Metering v1.3.0

**Release Date:** June 26, 2026

---

## ✨ Highlights

This release brings a **major telemetry architecture overhaul**, switching from multi-source polling (WMI, PowerShell, DeepCool APIs) to a **unified HWiNFO-only backend** via shared memory, resulting in cleaner code, faster reads, and better hardware compatibility.

---

## 🔧 What's New

### HWiNFO Unified Backend

- **Single telemetry source** — all CPU, disk, RAM, and GPU temperature readings now flow through HWiNFO shared memory (Global\HWiNFO_SENS_SM2)
- **No more multi-source polling** — removed complex fallback chains and WMI queries that often conflicted
- **Requires HWiNFO64** — user must run HWiNFO64 with shared memory support enabled (Settings → Misc. Options → Shared Memory Support)
- **434 sensors on test hardware** — real-time access to all HWiNFO-detected sensors without subprocess overhead

### Dependency Reduction

- **Removed `pywin32` and `wmi` modules** — no longer needed for temperature queries; now optional
- **Removed DeepCool sensor parsing** — simplified configuration footprint
- **Removed PowerShell temperature subprocess calls** — direct ctypes Win32 API bindings instead
- **Core dependencies now: PySide6, psutil, pynvml** — total installation size reduced

### Improved CPU Temperature Selection

- **Motherboard PECI sensors prioritized** — on ASUS boards, correctly selects "CPU (PECI)" from the motherboard section (e.g., ASUS X870 MAX Gaming WIFI7)
- **Smarter scoring algorithm** — ASUS CPU (PECI) gets highest priority (320), followed by calibrated PECI (300), then generic PECI (290)
- **Better AMD/Intel compatibility** — detects Tctl/Tdie for AMD Ryzen, PECI for Intel systems

### Technical Improvements

- **Shared memory reader class** (`_HwinfoSharedMemoryReader`) — handles SM2 binary parsing with proper ctypes bindings
- **Direct memory mapping** — uses Win32 `OpenFileMappingW`, `MapViewOfFile`, `UnmapViewOfFile` for zero-copy sensor access
- **Cached readings with TTL** — 1-second cache with thread-safe locking prevents excessive memory mapping cycles
- **Fallback support** — detects both SM2 and SM variants of HWiNFO shared memory

---

## 🐛 Bug Fixes

- Fixed CPU temperature detection returning 0 values with WMI timeouts
- Fixed GPU memory junction temperature being classified as RAM DIMM temperature
- Fixed application startup behavior under high sensor loads
- Improved handling of missing or malformed HWiNFO shared memory

---

## ⚠️ Breaking Changes

**HWiNFO64 is now required.** If you don't have it installed:
1. Download from [HWiNFO download page](https://www.hwinfo.com/download/)
2. Run HWiNFO64.exe (portable version works fine)
3. Enable Settings → Misc. Options → Shared Memory Support
4. Keep HWiNFO running while using Taskbar Metering

The app will show unavailable sensors if HWiNFO is not running.

---

## 📋 Installation & Upgrade

### Fresh Install (v1.3.0)

```powershell
python main.py
# or
dist/taskbar_meter.exe
```

The installer will guide you through standard setup.

### Upgrading from v1.2.0

1. Close the app via tray icon
2. Run new `dist/taskbar_meter.exe` or `python main.py`
3. Configuration from v1.2.0 will be preserved
4. **Install HWiNFO64** if you don't have it
5. Enable HWiNFO's shared memory support
6. Restart the app

---

## ⚙️ System Requirements

- Windows 10 / 11 (64-bit)
- **HWiNFO64** (with shared memory support enabled)
- Python 3.10+ (for running from source)
- NVIDIA GPU (optional, for GPU metrics)

---

## 🔍 Troubleshooting

### "No HWiNFO shared memory found"

- Verify HWiNFO64.exe is running
- In HWiNFO → Settings → Misc. Options → enable **Shared Memory Support**
- Restart HWiNFO64 after enabling

### CPU temperature shows 0°C or "Unavailable"

- Check HWiNFO sensor list for available CPU temperature readings
- Ensure motherboard PECI or Tctl/Tdie sensor is present
- Verify HWiNFO is reading temps correctly in its main window

### Disk temperatures not updating

- Ensure HWiNFO detects your NVMe/SATA drives (visible in its sensor list)
- Some M.2 drives may not expose temperature via SMART; check HWiNFO logs

---

## 🙏 Thank You

Thanks for using Taskbar Metering! HWiNFO integration feedback and bug reports are welcome on [GitHub](https://github.com/SilviuDobrica/taskbar_metering).

---

## 📄 License

Licensed under [Apache License 2.0](LICENSE).

---

---

# Release Notes — Taskbar Metering v1.2.0

**Release Date:** June 26, 2026

---

## ✨ Highlights

This release brings **installer improvements**, **auto-update functionality**, and **better Windows integration** for a more professional user experience.

---

## 🔧 What's New

### Administrator Elevation

- **Installation wizard** now offers to run the app as administrator after installation
- Better access to system temperature sensors when running elevated
- Temperature readings work properly on systems with proper drivers

### Auto-Update Support

- **Check for Updates** button in About dialog
- Automatically downloads latest release from GitHub
- Seamless upgrade without manual installation:
  - Kills running processes gracefully
  - Backs up current version
  - Replaces executable with retry logic for locked files
  - Restores backup if upgrade fails
  - Automatically restarts the app

### About Dialog Enhancements

- New **Check for Updates** button
- Displays current version
- Direct link to GitHub repository
- Styled dark theme UI

### Windows Integration

- App now appears in **Settings → Apps → Installed apps** with:
  - Display name and version
  - Uninstall option
  - Installation location
- Registry entries properly maintained during installation/uninstallation

### Command-Line Argument Fixes

- Fixed `parse_args()` to properly reject invalid arguments
- Better error messages for typos in CLI flags

---

## 🐛 Bug Fixes

- Fixed command-line argument parsing (was silently ignoring unknown args)
- Improved uninstaller registry handling
- Better error handling during update process

---

## 📋 Installation & Setup

### Fresh Install

```powershell
python main.py
# or
dist/taskbar_meter.exe
```

The installer will guide you through:
1. Choosing installation folder
2. Optional startup on login
3. **NEW**: Option to run as administrator

### Upgrading from v1.1.0

Simply run the executable. It will:
1. Show the installer if not installed
2. Launch to tray if already installed

Or use the **Check for Updates** button in the About dialog:
- Tray icon (right-click) → **About Taskbar Metering...**
- Click **Check for Updates**

---

## 🔄 Auto-Update Workflow

1. User clicks "Check for Updates" in About dialog
2. App queries GitHub API for latest release
3. If newer version found:
   - Downloads latest `taskbar_meter.exe`
   - Kills running processes
   - Backs up current version
   - Replaces with new version
   - Restarts application
4. If update fails, restores from backup

### Error Handling

- Retry logic for locked executable files (up to 5 retries)
- Automatic backup and restore on failure
- Graceful fallback to manual download if upgrade fails
- User-friendly error messages

---

## ⚙️ System Requirements

- Windows 10 / 11 (64-bit)
- .NET runtime (if running from source)
- Administrator privileges (optional, but recommended for temperature sensors)

---

## 🙏 Thank You

Thanks for using Taskbar Metering! Feedback and feature requests are always welcome on [GitHub](https://github.com/SilviuDobrica/taskbar_metering).

---

## 📄 License

Licensed under [Apache License 2.0](LICENSE).
