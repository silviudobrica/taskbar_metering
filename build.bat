@echo off
echo ====================================================
echo Building Taskbar Metering Executable via PyInstaller
echo ====================================================

REM Clean up previous build outputs
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist taskbar_meter.spec del /q taskbar_meter.spec

REM Run PyInstaller compilation
.\venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name="taskbar_meter" --clean main.py

echo ====================================================
echo Build Complete! Output executable is in the dist/ folder.
echo ====================================================

