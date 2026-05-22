import sys
import os
from PySide6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QWidget, 
                             QLabel, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QListWidget, QListWidgetItem, QDialog, QAbstractItemView,
                             QGraphicsDropShadowEffect, QCheckBox, QFrame, QScrollArea)
from PySide6.QtGui import (QIcon, QPixmap, QPainter, QColor, QFont, QPen, 
                           QAction, QActionGroup, QCursor, QPainterPath)
from PySide6.QtCore import QTimer, Qt, QSize, QEvent, QObject

import config
import metrics

# Styling constants for sensors
SENSOR_METADATA = {
    "cpu_usage": {
        "label": "CPU Usage",
        "short": "CPU",
        "color": "#00E676",      # Bright Green
        "unit": "%",
        "max": 100
    },
    "cpu_temp": {
        "label": "CPU Temperature",
        "short": "C°",
        "color": "#FF5252",      # Warm Coral
        "unit": "°C",
        "max": 100
    },
    "ram_usage": {
        "label": "RAM Usage",
        "short": "RAM",
        "color": "#2979FF",      # Electric Blue
        "unit": "%",
        "max": 100
    },
    "gpu_usage": {
        "label": "GPU Usage",
        "short": "GPU",
        "color": "#AA00FF",      # Vibrant Purple
        "unit": "%",
        "max": 100
    },
    "gpu_temp": {
        "label": "GPU Temperature",
        "short": "G°",
        "color": "#FF1744",      # Deep Red
        "unit": "°C",
        "max": 100
    },
    "disk_usage": {
        "label": "Disk Usage",
        "short": "DSK",
        "color": "#00B0FF",      # Soft Teal
        "unit": "%",
        "max": 100
    },
    "disk_temp": {
        "label": "Disk Temperature",
        "short": "D°",
        "color": "#FFD600",      # Golden Orange
        "unit": "°C",
        "max": 80
    }
}


def initialize_dynamic_sensors():
    # Detect physical disks/partitions and pre-populate metadata
    disk_list = metrics.get_disk_usage()
    if "disk_usage" in SENSOR_METADATA:
        del SENSOR_METADATA["disk_usage"]
    if "disk_temp" in SENSOR_METADATA:
        del SENSOR_METADATA["disk_temp"]
        
    for i, d in enumerate(disk_list):
        dev_name = d["device"]
        dev_clean = dev_name.lower().replace(":", "")
        
        # Disk usage sensor
        usage_key = f"disk_usage_{dev_clean}"
        SENSOR_METADATA[usage_key] = {
            "label": f"Disk {dev_name} Usage",
            "short": f"Dsk {dev_name}",
            "color": "#00B0FF" if i == 0 else ("#FFD600" if i == 1 else "#AA00FF"),
            "unit": "%",
            "max": 100,
            "device": dev_name
        }
        
        # Disk temp sensor
        temp_key = f"disk_temp_{dev_clean}"
        SENSOR_METADATA[temp_key] = {
            "label": f"Disk {dev_name} Temperature",
            "short": f"Tmp {dev_name}",
            "color": "#FFD600" if i == 0 else ("#FF1744" if i == 1 else "#FF5252"),
            "unit": "°C",
            "max": 80,
            "device": dev_name
        }

def migrate_config_keys():
    try:
        cfg = config.load_config()
        active = cfg.get("active_sensors", ["cpu_usage", "ram_usage"])
        new_active = []
        has_changes = False
        
        dynamic_usages = [k for k in SENSOR_METADATA.keys() if k.startswith("disk_usage_")]
        dynamic_temps = [k for k in SENSOR_METADATA.keys() if k.startswith("disk_temp_")]
        
        for key in active:
            if key == "disk_usage":
                for du in dynamic_usages:
                    if du not in new_active:
                        new_active.append(du)
                has_changes = True
            elif key == "disk_temp":
                for dt in dynamic_temps:
                    if dt not in new_active:
                        new_active.append(dt)
                has_changes = True
            else:
                if key not in new_active:
                    new_active.append(key)
                    
        if has_changes:
            cfg["active_sensors"] = new_active
            config.save_config(cfg)
    except Exception:
        pass

# Pre-populate dynamic disk sensors immediately
initialize_dynamic_sensors()
migrate_config_keys()


class CircularProgress(QWidget):
    """Custom premium widget representing a circular metric meter in the flyout"""
    def __init__(self, color_hex, parent=None):
        super().__init__(parent)
        self.color = QColor(color_hex)
        self.value = 0.0
        self.max_val = 100
        self.unit = "%"
        self.setFixedSize(50, 50)
        
    def set_value(self, val, max_val=100, unit="%"):
        self.value = val
        self.max_val = max_val
        self.unit = unit
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Background arc
        bg_pen = QPen(QColor(42, 42, 48), 3.5)
        painter.setPen(bg_pen)
        painter.drawEllipse(3, 3, 44, 44)
        
        if self.value is None:
            # Draw dotted gray circle for unsupported
            dot_pen = QPen(QColor(90, 90, 95), 3, Qt.DashLine)
            painter.setPen(dot_pen)
            painter.drawEllipse(3, 3, 44, 44)
            
            painter.setPen(QColor("#78909C"))
            font = QFont("Segoe UI", 9, QFont.Bold)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, "--")
        else:
            percent = min(max(self.value, 0.0), self.max_val)
            ratio = percent / self.max_val
            span = -int(ratio * 360 * 16)
            
            fg_pen = QPen(self.color, 3.5)
            painter.setPen(fg_pen)
            painter.drawArc(3, 3, 44, 44, 90 * 16, span)
            
            # Value in center
            painter.setPen(QColor("#FFFFFF"))
            font = QFont("Segoe UI", 10, QFont.Bold)
            painter.setFont(font)
            val_str = f"{int(round(self.value))}"
            painter.drawText(self.rect(), Qt.AlignCenter, val_str)
        painter.end()


class SensorCard(QFrame):
    def __init__(self, sensor_key, metadata, is_active, on_toggle, on_move_left, on_move_right, parent=None):
        super().__init__(parent)
        self.sensor_key = sensor_key
        self.metadata = metadata
        self.is_active = is_active
        self.on_toggle = on_toggle
        self.on_move_left = on_move_left
        self.on_move_right = on_move_right
        self.init_ui()
        
    def init_ui(self):
        self.setFixedSize(130, 140)
        self.setObjectName("SensorCard")
        self.update_style()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Indicator / Checkbox
        self.checkbox = QCheckBox(self.metadata.get("short", self.metadata["label"]), self)
        self.checkbox.setChecked(self.is_active)
        self.checkbox.stateChanged.connect(self.toggle_state)
        layout.addWidget(self.checkbox, 0, Qt.AlignLeft)
        
        # Details label
        lbl = QLabel(self.metadata["label"], self)
        lbl.setObjectName("CardLabel")
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl, 1)
        
        # Buttons layout
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        
        self.left_btn = QPushButton("◀", self)
        self.left_btn.setObjectName("CardBtn")
        self.left_btn.clicked.connect(self.move_left_clicked)
        
        self.right_btn = QPushButton("▶", self)
        self.right_btn.setObjectName("CardBtn")
        self.right_btn.clicked.connect(self.move_right_clicked)
        
        btn_layout.addWidget(self.left_btn)
        btn_layout.addWidget(self.right_btn)
        layout.addLayout(btn_layout)

    def move_left_clicked(self):
        self.on_move_left(self.sensor_key)

    def move_right_clicked(self):
        self.on_move_right(self.sensor_key)
        
    def update_style(self):
        color = self.metadata.get("color", "#2979FF")
        self.setStyleSheet(f"""
            QFrame#SensorCard {{
                background-color: #1E1E22;
                border: 1.5px solid {color if self.is_active else '#2D2D35'};
                border-radius: 8px;
            }}
            QFrame#SensorCard:hover {{
                background-color: #25252B;
                border-color: #2979FF;
            }}
            QLabel#CardLabel {{
                color: #B0BEC5;
                font-size: 11px;
                font-weight: bold;
            }}
            QCheckBox {{
                color: #ECEFF1;
                font-size: 12px;
                font-weight: bold;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 2px solid #546E7A;
                border-radius: 3px;
                background-color: transparent;
            }}
            QCheckBox::indicator:checked {{
                background-color: {color};
                border-color: {color};
            }}
            QPushButton#CardBtn {{
                background-color: #121214;
                border: 1px solid #2D2D35;
                color: #B0BEC5;
                font-size: 11px;
                font-weight: bold;
                border-radius: 4px;
                padding: 4px;
            }}
            QPushButton#CardBtn:hover {{
                background-color: #2D2D35;
                color: #FFFFFF;
            }}
        """)
        
    def toggle_state(self, state):
        self.is_active = (state == Qt.Checked.value or state == Qt.Checked)
        self.update_style()
        self.on_toggle(self.sensor_key, self.is_active)


class SensorConfigDialog(QDialog):
    """Configuration Dialog with custom SensorCards in a premium horizontal scroll view"""
    def __init__(self, on_save_callback, parent=None):
        super().__init__(parent)
        self.on_save_callback = on_save_callback
        self.cfg = config.load_config()
        self.active_sensors = list(self.cfg.get("active_sensors", ["cpu_usage", "ram_usage"]))
        
        all_sensors = list(SENSOR_METADATA.keys())
        self.ordered_sensors = [s for s in self.active_sensors if s in all_sensors]
        for s in all_sensors:
            if s not in self.ordered_sensors:
                self.ordered_sensors.append(s)
                
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Configure Sensors & Order")
        self.setFixedSize(720, 290)
        self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #121214;
                color: #ECEFF1;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                font-size: 13px;
                color: #90A4AE;
            }
            QPushButton {
                font-size: 12px;
                font-weight: bold;
                border-radius: 5px;
                padding: 8px 15px;
            }
            QPushButton#PrimaryBtn {
                background-color: #2979FF;
                color: white;
                border: none;
            }
            QPushButton#PrimaryBtn:hover {
                background-color: #448AFF;
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
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)
        
        desc = QLabel("Check/uncheck sensors to toggle visibility. Click ◀ and ▶ on each card to arrange their order left-to-right on the taskbar.")
        desc.setWordWrap(True)
        main_layout.addWidget(desc)
        
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.scroll_widget = QWidget(self)
        self.scroll_widget.setStyleSheet("background-color: transparent;")
        self.cards_layout = QHBoxLayout(self.scroll_widget)
        self.cards_layout.setContentsMargins(5, 5, 5, 5)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setAlignment(Qt.AlignLeft)
        
        self.scroll_area.setWidget(self.scroll_widget)
        main_layout.addWidget(self.scroll_area)
        
        self.rebuild_cards()
        
        bottom_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setObjectName("SecondaryBtn")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.save_btn = QPushButton("Save Config", self)
        self.save_btn.setObjectName("PrimaryBtn")
        self.save_btn.clicked.connect(self.save_and_close)
        
        bottom_layout.addWidget(self.cancel_btn)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.save_btn)
        main_layout.addLayout(bottom_layout)
        
    def rebuild_cards(self):
        # Clear layout
        while self.cards_layout.count():
            child = self.cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        for i, s in enumerate(self.ordered_sensors):
            is_active = s in self.active_sensors
            card = SensorCard(
                sensor_key=s,
                metadata=SENSOR_METADATA[s],
                is_active=is_active,
                on_toggle=self.on_card_toggle,
                on_move_left=self.move_card_left,
                on_move_right=self.move_card_right,
                parent=self
            )
            # Disable move buttons if at boundaries
            if i == 0:
                card.left_btn.setEnabled(False)
                card.left_btn.setStyleSheet("color: #455A64; border-color: #23232A;")
            if i == len(self.ordered_sensors) - 1:
                card.right_btn.setEnabled(False)
                card.right_btn.setStyleSheet("color: #455A64; border-color: #23232A;")
                
            self.cards_layout.addWidget(card)
            
    def on_card_toggle(self, key, is_active):
        if is_active:
            if key not in self.active_sensors:
                self.active_sensors.append(key)
        else:
            if key in self.active_sensors:
                self.active_sensors.remove(key)
                
    def move_card_left(self, key):
        idx = self.ordered_sensors.index(key)
        if idx > 0:
            self.ordered_sensors[idx], self.ordered_sensors[idx - 1] = self.ordered_sensors[idx - 1], self.ordered_sensors[idx]
            self.rebuild_cards()
            
    def move_card_right(self, key):
        idx = self.ordered_sensors.index(key)
        if idx < len(self.ordered_sensors) - 1:
            self.ordered_sensors[idx], self.ordered_sensors[idx + 1] = self.ordered_sensors[idx + 1], self.ordered_sensors[idx]
            self.rebuild_cards()
            
    def save_and_close(self):
        ordered_active = [s for s in self.ordered_sensors if s in self.active_sensors]
        if not ordered_active:
            ordered_active = ["cpu_usage"]
            
        self.cfg["active_sensors"] = ordered_active
        config.save_config(self.cfg)
        self.on_save_callback()
        self.accept()


class FlyoutPanel(QWidget):
    """Custom high-end frameless sliding translucent panel overlay representing the live dashboard"""
    def __init__(self, open_settings_callback, exit_callback, parent=None):
        super().__init__(parent)
        self.open_settings_callback = open_settings_callback
        self.exit_callback = exit_callback
        self.cfg = config.load_config()
        self.cards = {}
        self.init_ui()
        
    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(300, 480)
        
        self.main_container = QWidget(self)
        self.main_container.setFixedSize(300, 480)
        
        self.main_container.setStyleSheet("""
            QWidget#MainContainer {
                background-color: rgba(18, 18, 20, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            QLabel#Title {
                font-size: 14px;
                font-weight: bold;
                color: #FFFFFF;
            }
            QLabel#MetricLabel {
                font-size: 12px;
                font-weight: bold;
                color: #E2E8F0;
            }
            QLabel#MetricVal {
                font-size: 13px;
                font-weight: bold;
                color: #90A4AE;
            }
            QPushButton#IconBtn {
                background-color: transparent;
                border: none;
                font-size: 14px;
                color: #90A4AE;
                padding: 4px;
            }
            QPushButton#IconBtn:hover {
                color: #FFFFFF;
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 4px;
            }
            QPushButton#ActionBtn {
                background-color: #1A1A1E;
                border: 1px solid #2D2D35;
                color: #CFD8DC;
                font-size: 12px;
                font-weight: bold;
                border-radius: 5px;
                padding: 6px 12px;
            }
            QPushButton#ActionBtn:hover {
                background-color: #2D2D35;
                color: #FFFFFF;
            }
        """)
        self.main_container.setObjectName("MainContainer")
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        self.main_container.setGraphicsEffect(shadow)
        
        layout = QVBoxLayout(self.main_container)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        header = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("Title")
        
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("IconBtn")
        self.settings_btn.setToolTip("Configure Sensors & Sorting")
        self.settings_btn.clicked.connect(self.open_settings_callback)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.settings_btn)
        layout.addLayout(header)
        
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(8)
        layout.addLayout(self.list_layout)
        
        layout.addStretch()
        
        footer = QHBoxLayout()
        
        self.exit_btn = QPushButton("Exit App")
        self.exit_btn.setObjectName("ActionBtn")
        self.exit_btn.clicked.connect(self.exit_callback)
        
        footer.addStretch()
        footer.addWidget(self.exit_btn)
        layout.addLayout(footer)
        
        self.rebuild_cards()
        
    def rebuild_cards(self):
        while self.list_layout.count():
            child = self.list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        self.cards.clear()
        self.cfg = config.load_config()
        
        for key in self.cfg.get("active_sensors", ["cpu_usage", "ram_usage"]):
            if key not in SENSOR_METADATA:
                continue
            meta = SENSOR_METADATA[key]
            
            card_widget = QWidget()
            card_widget.setStyleSheet("""
                QWidget {
                    background-color: rgba(255, 255, 255, 0.02);
                    border: 1px solid rgba(255, 255, 255, 0.04);
                    border-radius: 8px;
                }
            """)
            card_layout = QHBoxLayout(card_widget)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(12)
            
            progress = CircularProgress(meta["color"], card_widget)
            card_layout.addWidget(progress)
            
            text_layout = QVBoxLayout()
            text_layout.setSpacing(2)
            lbl = QLabel(meta["label"])
            lbl.setObjectName("MetricLabel")
            val_lbl = QLabel("--")
            val_lbl.setObjectName("MetricVal")
            text_layout.addWidget(lbl)
            text_layout.addWidget(val_lbl)
            card_layout.addLayout(text_layout)
            
            card_layout.addStretch()
            
            self.list_layout.addWidget(card_widget)
            self.cards[key] = {
                "progress_widget": progress,
                "value_label": val_lbl,
                "meta": meta
            }
            
        item_count = len(self.cards)
        dyn_height = 80 + (item_count * 68)
        self.setFixedSize(300, min(max(dyn_height, 150), 550))
        self.main_container.setFixedSize(self.width(), self.height())
        
    def update_metrics(self, values):
        for key, widgets in self.cards.items():
            val = values.get(key)
            meta = widgets["meta"]
            
            widgets["progress_widget"].set_value(val, meta["max"], meta["unit"])
            
            if val is not None:
                if "temp" in key:
                    widgets["value_label"].setText(f"{val}{meta['unit']}")
                else:
                    widgets["value_label"].setText(f"{val:.1f}{meta['unit']}")
            else:
                widgets["value_label"].setText("N/A")
                
    def position_above_clock(self):
        screen = QApplication.primaryScreen()
        geom = screen.availableGeometry()
        
        x = geom.right() - self.width() - 10
        y = geom.bottom() - self.height() - 10
        self.move(x, y)
        
    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow():
            self.hide()
        super().changeEvent(event)


class MeterTray(QObject):
    """The central tray controller, managing a series of individual system tray icons in custom order"""
    def __init__(self, uninstall_callback=None, parent=None):
        super().__init__(parent)
        self.uninstall_callback = uninstall_callback
        
        self.cfg = config.load_config()
        self.tray_icons = []
        
        self.menu = QMenu()
        self.setup_menu()
        
        self.flyout = FlyoutPanel(self.open_config_dialog, self.quit_app)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_metrics)
        self.update_timer_interval()
        self.timer.start()
        
        self.rebuild_tray_icons()
        self.poll_metrics()
        
    def setup_menu(self):
        title_action = QAction("Taskbar Metering", self)
        title_font = QFont()
        title_font.setBold(True)
        title_action.setFont(title_font)
        title_action.setEnabled(False)
        self.menu.addAction(title_action)
        self.menu.addSeparator()
        
        open_flyout = QAction("Open Dashboard Menu", self)
        open_flyout.triggered.connect(self.toggle_flyout)
        self.menu.addAction(open_flyout)
        
        config_action = QAction("Configure Sensors & Order...", self)
        config_action.triggered.connect(self.open_config_dialog)
        self.menu.addAction(config_action)
        
        self.poll_menu = QMenu("Polling Interval", self.menu)
        self.poll_group = QActionGroup(self)
        intervals = [
            ("1 Second", 1),
            ("2 Seconds", 2),
            ("5 Seconds", 5),
            ("10 Seconds", 10),
            ("30 Seconds", 30)
        ]
        for label, sec in intervals:
            act = QAction(label, self, checkable=True)
            act.setChecked(self.cfg["poll_rate"] == sec)
            act.setData(sec)
            act.triggered.connect(self.on_poll_rate_changed)
            self.poll_group.addAction(act)
            self.poll_menu.addAction(act)
        self.menu.addMenu(self.poll_menu)
        
        self.startup_action = QAction("Launch on Startup", self, checkable=True)
        self.startup_action.setChecked(self.cfg.get("launch_on_startup", True))
        self.startup_action.triggered.connect(self.on_startup_toggled)
        self.menu.addAction(self.startup_action)
        
        self.menu.addSeparator()
        
        uninstall_action = QAction("Uninstall App...", self)
        uninstall_action.triggered.connect(self.trigger_uninstallation)
        self.menu.addAction(uninstall_action)
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.quit_app)
        self.menu.addAction(exit_action)
        
    def update_timer_interval(self):
        self.timer.setInterval(self.cfg["poll_rate"] * 1000)
        
    def on_poll_rate_changed(self):
        sender = self.sender()
        if sender:
            sec = sender.data()
            self.cfg["poll_rate"] = sec
            config.save_config(self.cfg)
            self.update_timer_interval()
            
    def on_startup_toggled(self):
        self.cfg["launch_on_startup"] = self.startup_action.isChecked()
        config.save_config(self.cfg)
        self.update_startup_registry()
        
    def update_startup_registry(self):
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            app_name = "TaskbarMetering"
            if self.cfg["launch_on_startup"]:
                exe_path = os.path.abspath(sys.argv[0])
                if " " in exe_path:
                    exe_path = f'"{exe_path}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f"{exe_path} --run")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception:
            pass
            
    def open_config_dialog(self):
        self.flyout.hide()
        dialog = SensorConfigDialog(self.on_config_saved)
        dialog.exec()
        
    def on_config_saved(self):
        self.cfg = config.load_config()
        self.flyout.rebuild_cards()
        self.rebuild_tray_icons()
        self.poll_metrics()
        
    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_flyout()
            
    def toggle_flyout(self):
        if self.flyout.isVisible():
            self.flyout.hide()
        else:
            self.flyout.position_above_clock()
            self.flyout.show()
            self.flyout.activateWindow()
            
    def rebuild_tray_icons(self):
        # Hide and clean up existing tray icons
        for _, icon in self.tray_icons:
            icon.hide()
            icon.deleteLater()
        self.tray_icons.clear()
        
        active_list = self.cfg.get("active_sensors", ["cpu_usage", "ram_usage"])
        active_list = [k for k in active_list if k in SENSOR_METADATA]
        
        if not active_list:
            active_list = ["cpu_usage"]
            
        # Create tray icons in normal order to match active_list sequence from left-to-right
        for key in active_list:
            tray_icon = QSystemTrayIcon(self)
            tray_icon.activated.connect(self.on_tray_activated)
            tray_icon.setContextMenu(self.menu)
            tray_icon.show()
            self.tray_icons.append((key, tray_icon))
            
    def poll_metrics(self):
        cpu_usage = metrics.get_cpu_usage()
        cpu_temp = metrics.get_cpu_temp()
        ram_usage = metrics.get_ram_usage()
        gpu_usage, gpu_temp = metrics.get_gpu_metrics()
        disk_usage_list = metrics.get_disk_usage()
        
        values = {
            "cpu_usage": cpu_usage,
            "cpu_temp": cpu_temp,
            "ram_usage": ram_usage,
            "gpu_usage": gpu_usage,
            "gpu_temp": gpu_temp
        }
        
        # Populate each dynamic disk partition usage and temperature
        for d in disk_usage_list:
            dev_name = d["device"]
            dev_clean = dev_name.lower().replace(':', '')
            
            usage_key = f"disk_usage_{dev_clean}"
            values[usage_key] = d["percent"]
            
            temp_key = f"disk_temp_{dev_clean}"
            values[temp_key] = metrics.get_drive_temp(dev_name)
        
        self.flyout.update_metrics(values)
        
        # Guard in case config mismatch
        if len(self.tray_icons) != len([k for k in self.cfg.get("active_sensors", []) if k in SENSOR_METADATA]):
            self.rebuild_tray_icons()
            
        for key, tray_icon in self.tray_icons:
            if key not in SENSOR_METADATA:
                continue
            meta = SENSOR_METADATA[key]
            val = values.get(key)
            
            icon = self.create_sensor_icon(key, val)
            tray_icon.setIcon(icon)
            
            if val is not None:
                if "temp" in key:
                    tooltip = f"{meta['label']}: {val}{meta['unit']}"
                else:
                    tooltip = f"{meta['label']}: {val:.1f}{meta['unit']}"
            else:
                tooltip = f"{meta['label']}: N/A"
            tray_icon.setToolTip(f"Taskbar Metering\n{tooltip}")
            
    def create_sensor_icon(self, key, val):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        meta = SENSOR_METADATA[key]
        color = QColor(meta["color"])
        
        # 1. Background dark ring
        bg_pen = QPen(QColor(50, 50, 55, 140), 2.5)
        painter.setPen(bg_pen)
        painter.drawEllipse(4, 4, 24, 24)
        
        # 2. Foreground active colored arc
        if val is not None:
            percent = min(max(val, 0.0), meta["max"])
            ratio = percent / meta["max"]
            span = -int(ratio * 360 * 16)
            
            fg_pen = QPen(color, 2.5)
            painter.setPen(fg_pen)
            painter.drawArc(4, 4, 24, 24, 90 * 16, span)
            
            # 3. Numeric text in center
            painter.setPen(QColor("#FFFFFF"))
            val_rounded = int(round(val))
            if val_rounded >= 100:
                font = QFont("Segoe UI", 8, QFont.Bold)
            else:
                font = QFont("Segoe UI", 9, QFont.Bold)
            painter.setFont(font)
            
            val_str = f"{val_rounded}"
            painter.drawText(pixmap.rect(), Qt.AlignCenter, val_str)
        else:
            # Unsupported/N/A dotted ring
            dot_pen = QPen(QColor(110, 110, 115), 2.5, Qt.DashLine)
            painter.setPen(dot_pen)
            painter.drawArc(4, 4, 24, 24, 0, 360 * 16)
            
            painter.setPen(QColor("#90A4AE"))
            font = QFont("Segoe UI", 9, QFont.Bold)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "--")
            
        painter.end()
        return QIcon(pixmap)
        
    def trigger_uninstallation(self):
        if self.uninstall_callback:
            self.uninstall_callback()
        else:
            self.quit_app()
            
    def quit_app(self):
        for _, icon in self.tray_icons:
            icon.hide()
        self.flyout.hide()
        metrics.cleanup_metrics()
        QApplication.quit()


def run_app(uninstall_callback=None):
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.tray_ref = MeterTray(uninstall_callback)
    sys.exit(app.exec())
