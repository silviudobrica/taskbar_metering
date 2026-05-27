@echo off
echo ====================================================
echo Building Taskbar Metering Executable via PyInstaller
echo ====================================================

REM Clean up previous build outputs (keep the spec file - it contains hidden imports)
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Run PyInstaller using the maintained spec file
.\venv\Scripts\pyinstaller --noconfirm --clean taskbar_meter.spec

echo ====================================================
echo Build Complete! Output executable is in the dist/ folder.
echo ====================================================

