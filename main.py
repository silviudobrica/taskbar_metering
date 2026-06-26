import sys
import os
import ctypes
import subprocess
import logging
import logging.handlers
import argparse
from PySide6.QtWidgets import QApplication

import config
import tray_app
import installer


def setup_logging():
    log_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "TaskbarMetering", "logs"
    )
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")

    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(handler)

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

def run_installer_gui():
    # Enable High DPI scaling
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Essential to prevent exit when installer closes
    
    # Store references to prevent garbage collection
    app.tray_instance = None
    
    def launch_tray_app():
        app.tray_instance = tray_app.MeterTray(uninstall_callback=installer.run_uninstallation)
        
    window = installer.InstallerWindow(launch_tray_app)
    window.show()
    sys.exit(app.exec())


def _is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin(args):
    try:
        exe_path = os.path.abspath(sys.argv[0])
        params = " ".join(args)
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe_path, params, None, 1)
        return result > 32
    except Exception:
        return False


def _run_elevated_task_once():
    try:
        result = subprocess.run(
            ["schtasks", "/Run", "/TN", "TaskbarMetering_AutoRun"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        return result.returncode == 0
    except Exception:
        return False

def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Taskbar Metering Application")
    parser.add_argument("--version", action="version", version=f"Taskbar Metering {config.APP_VERSION}")
    parser.add_argument("--run", action="store_true", help="Launch the tray monitoring application directly")
    parser.add_argument("--install", action="store_true", help="Launch the installation wizard")
    parser.add_argument("--uninstall", action="store_true", help="Uninstall the application and clean up configurations")
    
    args = parser.parse_args()
    
    if args.uninstall:
        installer.run_uninstallation()
    elif args.install:
        run_installer_gui()
    elif args.run:
        cfg = config.load_config()
        if cfg.get("run_as_admin", False) and not _is_admin():
            if _run_elevated_task_once():
                return
            if _relaunch_as_admin(["--run"]):
                return
        tray_app.run_app(uninstall_callback=installer.run_uninstallation)
    else:
        # Default: Always show installer GUI
        # The installer detects installation status and shows appropriate options
        # (Install, Uninstall, Repair, or Upgrade)
        run_installer_gui()

if __name__ == "__main__":
    main()
