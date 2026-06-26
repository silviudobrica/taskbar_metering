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
