@echo off
setlocal

cd /d "%~dp0"
if errorlevel 1 (
	echo [ERROR] Could not switch to the repository directory.
	exit /b 1
)

echo ====================================================
echo Building Taskbar Metering Executable via PyInstaller
echo ====================================================

set "PYTHON_CMD="
set "PYINSTALLER_CMD="

if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"
if not defined PYTHON_CMD if exist "venv\Scripts\python.exe" set "PYTHON_CMD=venv\Scripts\python.exe"
if not defined PYTHON_CMD set "PYTHON_CMD=python"

"%PYTHON_CMD%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
	echo [ERROR] PyInstaller is not available for "%PYTHON_CMD%".
	echo         Install it in that environment: "%PYTHON_CMD%" -m pip install pyinstaller
	exit /b 1
)

set "PYINSTALLER_CMD=%PYTHON_CMD% -m PyInstaller"

REM Clean up previous build outputs (keep the spec file - it contains hidden imports)
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Run PyInstaller using the maintained spec file
if exist taskbar_meter.spec (
	%PYINSTALLER_CMD% --noconfirm --clean taskbar_meter.spec
) else (
	echo [WARN] taskbar_meter.spec not found. Using main.py defaults.
	%PYINSTALLER_CMD% --noconfirm --clean --specpath build --onefile --windowed --name taskbar_meter main.py
)

if errorlevel 1 (
	echo ====================================================
	echo Build FAILED.
	echo ====================================================
	exit /b 1
)

echo ====================================================
echo Build Complete! Output executable is in the dist/ folder.
echo ====================================================
exit /b 0

