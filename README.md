# Taskbar Metering

A lightweight Windows system-tray application that renders real-time hardware metrics directly alongside the taskbar clock. Built with Python and PySide6.

---

## What's New in v1.2.0

- **Administrator elevation support** — installer now offers to run the app as admin for better temperature sensor access
- **Auto-update functionality** — check for new releases from GitHub and automatically upgrade
- **About dialog** — view version info and check for updates directly from the app  
- **Add/Remove Programs support** — app now appears in Windows Settings with current version
- **Improved installer** — better registry entries and program listing
- **Bug fixes** — fixed command-line argument parsing

---

## What's New in v1.1.0

- **Improved CPU temperature detection** — now tries multiple WMI methods (Win32_TemperatureProbe, MSAcpi_ThermalZoneTemperature) with better error handling and logging
- **Enhanced disk temperature detection** — multiple fallback methods for better hardware compatibility
- **Optional WMI module support** — install `pywin32` and `wmi` for faster, more reliable temperature queries
- **Debug logging** — temperature detection failures are now logged to `%LOCALAPPDATA%\TaskbarMetering\logs\app.log` for troubleshooting

---

## Features

- **System tray icon** — live metric badges rendered as a custom icon next to the system clock, updating on a configurable interval
- **Flyout dashboard** — click the tray icon (or press `Ctrl + Shift + M` globally) to open a translucent overlay panel with circular progress gauges and sparkline history for every active sensor
- **Companion bar** — optional compact bar anchored near the taskbar showing all active sensors at a glance (supports compact mode)
- **Sensors supported:**
  - CPU Usage (%)
  - CPU Temperature (°C, via WMI)
  - RAM Usage (%)
  - GPU Usage (%) — NVIDIA only, via NVML
  - GPU Temperature (°C) — NVIDIA only
  - Per-disk Usage (%) — auto-detected for all fixed drives
  - Per-disk Temperature (°C) — via PowerShell Storage API
- **Sensor configuration dialog** — toggle sensors on/off and reorder them with arrow buttons; order is reflected left-to-right on the tray icon
- **Alert thresholds** — configure per-sensor limits; a tray balloon fires (at most once per minute) when a value is exceeded
- **Historical sparklines** — each dashboard card shows a compact 60-sample trend line
- **Global hotkey** — `Ctrl + Shift + M` shows/hides the dashboard from anywhere on the desktop
- **Pause monitoring** — temporarily freeze all polling from the tray right-click menu
- **Configurable poll rate** — default 5 seconds, stored in `config.json`
- **Adjustable tray icon number size** — set from the tray icon right-click menu to improve readability on different displays/taskbar sizes
- **Quick size controls** — right-click actions for fast `+ / -` tray number and companion text scaling
- **Keyboard resizing shortcuts** (when dashboard is focused): `Ctrl + +/-` for tray icon numbers, `Ctrl + Shift + +/-` for companion text
- **On-panel shortcut hint** — the dashboard shows a compact legend for all shortcuts
- **Launch on Windows startup** — optional registry entry created during installation
- **Standalone mode** — run without installing (no registry entry, no file copy)
- **Graceful uninstall** — removes installed files, startup registry entry, Start Menu shortcut, Add/Remove Programs entry, and config directory via IPC shutdown
- **Crash log** — unhandled exceptions are written to `%LOCALAPPDATA%\TaskbarMetering\logs\app.log`
- **Per-Monitor V2 DPI awareness** — crisp rendering on mixed-DPI multi-monitor setups (compiled build)

---

## Requirements

- Windows 10 / 11 (64-bit)
- Python 3.10 or newer (for running from source)
- NVIDIA GPU (optional) — required only for GPU metrics

---

## Running from Source

### 1. Clone the repository

```bash
git clone https://github.com/SilviuDobrica/taskbar_metering.git
cd taskbar_metering
```

### 2. Create and activate a virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

> `build.bat` also auto-detects a `.venv` folder if you prefer that name.

### 3. Install dependencies

```powershell
pip install PySide6 psutil pynvml
```

> `pynvml` is optional. If no NVIDIA GPU is present, GPU sensors will simply show as unavailable.
>
> For improved CPU and disk temperature detection, also install the WMI module:
> ```powershell
> pip install pywin32 wmi
> ```
> If `wmi` is not installed, the app will fall back to PowerShell WMI queries, which are slower and less reliable.

### 4. Launch the application

```powershell
python main.py
```

On first run the installation wizard will appear. You can choose to **Install & Launch** (copies the executable, registers a startup entry) or **Run Standalone** (skips installation and goes straight to the tray).

---

## Command-line Options

| Flag | Description |
|---|---|
| *(none)* | Auto-detect: show installer on first run, go to tray if already installed |
| `--run` | Skip the installer and launch directly to the system tray |
| `--install` | Force the installation wizard to open |
| `--uninstall` | Remove the application, startup entry, and configuration |
| `--version` | Print the application version and exit |

Examples:

```powershell
python main.py --run
python main.py --uninstall
```

---

## Building a Standalone Executable

Run the helper script to produce a single-file executable in `dist/`:

```powershell
.\build.bat
```

This script:
1. Cleans previous `build/` and `dist/` directories
2. Runs PyInstaller using `taskbar_meter.spec` when present, otherwise falls back to building from `main.py`
3. Outputs `dist\taskbar_meter.exe`

> Requires PyInstaller: `pip install pyinstaller`

The resulting `taskbar_meter.exe` bundles all dependencies and can be distributed without a Python installation.

---

## Installation Wizard

When `taskbar_meter.exe` (or `main.py`) is run for the first time:

1. **Choose an installation folder** — defaults to `%LOCALAPPDATA%\TaskbarMetering`
2. **Select startup option** — optionally register the app to launch on Windows login
3. Click **Install & Launch** — the executable is copied to the chosen folder, and the following are created:
   - Registry startup entry (if selected)
   - Start Menu shortcut (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Taskbar Metering.lnk`)
   - Add/Remove Programs entry (`HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\TaskbarMetering`)

To skip installation entirely, click **Run Standalone (No Install)**.

---

## Configuration

Settings are stored in `%LOCALAPPDATA%\TaskbarMetering\config.json`.

| Key | Default | Description |
|---|---|---|
| `active_sensors` | `["cpu_usage", "ram_usage"]` | Ordered list of enabled sensor keys |
| `poll_rate` | `5` | Metric refresh interval in seconds |
| `installed` | `false` | Set to `true` after installation |
| `launch_on_startup` | `true` | Whether a Windows startup entry exists |
| `show_companion_bar` | `true` | Show the anchored companion bar |
| `companion_compact_mode` | `false` | Use compact layout for the companion bar |
| `tray_icon_font_size` | `10` | Font size (pt) for numeric values rendered inside each tray icon (8-24) |
| `companion_font_size` | `11` | Font size (pt) for the text shown in the companion bar |
| `thresholds` | `{}` | Per-sensor alert limits, e.g. `{"cpu_usage": 90}` — 0 or absent means disabled |
| `hotkey_enabled` | `true` | Whether `Ctrl + Shift + M` global hotkey is registered |

You can edit this file manually or use the **Settings** dialog accessible from the tray icon right-click menu.

---

## Uninstalling

**From the tray icon:** right-click → *Uninstall* — removes the following, then exits:
- Startup registry entry
- Start Menu shortcut
- Add/Remove Programs registry entry
- Installed application files
- Config directory (`%LOCALAPPDATA%\TaskbarMetering`)

**From the command line:**

```powershell
taskbar_meter.exe --uninstall
# or from source:
python main.py --uninstall
```

---

## Project Structure

```
taskbar_metering/
├── main.py              # Entry point; CLI argument handling, logging setup, app bootstrap
├── tray_app.py          # System tray icon, flyout panel, companion bar, sensor cards, sparklines
├── metrics.py           # Hardware metric collectors (CPU, RAM, GPU, disk)
├── config.py            # Config load/save, default values, AppData paths, APP_VERSION
├── installer.py         # Installation wizard UI and uninstall logic
├── app.manifest         # Per-Monitor V2 DPI awareness manifest (embedded by PyInstaller)
├── taskbar_meter.spec   # PyInstaller build spec (references app.manifest)
├── build.bat            # Helper script to invoke PyInstaller
└── LICENSE              # Apache License 2.0
```

---

## License

Licensed under the [Apache License 2.0](LICENSE).
