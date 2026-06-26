import sys
import os
import time
import shutil
import subprocess
import winreg
import ctypes
import logging
import threading
from PySide6.QtWidgets import (QWidget, QLabel, QPushButton, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QFileDialog, QCheckBox, 
                             QMessageBox, QGraphicsDropShadowEffect, QApplication)
from PySide6.QtGui import QFont, QColor, QLinearGradient, QPalette, QBrush
from PySide6.QtCore import Qt, QSize
from PySide6.QtNetwork import QLocalSocket

import config
import updater

logger = logging.getLogger(__name__)

UNINSTALL_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TaskbarMetering"
ELEVATED_TASK_NAME = "TaskbarMetering_AutoRun"


def _parse_exe_from_command(command):
    if not command:
        return None
    cmd = command.strip()
    if cmd.startswith('"'):
        end_quote = cmd.find('"', 1)
        if end_quote > 1:
            return cmd[1:end_quote]
    return cmd.split()[0] if cmd else None


def get_registered_install_info():
    info = {
        "installed": False,
        "install_dir": os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TaskbarMetering"),
        "exe_path": None,
        "display_version": None,
    }

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_KEY, 0, winreg.KEY_READ)
        try:
            install_dir, _ = winreg.QueryValueEx(key, "InstallLocation")
            if install_dir:
                info["install_dir"] = install_dir
        except OSError:
            pass

        try:
            uninstall_cmd, _ = winreg.QueryValueEx(key, "UninstallString")
            exe_from_cmd = _parse_exe_from_command(uninstall_cmd)
            if exe_from_cmd:
                info["exe_path"] = exe_from_cmd
        except OSError:
            pass

        try:
            display_version, _ = winreg.QueryValueEx(key, "DisplayVersion")
            info["display_version"] = display_version
        except OSError:
            pass

        winreg.CloseKey(key)
    except OSError:
        pass

    if not info["exe_path"]:
        info["exe_path"] = os.path.join(info["install_dir"], "taskbar_meter.exe")

    info["installed"] = os.path.exists(info["exe_path"])
    return info


def _create_elevated_logon_task(exe_path):
    command = f'"{exe_path}" --run'
    result = subprocess.run(
        [
            "schtasks",
            "/Create",
            "/F",
            "/TN",
            ELEVATED_TASK_NAME,
            "/TR",
            command,
            "/SC",
            "ONLOGON",
            "/RL",
            "HIGHEST",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode == 0


def _remove_elevated_logon_task():
    subprocess.run(
        ["schtasks", "/Delete", "/TN", ELEVATED_TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        timeout=10,
    )


def _run_elevated_task_once():
    result = subprocess.run(
        ["schtasks", "/Run", "/TN", ELEVATED_TASK_NAME],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode == 0


def is_admin():
    """Check if the current process has administrator privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin(args=None):
    """Re-run the current script with administrator privileges"""
    if is_admin():
        return  # Already admin
    
    try:
        if args is None:
            args = sys.argv[1:]
        
        script = os.path.abspath(sys.argv[0])
        params = ' '.join([f'"{arg}"' if ' ' in arg else arg for arg in args])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", script, params, None, 1)
        sys.exit(0)
    except Exception as e:
        print(f"Failed to escalate to admin: {e}")


def _is_running_inside_app_process():
    app = QApplication.instance()
    return bool(app and (hasattr(app, "tray_ref") or hasattr(app, "tray_instance")))


def request_running_instance_exit(wait_seconds=8):
    socket = QLocalSocket()
    socket.connectToServer(config.APP_IPC_SERVER_NAME)
    if not socket.waitForConnected(600):
        return True

    socket.write(b"UNINSTALL\n")
    socket.flush()
    socket.waitForBytesWritten(600)
    socket.disconnectFromServer()

    deadline = time.monotonic() + max(1, wait_seconds)
    while time.monotonic() < deadline:
        probe = QLocalSocket()
        probe.connectToServer(config.APP_IPC_SERVER_NAME)
        if not probe.waitForConnected(250):
            return True
        probe.disconnectFromServer()
        probe.waitForDisconnected(200)
        time.sleep(0.2)

    return False

class InstallerWindow(QWidget):
    MODE_INSTALL = "install"
    MODE_MANAGE = "manage"
    
    def __init__(self, run_app_callback):
        super().__init__()
        self.run_app_callback = run_app_callback
        self.cfg = config.load_config()

        # Detect current installation state from registry + executable presence.
        self.install_info = get_registered_install_info()
        self.is_installed = self.install_info["installed"]
        self.mode = self.MODE_MANAGE if self.is_installed else self.MODE_INSTALL

        self.install_dir = self.install_info["install_dir"]
        self.exe_path = self.install_info["exe_path"]

        # Keep config in sync so stale config does not force wrong mode.
        if self.cfg.get("installed", False) != self.is_installed:
            self.cfg["installed"] = self.is_installed
            config.save_config(self.cfg)
        
        self.init_ui()
        
    def init_ui(self):
        self.setObjectName("InstallerWindow")
        self.setWindowTitle("Taskbar Metering Installer")
        
        if self.mode == self.MODE_INSTALL:
            self._init_install_ui()
        else:
            self._init_manage_ui()
    
    def _init_install_ui(self):
        """UI for fresh installation"""
        self.setFixedSize(520, 390)
        self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint)
        
        # Enable premium dark mode stylesheet
        self.setStyleSheet("""
            QWidget#InstallerWindow {
                background-color: #121214;
            }
            QLabel {
                color: #ECEFF1;
                font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
            }
            QLabel#TitleLabel {
                font-size: 24px;
                font-weight: bold;
                color: #FFFFFF;
                margin-bottom: 2px;
            }
            QLabel#SubTitleLabel {
                font-size: 13px;
                color: #90A4AE;
                margin-bottom: 15px;
            }
            QLabel#SectionLabel {
                font-size: 12px;
                font-weight: bold;
                color: #2979FF;
                text-transform: uppercase;
                margin-bottom: 5px;
            }
            QLineEdit {
                background-color: #1A1A1E;
                border: 1px solid #2D2D35;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                color: #FFFFFF;
            }
            QLineEdit:focus {
                border: 1px solid #2979FF;
            }
            QPushButton {
                font-size: 13px;
                font-weight: bold;
                border-radius: 6px;
                padding: 10px 20px;
            }
            QPushButton#PrimaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2979FF, stop:1 #1565C0);
                color: white;
                border: none;
            }
            QPushButton#PrimaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #448AFF, stop:1 #1E88E5);
            }
            QPushButton#SecondaryBtn {
                background-color: #1A1A1E;
                border: 1px solid #2D2D35;
                color: #B0BEC5;
            }
            QPushButton#SecondaryBtn:hover {
                background-color: #2D2D35;
                color: #FFFFFF;
            }
            QCheckBox {
                font-size: 13px;
                color: #ECEFF1;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #555555;
                background-color: #1A1A1E;
            }
            QCheckBox::indicator:hover {
                border-color: #2979FF;
                background-color: #232327;
            }
            QCheckBox::indicator:unchecked {
                background-color: #1A1A1E;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #2979FF;
                background-color: #2979FF;
            }
        """)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(30, 25, 30, 25)
        main_layout.setSpacing(15)
        
        # Header Group
        header_layout = QVBoxLayout()
        title = QLabel("Taskbar Metering")
        title.setObjectName("TitleLabel")
        subtitle = QLabel("Hardware status metrics directly on your Windows tray clock")
        subtitle.setObjectName("SubTitleLabel")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        main_layout.addLayout(header_layout)
        
        # Path Selector Group
        path_layout = QVBoxLayout()
        path_title = QLabel("Installation Folder")
        path_title.setObjectName("SectionLabel")
        path_layout.addWidget(path_title)
        
        path_input_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        default_dir = self.install_dir
        self.path_edit.setText(default_dir)
        
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setObjectName("SecondaryBtn")
        self.browse_btn.clicked.connect(self.browse_folder)
        
        path_input_layout.addWidget(self.path_edit)
        path_input_layout.addWidget(self.browse_btn)
        path_layout.addLayout(path_input_layout)
        main_layout.addLayout(path_layout)
        
        # Options Group
        options_layout = QVBoxLayout()
        self.startup_check = QCheckBox("Launch automatically on Windows startup")
        self.startup_check.setChecked(self.cfg.get("launch_on_startup", True))
        options_layout.addWidget(self.startup_check)
        
        # Admin info label
        admin_label = QLabel("ℹ Administrator mode is optional and improves temperature sensor access")
        admin_label.setStyleSheet("font-size: 11px; color: #90A4AE; margin-top: 5px;")
        admin_label.setWordWrap(True)
        options_layout.addWidget(admin_label)
        
        main_layout.addLayout(options_layout)
        
        main_layout.addStretch()
        
        # Action Buttons Group
        btn_layout = QHBoxLayout()
        
        self.standalone_btn = QPushButton("Run Standalone (No Install)")
        self.standalone_btn.setObjectName("SecondaryBtn")
        self.standalone_btn.clicked.connect(self.run_standalone)
        
        self.install_btn = QPushButton("Install & Launch")
        self.install_btn.setObjectName("PrimaryBtn")
        self.install_btn.clicked.connect(self.perform_installation)
        
        btn_layout.addWidget(self.standalone_btn)
        btn_layout.addWidget(self.install_btn)
        main_layout.addLayout(btn_layout)
        
        self.setLayout(main_layout)
    
    def _init_manage_ui(self):
        """UI for managing existing installation (Uninstall/Repair/Upgrade)"""
        self.setFixedSize(500, 350)
        self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint)
        
        self.setStyleSheet("""
            QWidget#InstallerWindow {
                background-color: #121214;
            }
            QLabel {
                color: #ECEFF1;
                font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
            }
            QLabel#TitleLabel {
                font-size: 24px;
                font-weight: bold;
                color: #FFFFFF;
                margin-bottom: 2px;
            }
            QLabel#SubTitleLabel {
                font-size: 13px;
                color: #90A4AE;
                margin-bottom: 15px;
            }
            QLabel#InfoLabel {
                font-size: 12px;
                color: #B0BEC5;
                margin: 5px 0px;
            }
            QPushButton {
                font-size: 13px;
                font-weight: bold;
                border-radius: 6px;
                padding: 10px 20px;
                min-width: 140px;
            }
            QPushButton#PrimaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2979FF, stop:1 #1565C0);
                color: white;
                border: none;
            }
            QPushButton#PrimaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #448AFF, stop:1 #1E88E5);
            }
            QPushButton#SecondaryBtn {
                background-color: #1A1A1E;
                border: 1px solid #2D2D35;
                color: #B0BEC5;
            }
            QPushButton#SecondaryBtn:hover {
                background-color: #2D2D35;
                color: #FFFFFF;
            }
            QPushButton#DangerBtn {
                background-color: #B71C1C;
                color: white;
                border: none;
            }
            QPushButton#DangerBtn:hover {
                background-color: #D32F2F;
            }
        """)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(30, 25, 30, 25)
        main_layout.setSpacing(15)
        
        # Header Group
        header_layout = QVBoxLayout()
        title = QLabel("Taskbar Metering")
        title.setObjectName("TitleLabel")
        installed_ver = self.install_info.get("display_version") or config.APP_VERSION
        subtitle = QLabel(f"Version {installed_ver} is installed")
        subtitle.setObjectName("SubTitleLabel")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        main_layout.addLayout(header_layout)
        
        # Info Group
        info_layout = QVBoxLayout()
        info_title = QLabel("Installation Details:")
        info_title.setStyleSheet("font-weight: bold; color: #FFFFFF; margin-top: 10px;")
        info_layout.addWidget(info_title)
        
        install_path_label = QLabel(f"Location: {self.install_dir}")
        install_path_label.setObjectName("InfoLabel")
        install_path_label.setWordWrap(True)
        info_layout.addWidget(install_path_label)

        launch_mode = "Administrator" if self.cfg.get("run_as_admin", False) else "Current User"
        launch_mode_label = QLabel(f"Launch Mode: {launch_mode}")
        launch_mode_label.setObjectName("InfoLabel")
        info_layout.addWidget(launch_mode_label)
        
        info_layout.addSpacing(5)
        main_layout.addLayout(info_layout)
        main_layout.addStretch()
        
        # Action Buttons Group
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(10)
        
        # Row 1: Launch and Check for Updates
        row1_layout = QHBoxLayout()
        
        self.launch_btn = QPushButton("Launch Application")
        self.launch_btn.setObjectName("PrimaryBtn")
        self.launch_btn.clicked.connect(self.launch_app)
        
        self.check_update_btn = QPushButton("Check for Updates")
        self.check_update_btn.setObjectName("SecondaryBtn")
        self.check_update_btn.clicked.connect(self.check_for_updates)
        
        row1_layout.addWidget(self.launch_btn)
        row1_layout.addWidget(self.check_update_btn)
        btn_layout.addLayout(row1_layout)
        
        # Row 2: Repair and Uninstall
        row2_layout = QHBoxLayout()
        
        self.repair_btn = QPushButton("Repair")
        self.repair_btn.setObjectName("SecondaryBtn")
        self.repair_btn.clicked.connect(self.repair_installation)

        self.repair_admin_btn = QPushButton("Repair as Admin")
        self.repair_admin_btn.setObjectName("SecondaryBtn")
        self.repair_admin_btn.clicked.connect(self.repair_installation_as_admin)
        
        self.uninstall_btn = QPushButton("Uninstall")
        self.uninstall_btn.setObjectName("DangerBtn")
        self.uninstall_btn.clicked.connect(self.prompt_uninstall)
        
        row2_layout.addWidget(self.repair_btn)
        row2_layout.addWidget(self.repair_admin_btn)
        row2_layout.addWidget(self.uninstall_btn)
        btn_layout.addLayout(row2_layout)
        
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)
        
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Installation Folder", self.path_edit.text())
        if folder:
            self.path_edit.setText(os.path.normpath(folder))
            
    def run_standalone(self):
        current_src = os.path.abspath(sys.argv[0])
        try:
            if current_src.endswith(".exe"):
                subprocess.Popen([current_src, "--run"])
            else:
                subprocess.Popen([sys.executable, current_src, "--run"])
            self.close()
            QApplication.quit()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to run standalone:\n{str(e)}")
        
    def perform_installation(self):
        # Offer both install modes when not elevated.
        if not is_admin():
            mode_box = QMessageBox(self)
            mode_box.setIcon(QMessageBox.Question)
            mode_box.setWindowTitle("Choose Installation Mode")
            mode_box.setText("How would you like to install Taskbar Metering?")
            mode_box.setInformativeText(
                "Administrator mode is recommended for best temperature sensor support.\n"
                "Current user mode installs without elevation in your profile."
            )
            mode_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            mode_box.setDefaultButton(QMessageBox.Yes)
            mode_box.button(QMessageBox.Yes).setText("Install as Administrator")
            mode_box.button(QMessageBox.No).setText("Install as Current User")
            mode_box.button(QMessageBox.Cancel).setText("Cancel")
            choice = mode_box.exec()

            if choice == QMessageBox.Cancel:
                return

            if choice == QMessageBox.Yes:
                try:
                    exe_path = os.path.abspath(sys.argv[0])
                    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe_path, "--install", None, 1)
                    self.close()
                    QApplication.quit()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to elevate privileges:\n{str(e)}")
                return

        # Continue installation in current context (admin or current user).
        target_dir = os.path.normpath(self.path_edit.text())
        
        try:
            os.makedirs(target_dir, exist_ok=True)
            
            current_src = os.path.abspath(sys.argv[0])
            dest_filename = "taskbar_meter.exe" if current_src.endswith(".exe") else "main.py"
            target_file = os.path.join(target_dir, dest_filename)
            
            if os.path.abspath(current_src).lower() != os.path.abspath(target_file).lower():
                if not current_src.endswith(".exe"):
                    shutil.copy2(current_src, target_file)
                    for pyfile in ["config.py", "metrics.py", "tray_app.py", "installer.py", "updater.py"]:
                        src_file = os.path.join(os.path.dirname(current_src), pyfile)
                        if os.path.exists(src_file):
                            shutil.copy2(src_file, os.path.join(target_dir, pyfile))
                else:
                    shutil.copy2(current_src, target_file)
            
            self.cfg["installed"] = True
            self.cfg["run_as_admin"] = is_admin()
            self.cfg["launch_on_startup"] = self.startup_check.isChecked()
            config.save_config(self.cfg)
            
            register_startup(target_file, self.startup_check.isChecked(), self.cfg.get("run_as_admin", False))
            register_uninstaller(target_file, target_dir, self.cfg.get("run_as_admin", False))
            create_start_menu_shortcut(target_file, self.cfg.get("run_as_admin", False))
            
            if is_admin():
                success_msg = (
                    "Taskbar Metering has been installed successfully!\n\n"
                    "Launched in administrator mode for improved temperature sensor access."
                )
            else:
                success_msg = (
                    "Taskbar Metering has been installed successfully!\n\n"
                    "Installed for current user (no administrator privileges)."
                )

            QMessageBox.information(self, "Installation Complete", success_msg)
            self.close()
            
            # Launch app as admin (we're already elevated)
            try:
                subprocess.Popen([target_file, "--run"])
            except Exception as e:
                logger.warning(f"Failed to launch app: {e}")
            
            QApplication.quit()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to complete installation:\n{str(e)}")
    
    def launch_app(self):
        """Launch the installed application"""
        try:
            if self.exe_path and os.path.exists(self.exe_path):
                launch_as_admin = self.cfg.get("run_as_admin", False)
                if launch_as_admin and not is_admin():
                    if not _run_elevated_task_once():
                        ctypes.windll.shell32.ShellExecuteW(None, "runas", self.exe_path, "--run", None, 1)
                else:
                    subprocess.Popen([self.exe_path, "--run"])
                self.close()
            else:
                QMessageBox.critical(self, "Error", "Application executable not found at installation location")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to launch application:\n{str(e)}")
    
    def check_for_updates(self):
        """Check for updates in a background thread"""
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText("Checking...")
        
        def check_thread():
            try:
                newer_available, tag = updater.is_newer_version_available()
                
                if newer_available:
                    reply = QMessageBox.question(
                        self,
                        "Update Available",
                        f"A new version {tag} is available.\n\nWould you like to download and install it?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    
                    if reply == QMessageBox.Yes:
                        self.check_update_btn.setText("Downloading...")
                        try:
                            updater.perform_upgrade()
                            self.close()
                        except Exception as e:
                            QMessageBox.critical(self, "Update Failed", f"Failed to upgrade:\n{str(e)}")
                else:
                    QMessageBox.information(self, "Up to Date", f"You have the latest version ({config.APP_VERSION})")
            except Exception as e:
                QMessageBox.critical(self, "Check Failed", f"Failed to check for updates:\n{str(e)}")
            finally:
                self.check_update_btn.setEnabled(True)
                self.check_update_btn.setText("Check for Updates")
        
        thread = threading.Thread(target=check_thread, daemon=True)
        thread.start()
    
    def repair_installation(self):
        """Repair the installation by restoring files"""
        reply = QMessageBox.question(
            self,
            "Repair Installation",
            "This will restore the application files to their original state.\n\n"
            "Your settings will be preserved.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            current_src = os.path.abspath(sys.argv[0])
            target_dir = self.install_dir
            
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
            
            # Copy files
            if current_src.endswith(".exe"):
                dest_filename = "taskbar_meter.exe"
                target_file = os.path.join(target_dir, dest_filename)
                if os.path.abspath(current_src).lower() != os.path.abspath(target_file).lower():
                    shutil.copy2(current_src, target_file)
                QMessageBox.information(self, "Success", "Installation repaired successfully!")
            else:
                # Copy Python files
                for pyfile in ["config.py", "metrics.py", "tray_app.py", "installer.py", "updater.py", "main.py"]:
                    src_file = os.path.join(os.path.dirname(current_src), pyfile)
                    if os.path.exists(src_file):
                        shutil.copy2(src_file, os.path.join(target_dir, pyfile))
                
                QMessageBox.information(self, "Success", "Installation repaired successfully!")
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to repair installation:\n{str(e)}")

    def repair_installation_as_admin(self):
        """Relaunch repair flow with administrator privileges."""
        if is_admin():
            self.repair_installation()
            return

        try:
            exe_path = os.path.abspath(sys.argv[0])
            ctypes.windll.shell32.ShellExecuteW(None, "runas", exe_path, "--install", None, 1)
            self.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start admin repair:\n{str(e)}")
    
    def prompt_uninstall(self):
        """Prompt user to confirm uninstallation"""
        reply = QMessageBox.warning(
            self,
            "Uninstall Taskbar Metering",
            "Are you sure you want to uninstall Taskbar Metering?\n\n"
            "Your configuration settings will be preserved in:\n"
            f"{os.path.join(os.environ.get('LOCALAPPDATA', '~'), 'TaskbarMetering', 'config.json')}\n\n"
            "Click 'Uninstall' to proceed.",
            QMessageBox.Ok | QMessageBox.Cancel
        )
        
        if reply == QMessageBox.Ok:
            if self.cfg.get("run_as_admin", False) and not is_admin():
                try:
                    exe_path = os.path.abspath(sys.argv[0])
                    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe_path, "--uninstall", None, 1)
                    self.close()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to start elevated uninstall:\n{str(e)}")
                return
            run_uninstallation()
            self.close()


def register_startup(exe_path, enabled, run_as_admin=False):
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        app_name = "TaskbarMetering"
        if enabled:
            if run_as_admin:
                _remove_elevated_logon_task()
                created = _create_elevated_logon_task(exe_path)
                if created:
                    try:
                        winreg.DeleteValue(key, app_name)
                    except FileNotFoundError:
                        pass
                else:
                    cmd = f'"{exe_path}" --run' if " " in exe_path else f"{exe_path} --run"
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                _remove_elevated_logon_task()
                cmd = f'"{exe_path}" --run' if " " in exe_path else f"{exe_path} --run"
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
        else:
            _remove_elevated_logon_task()
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Failed to configure startup registry: {e}")


def register_uninstaller(exe_path, install_dir, run_as_admin=False):
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TaskbarMetering"
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Taskbar Metering")
        if run_as_admin:
            safe_exe = exe_path.replace("'", "''")
            uninst_cmd = (
                "powershell -NoProfile -WindowStyle Hidden -Command "
                f"\"Start-Process -FilePath '{safe_exe}' -ArgumentList '--uninstall' -Verb RunAs\""
            )
        else:
            uninst_cmd = f'"{exe_path}" --uninstall' if " " in exe_path else f"{exe_path} --uninstall"
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, uninst_cmd)
        
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, exe_path)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Charlie")
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, config.APP_VERSION)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        
        winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"Failed to register uninstaller: {e}")


def create_start_menu_shortcut(exe_path, run_as_admin=False):
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        programs_dir = os.path.join(os.environ.get("APPDATA"), r"Microsoft\Windows\Start Menu\Programs")
        shortcut_path = os.path.join(programs_dir, "Taskbar Metering.lnk")
        
        # Escape single quotes in paths to prevent PowerShell injection
        safe_shortcut = shortcut_path.replace("'", "''")
        safe_exe = exe_path.replace("'", "''")

        if run_as_admin:
            target_path = r"C:\\Windows\\System32\\schtasks.exe"
            target_args = f'/Run /TN "{ELEVATED_TASK_NAME}"'
        else:
            target_path = safe_exe
            target_args = '--run'

        ps_cmd = f"""
        $WshShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut('{safe_shortcut}')
        $Shortcut.TargetPath = '{target_path}'
        $Shortcut.Arguments = '{target_args}'
        $Shortcut.IconLocation = '{safe_exe}'
        $Shortcut.Save()
        """
        
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], startupinfo=startupinfo, capture_output=True, timeout=5)
    except Exception as e:
        print(f"Failed to create shortcut: {e}")


def run_uninstallation():
    cfg = config.load_config()
    # For admin-mode installs, ensure uninstall runs elevated so process termination
    # and file deletion can succeed.
    if cfg.get("run_as_admin", False) and not is_admin():
        try:
            exe_path = os.path.abspath(sys.argv[0])
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe_path, "--uninstall", None, 1)
            if result > 32:
                return
        except Exception:
            pass

    # 1. Show confirmation dialog FIRST
    import ctypes
    confirm = ctypes.windll.user32.MessageBoxW(
        0, 
        "Are you sure you want to uninstall Taskbar Metering?\nThis will remove startup shortcuts and delete application files.", 
        "Uninstall Confirmation", 
        0x20 | 0x1  # MB_ICONQUESTION | MB_OKCANCEL
    )
    if confirm != 1: # 1 is IDOK, 2 is IDCANCEL
        print("Uninstallation cancelled by user.")
        return # Do nothing!

    install_info = get_registered_install_info()

    # If uninstall is launched from outside the running tray process,
    # ask the active instance to quit first so file cleanup can succeed.
    if not _is_running_inside_app_process():
        if not request_running_instance_exit():
            pass

    # Try force-stopping remaining instances except current process.
    try:
        stop_ps = (
            f"Get-Process taskbar_meter -ErrorAction SilentlyContinue | "
            f"Where-Object {{$_.Id -ne {os.getpid()}}} | Stop-Process -Force"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", stop_ps], capture_output=True, timeout=8)
    except Exception:
        pass

    # Additional force kill fallback.
    try:
        subprocess.run(["taskkill", "/F", "/IM", "taskbar_meter.exe", "/T"], capture_output=True, timeout=8)
    except Exception:
        pass

    # 2. Remove Registry Key for Startup
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        winreg.DeleteValue(key, "TaskbarMetering")
        winreg.CloseKey(key)
    except Exception:
        pass

    # 3. Remove Registry Key for Uninstaller
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{key_path}\\TaskbarMetering")
    except Exception:
        pass

    # 4. Remove Start Menu Shortcut
    try:
        programs_dir = os.path.join(os.environ.get("APPDATA"), r"Microsoft\Windows\Start Menu\Programs")
        shortcut_path = os.path.join(programs_dir, "Taskbar Metering.lnk")
        if os.path.exists(shortcut_path):
            os.remove(shortcut_path)
    except Exception:
        pass

    # Get install location
    app_dir = config.get_config_dir()
    install_dir = install_info.get("install_dir") or os.path.dirname(os.path.abspath(sys.argv[0]))
    local_appdata = os.environ.get("LOCALAPPDATA", "").lower()
    
    # 5. Path Guardrails:
    # Only delete files if we are running from a directory inside %LOCALAPPDATA%
    # This prevents accidental deletion of project workspace or compile directory!
    is_safe_to_delete = local_appdata and install_dir.lower().startswith(local_appdata)
    
    if is_safe_to_delete:
        # Schedule deletion via cmd (handles file locks better)
        try:
            # Use a delayed batch command to delete the directory after the process exits
            # This avoids file lock issues
            batch_cmd = f'''
@echo off
taskkill /F /IM taskbar_meter.exe /T >nul 2>&1
timeout /t 2 /nobreak
taskkill /F /IM taskbar_meter.exe /T >nul 2>&1
if exist "{install_dir}" rmdir /s /q "{install_dir}" >nul 2>&1
if exist "{app_dir}" rmdir /s /q "{app_dir}" >nul 2>&1
exit /b 0
'''
            batch_file = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "taskbar_meter_uninstall.bat")
            with open(batch_file, "w") as f:
                f.write(batch_cmd)
            
            # Show success message first
            ctypes.windll.user32.MessageBoxW(
                0, 
                "Taskbar Metering has been uninstalled successfully.\n\n"
                "Registry entries, shortcuts, and application files are being removed.", 
                "Uninstallation Complete", 
                0x40 | 0x0
            )
            
            # Run the batch file in background
            subprocess.Popen(f'cmd.exe /c "{batch_file}"', shell=False, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            logger.warning(f"Failed to schedule file deletion: {e}")
            ctypes.windll.user32.MessageBoxW(
                0, 
                "Taskbar Metering has been uninstalled successfully.\n\n"
                "Note: Some application files could not be automatically removed.\n"
                "You may need to manually delete the folder.", 
                "Uninstallation Complete", 
                0x40 | 0x0
            )
    else:
        # Running from developer workspace - don't delete files
        ctypes.windll.user32.MessageBoxW(
            0, 
            "Registry entries and shortcuts were removed successfully.\n\n"
            "Note: Application is running from developer workspace.\n"
            "To fully uninstall, install the app first (Install button),\n"
            "then uninstall from Windows Settings → Apps.", 
            "Uninstallation Complete", 
            0x40 | 0x0
        )

    # Ensure startup behavior and config state are reset.
    try:
        register_startup(install_info.get("exe_path") or "taskbar_meter.exe", False, False)
    except Exception:
        pass

    try:
        cfg["installed"] = False
        cfg["run_as_admin"] = False
        config.save_config(cfg)
    except Exception:
        pass
        
    sys.exit(0)
