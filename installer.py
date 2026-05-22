import sys
import os
import shutil
import subprocess
import winreg
from PySide6.QtWidgets import (QWidget, QLabel, QPushButton, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QFileDialog, QCheckBox, 
                             QMessageBox, QGraphicsDropShadowEffect)
from PySide6.QtGui import QFont, QColor, QLinearGradient, QPalette, QBrush
from PySide6.QtCore import Qt, QSize

import config

class InstallerWindow(QWidget):
    def __init__(self, run_app_callback):
        super().__init__()
        self.run_app_callback = run_app_callback
        self.cfg = config.load_config()
        self.init_ui()
        
    def init_ui(self):
        self.setObjectName("InstallerWindow")
        self.setWindowTitle("Taskbar Metering Installer")
        self.setFixedSize(520, 360)
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
                width: 14px;
                height: 14px;
                border: 2px solid #455A64;
                border-radius: 4px;
                background-color: #1A1A1E;
            }
            QCheckBox::indicator:hover {
                border-color: #2979FF;
            }
            QCheckBox::indicator:unchecked {
                background-color: #1A1A1E;
            }
            QCheckBox::indicator:checked {
                border: 4px solid #2979FF;
                background-color: #FFFFFF;
            }
            QCheckBox:hover {
                color: #FFFFFF;
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
        default_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TaskbarMetering")
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
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to run standalone:\n{str(e)}")
        
    def perform_installation(self):
        target_dir = os.path.normpath(self.path_edit.text())
        
        try:
            os.makedirs(target_dir, exist_ok=True)
            
            current_src = os.path.abspath(sys.argv[0])
            dest_filename = "taskbar_meter.exe" if current_src.endswith(".exe") else "main.py"
            target_file = os.path.join(target_dir, dest_filename)
            
            if os.path.abspath(current_src).lower() != os.path.abspath(target_file).lower():
                if not current_src.endswith(".exe"):
                    shutil.copy2(current_src, target_file)
                    for pyfile in ["config.py", "metrics.py", "tray_app.py", "installer.py"]:
                        shutil.copy2(os.path.join(os.path.dirname(current_src), pyfile), os.path.join(target_dir, pyfile))
                else:
                    shutil.copy2(current_src, target_file)
            
            self.cfg["installed"] = True
            self.cfg["launch_on_startup"] = self.startup_check.isChecked()
            config.save_config(self.cfg)
            
            register_startup(target_file, self.startup_check.isChecked())
            register_uninstaller(target_file, target_dir)
            create_start_menu_shortcut(target_file)
            
            QMessageBox.information(self, "Success", "Taskbar Metering installed successfully!")
            self.close()
            
            if current_src.endswith(".exe"):
                subprocess.Popen([target_file, "--run"])
            else:
                subprocess.Popen([sys.executable, target_file, "--run"])
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to complete installation:\n{str(e)}")


def register_startup(exe_path, enabled):
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        app_name = "TaskbarMetering"
        if enabled:
            cmd = f'"{exe_path}" --run' if " " in exe_path else f"{exe_path} --run"
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Failed to configure startup registry: {e}")


def register_uninstaller(exe_path, install_dir):
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TaskbarMetering"
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Taskbar Metering")
        uninst_cmd = f'"{exe_path}" --uninstall' if " " in exe_path else f"{exe_path} --uninstall"
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, uninst_cmd)
        
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, exe_path)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Charlie")
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "1.0.0")
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Failed to register uninstaller: {e}")


def create_start_menu_shortcut(exe_path):
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        programs_dir = os.path.join(os.environ.get("APPDATA"), r"Microsoft\Windows\Start Menu\Programs")
        shortcut_path = os.path.join(programs_dir, "Taskbar Metering.lnk")
        
        ps_cmd = f"""
        $WshShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut('{shortcut_path}')
        $Shortcut.TargetPath = '{exe_path}'
        $Shortcut.Arguments = '--run'
        $Shortcut.IconLocation = '{exe_path}'
        $Shortcut.Save()
        """
        
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], startupinfo=startupinfo, capture_output=True, timeout=5)
    except Exception as e:
        print(f"Failed to create shortcut: {e}")


def run_uninstallation():
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
    cfg = config.load_config()
    app_dir = config.get_config_dir()
    install_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    local_appdata = os.environ.get("LOCALAPPDATA", "").lower()
    
    # 5. Path Guardrails:
    # Only delete files if we are running from a directory inside %LOCALAPPDATA%
    # This prevents accidental deletion of project workspace or compile directory!
    is_safe_to_delete = local_appdata and install_dir.lower().startswith(local_appdata)
    
    if is_safe_to_delete:
        try:
            ctypes.windll.user32.MessageBoxW(0, "Taskbar Metering has been uninstalled successfully.", "Uninstallation Complete", 0x40 | 0x0)
            cmd_str = f'timeout /t 2 & rmdir /s /q "{install_dir}" & rmdir /s /q "{app_dir}"'
            subprocess.Popen(f'cmd.exe /c "{cmd_str}"', shell=True)
        except Exception as e:
            print(f"Self-destruct invocation failed: {e}")
    else:
        ctypes.windll.user32.MessageBoxW(
            0, 
            "Registry entries and shortcuts were removed successfully.\n\nNote: Running from developer workspace folder, so actual files were not deleted.", 
            "Uninstallation Complete", 
            0x40 | 0x0
        )
        
    sys.exit(0)
