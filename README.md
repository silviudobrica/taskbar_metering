# Taskbar Metering

A lightweight Windows system-tray application that renders real-time hardware metrics directly alongside the taskbar clock. Built with Python and PySide6.

---

## Features

- **System tray icon** — live metric badges rendered as a custom icon next to the system clock, updating on a configurable interval
- **Flyout dashboard** — click the tray icon to open a translucent overlay panel with circular progress gauges for every active sensor
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
- **Configurable poll rate** — default 5 seconds, stored in `config.json`
- **Launch on Windows startup** — optional registry entry created during installation
- **Standalone mode** — run without installing (no registry entry, no file copy)
- **Graceful uninstall** — removes copied files, startup registry entry, and config directory via IPC shutdown

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

### 3. Install dependencies

```powershell
pip install PySide6 psutil pynvml
```

> `pynvml` is optional. If no NVIDIA GPU is present, GPU sensors will simply show as unavailable.

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

Examples:

```powershell
python main.py --run
python main.py --uninstall
```

---

## Building a Standalone Executable

A PyInstaller spec file is included. Run the helper script to produce a single-file executable in `dist/`:

```powershell
.\build.bat
```

This script:
1. Cleans previous `build/` and `dist/` directories
2. Runs PyInstaller using `taskbar_meter.spec`
3. Outputs `dist\taskbar_meter.exe`

> Requires PyInstaller: `pip install pyinstaller`

The resulting `taskbar_meter.exe` bundles all dependencies and can be distributed without a Python installation.

---

## Installation Wizard

When `taskbar_meter.exe` (or `main.py`) is run for the first time:

1. **Choose an installation folder** — defaults to `%LOCALAPPDATA%\TaskbarMetering`
2. **Select startup option** — optionally register the app to launch on Windows login
3. Click **Install & Launch** — the executable is copied to the chosen folder, the registry startup entry is written, and the tray app starts immediately

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

You can edit this file manually or use the **Settings** dialog accessible from the tray icon right-click menu.

---

## Uninstalling

**From the tray icon:** right-click → *Uninstall* — removes the startup registry entry, copied files, and config directory, then exits.

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
├── main.py              # Entry point; CLI argument handling, app bootstrap
├── tray_app.py          # System tray icon, flyout panel, companion bar, sensor cards
├── metrics.py           # Hardware metric collectors (CPU, RAM, GPU, disk)
├── config.py            # Config load/save, default values, AppData paths
├── installer.py         # Installation wizard UI and uninstall logic
├── taskbar_meter.spec   # PyInstaller build spec
├── build.bat            # Helper script to invoke PyInstaller
└── LICENSE              # Apache License 2.0
```

---

## License

Licensed under the [Apache License 2.0](LICENSE).
