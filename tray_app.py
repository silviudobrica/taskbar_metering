import sys
import os
import time
import ctypes
from ctypes import wintypes
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QWidget, 
                             QLabel, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QListWidget, QListWidgetItem, QDialog, QAbstractItemView,
                             QGraphicsDropShadowEffect, QCheckBox, QFrame, QScrollArea)
from PySide6.QtGui import (QIcon, QPixmap, QPainter, QColor, QFont, QPen, 
                           QAction, QActionGroup, QCursor, QPainterPath, QGuiApplication,
                           QShortcut, QKeySequence)
from PySide6.QtCore import QTimer, Qt, QSize, QEvent, QObject, QSharedMemory
from PySide6.QtNetwork import QLocalServer, QLocalSocket

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
        dev_clean = dev_name.lower().replace(":", "").replace(" ", "_")
        
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


def send_ipc_command(command, timeout_ms=1200):
    socket = QLocalSocket()
    socket.connectToServer(config.APP_IPC_SERVER_NAME)
    if not socket.waitForConnected(timeout_ms):
        return False

    payload = f"{command.strip()}\n".encode("utf-8")
    socket.write(payload)
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.waitForReadyRead(timeout_ms)
    socket.disconnectFromServer()
    socket.waitForDisconnected(200)
    return True


class TaskbarAnchor:
    ABM_GETTASKBARPOS = 0x00000005

    class APPBARDATA(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uCallbackMessage", wintypes.UINT),
            ("uEdge", wintypes.UINT),
            ("rc", wintypes.RECT),
            ("lParam", ctypes.c_long),
        ]

    def _taskbar_rect(self):
        if os.name != "nt":
            return None
        try:
            data = self.APPBARDATA()
            data.cbSize = ctypes.sizeof(self.APPBARDATA)
            result = ctypes.windll.shell32.SHAppBarMessage(self.ABM_GETTASKBARPOS, ctypes.byref(data))
            if result:
                return data.rc
        except Exception:
            pass
        return None

    def _window_rect(self, hwnd):
        if not hwnd:
            return None
        rect = wintypes.RECT()
        if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return rect
        return None

    def _collect_taskbar_rects(self):
        """Collect primary and secondary taskbar rectangles on Windows."""
        rects = []
        if os.name != "nt":
            return rects

        try:
            user32 = ctypes.windll.user32

            primary = user32.FindWindowW("Shell_TrayWnd", None)
            primary_rect = self._window_rect(primary)
            if primary_rect:
                rects.append(primary_rect)

            after = 0
            while True:
                hwnd = user32.FindWindowExW(0, after, "Shell_SecondaryTrayWnd", None)
                if not hwnd:
                    break
                rect = self._window_rect(hwnd)
                if rect:
                    rects.append(rect)
                after = hwnd
        except Exception:
            pass

        # Fallback for cases where secondary taskbars are not exposed by class.
        if not rects:
            fallback = self._taskbar_rect()
            if fallback:
                rects.append(fallback)

        return rects

    def _intersection_area(self, a, b):
        left = max(int(a.left), int(b.left()))
        top = max(int(a.top), int(b.top()))
        right = min(int(a.right), int(b.right()))
        bottom = min(int(a.bottom), int(b.bottom()))
        if right <= left or bottom <= top:
            return 0
        return (right - left) * (bottom - top)

    def _taskbar_rect_for_screen(self, screen):
        if screen is None:
            return self._taskbar_rect()

        rects = self._collect_taskbar_rects()
        if not rects:
            return None

        geom = screen.geometry()
        best_rect = None
        best_area = 0
        for rect in rects:
            area = self._intersection_area(rect, geom)
            if area > best_area:
                best_area = area
                best_rect = rect

        if best_rect is not None:
            return best_rect

        # Fallback to any known taskbar if there was no overlap.
        return rects[0]

    def get_widget_position(self, width, height, margin=10):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return 0, 0

        geom = screen.geometry()
        avail = screen.availableGeometry()
        x = avail.right() - width - margin
        y = avail.bottom() - height - margin

        taskbar = self._taskbar_rect_for_screen(screen)
        if taskbar is not None:
            t_left = int(taskbar.left)
            t_top = int(taskbar.top)
            t_right = int(taskbar.right)
            t_bottom = int(taskbar.bottom)
            t_width = t_right - t_left
            t_height = t_bottom - t_top

            if t_width >= t_height:
                if t_top <= geom.top() + 4:
                    x = t_right - width - margin
                    y = t_bottom + margin
                else:
                    x = t_right - width - margin
                    y = t_top - height - margin
            else:
                if t_left <= geom.left() + 4:
                    x = t_right + margin
                    y = avail.bottom() - height - margin
                else:
                    x = t_left - width - margin
                    y = avail.bottom() - height - margin

        x = max(geom.left() + margin, min(x, geom.right() - width - margin))
        y = max(geom.top() + margin, min(y, geom.bottom() - height - margin))
        return x, y


class CircularProgress(QWidget):
    """Custom premium widget representing a circular metric meter in the flyout"""
    def __init__(self, color_hex, font_size=10, parent=None):
        super().__init__(parent)
        self.color = QColor(color_hex)
        self.value = 0.0
        self.max_val = 100
        self.unit = "%"
        self.font_size = max(8, min(24, int(font_size)))
        self.update_size()

    def update_size(self):
        # Keep gauge growth strong but bounded so labels and cards can still fit.
        size = 48 + max(0, (self.font_size - 10) * 3)
        self.setFixedSize(size, size)
        self.update()

    def set_font_size(self, font_size):
        new_size = max(8, min(24, int(font_size)))
        if new_size != self.font_size:
            self.font_size = new_size
            self.update_size()
        
    def set_value(self, val, max_val=100, unit="%"):
        self.value = val
        self.max_val = max_val
        self.unit = unit
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        def fit_font(text, preferred_size, min_size=7):
            target = text_rect
            size = max(min_size, int(preferred_size))
            while size >= min_size:
                font = QFont("Segoe UI", size, QFont.Bold)
                painter.setFont(font)
                metrics = painter.fontMetrics()
                if metrics.horizontalAdvance(text) <= target.width() and metrics.height() <= target.height():
                    return font
                size -= 1
            return QFont("Segoe UI", min_size, QFont.Bold)
        
        size = self.width()
        pad = max(3, int(size * 0.07))
        diameter = size - (2 * pad)
        pen_w = max(2.2, size * 0.075)
        inner_pad = int(pad + pen_w + 1)
        text_rect = self.rect().adjusted(inner_pad, inner_pad, -inner_pad, -inner_pad)
        
        # Background arc
        bg_pen = QPen(QColor(42, 42, 48), pen_w)
        painter.setPen(bg_pen)
        painter.drawEllipse(pad, pad, diameter, diameter)
        
        if self.value is None:
            # Draw dotted gray circle for unsupported
            dot_pen = QPen(QColor(90, 90, 95), pen_w, Qt.DashLine)
            painter.setPen(dot_pen)
            painter.drawEllipse(pad, pad, diameter, diameter)
            
            painter.setPen(QColor("#78909C"))
            font = fit_font("--", max(7, self.font_size - 1))
            painter.setFont(font)
            painter.drawText(text_rect, Qt.AlignCenter, "--")
        else:
            percent = min(max(self.value, 0.0), self.max_val)
            ratio = percent / self.max_val
            span = -int(ratio * 360 * 16)
            
            fg_pen = QPen(self.color, pen_w)
            painter.setPen(fg_pen)
            painter.drawArc(pad, pad, diameter, diameter, 90 * 16, span)
            
            # Value in center
            painter.setPen(QColor("#FFFFFF"))
            val_str = f"{int(round(self.value))}"
            preferred = self.font_size - 1 if len(val_str) >= 3 else self.font_size
            painter.setFont(fit_font(val_str, preferred))
            painter.drawText(text_rect, Qt.AlignCenter, val_str)
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
        self.anchor = TaskbarAnchor()
        self.init_ui()
        self._connect_screen_signals()

        self._reanchor_timer = QTimer(self)
        self._reanchor_timer.setInterval(1500)
        self._reanchor_timer.timeout.connect(self._reanchor_if_visible)
        self._reanchor_timer.start()
        
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
            QLabel#MetricSub {
                font-size: 10px;
                color: #607D8B;
            }
            QLabel#Hint {
                font-size: 10px;
                color: #78909C;
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

        self.shortcut_hint = QLabel(
            "Shortcuts: Ctrl +/- tray size, Ctrl+Shift +/- companion size",
            self
        )
        self.shortcut_hint.setObjectName("Hint")
        self.shortcut_hint.setWordWrap(True)
        layout.addWidget(self.shortcut_hint)
        
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
        
        font_size = self.cfg.get("tray_icon_font_size", 10)
        # Keep dashboard gauges and text readable even when tray icon size is small.
        gauge_font_size = min(20, max(12, int(font_size)))
        gauge_size = 48 + max(0, (gauge_font_size - 10) * 3)
        card_height = max(88, gauge_size + 24)
        
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
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(12)
            card_widget.setFixedHeight(card_height)
            
            progress = CircularProgress(meta["color"], font_size=gauge_font_size, parent=card_widget)
            card_layout.addWidget(progress)
            
            text_layout = QVBoxLayout()
            text_layout.setSpacing(4)
            text_layout.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(meta["label"])
            lbl.setObjectName("MetricLabel")
            lbl.setMinimumWidth(120)
            val_lbl = QLabel("--")
            val_lbl.setObjectName("MetricVal")
            val_lbl.setMinimumWidth(120)
            sub_lbl = QLabel("Waiting for sample")
            sub_lbl.setObjectName("MetricSub")
            sub_lbl.setMinimumWidth(120)
            text_layout.addWidget(lbl)
            text_layout.addWidget(val_lbl)
            text_layout.addWidget(sub_lbl)
            card_layout.addLayout(text_layout)
            
            card_layout.addStretch()
            
            self.list_layout.addWidget(card_widget)
            self.cards[key] = {
                "progress_widget": progress,
                "value_label": val_lbl,
                "status_label": sub_lbl,
                "meta": meta
            }
            
        item_count = len(self.cards)
        item_height = card_height
        dyn_height = 170 + (item_count * item_height)
        dashboard_width = min(520, max(360, gauge_size + 250))
        self.setFixedSize(dashboard_width, min(max(dyn_height, 300), 680))
        self.main_container.setFixedSize(self.width(), self.height())
        
    def update_metrics(self, values, freshness=None):
        freshness = freshness or {}
        for key, widgets in self.cards.items():
            val = values.get(key)
            meta = widgets["meta"]
            fresh_info = freshness.get(key, {})
            
            widgets["progress_widget"].set_value(val, meta["max"], meta["unit"])
            
            if val is not None:
                if "temp" in key:
                    widgets["value_label"].setText(f"{val}{meta['unit']}")
                else:
                    widgets["value_label"].setText(f"{val:.1f}{meta['unit']}")
            else:
                widgets["value_label"].setText("N/A")

            widgets["status_label"].setText(self._format_freshness(fresh_info, val))
                
    def position_above_clock(self):
        x, y = self.anchor.get_widget_position(self.width(), self.height(), margin=10)
        self.move(x, y)

    def _connect_screen_signals(self):
        app = QGuiApplication.instance()
        if app is None:
            return

        app.screenAdded.connect(lambda _screen: self._schedule_reanchor())
        app.screenRemoved.connect(lambda _screen: self._schedule_reanchor())
        for screen in app.screens():
            try:
                screen.geometryChanged.connect(lambda _geom: self._schedule_reanchor())
                screen.availableGeometryChanged.connect(lambda _geom: self._schedule_reanchor())
            except Exception:
                pass

    def _schedule_reanchor(self):
        QTimer.singleShot(120, self._reanchor_if_visible)

    def _reanchor_if_visible(self):
        if self.isVisible():
            self.position_above_clock()

    def _format_freshness(self, info, value):
        if value is None:
            return "Unavailable"

        state = info.get("state", "fresh")
        updated_at = info.get("updated_at")
        if updated_at is None:
            return "Live sample"

        age = max(0, int(time.time() - updated_at))
        if state == "cached":
            return f"Cached {age}s ago"
        return "Live sample"
        
    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow():
            self.hide()
        super().changeEvent(event)


class TaskbarCompanionBar(QWidget):
    """Compact always-on bar anchored near the clock with live metric text."""
    def __init__(self, menu, toggle_flyout_callback, text_size=11, parent=None):
        super().__init__(parent)
        self.menu = menu
        self.toggle_flyout_callback = toggle_flyout_callback
        self.anchor = TaskbarAnchor()
        self.labels = {}
        self.active_keys = []
        self.hidden_count = 0
        self._last_layout_limit = None
        self.compact_three_mode = False
        self.text_size = max(8, min(18, int(text_size)))

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self.container = QWidget(self)
        self.container.setObjectName("CompanionContainer")
        self.container.setStyleSheet("""
            QWidget#CompanionContainer {
                background-color: rgba(18, 18, 20, 0.88);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
            }
            QLabel#CompanionMetric {
                color: #ECEFF1;
                font-weight: bold;
                padding: 0 2px;
            }
        """)

        self.layout_main = QHBoxLayout(self.container)
        self.layout_main.setContentsMargins(10, 6, 10, 6)
        self.layout_main.setSpacing(10)

        self.rebuild_sensors(["cpu_usage", "ram_usage"])

        self._anchor_timer = QTimer(self)
        self._anchor_timer.setInterval(1500)
        self._anchor_timer.timeout.connect(self.reanchor)
        self._anchor_timer.start()

        self.show()
        self.reanchor()

    def rebuild_sensors(self, active_keys):
        self.active_keys = [k for k in active_keys if k in SENSOR_METADATA]

        while self.layout_main.count():
            child = self.layout_main.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.labels.clear()
        visible_keys = self._compute_visible_keys()
        self.hidden_count = max(0, len(self.active_keys) - len(visible_keys))

        for key in visible_keys:
            label = QLabel(f"{SENSOR_METADATA[key]['short']}: --")
            label.setObjectName("CompanionMetric")
            label.setFont(QFont("Segoe UI", self.text_size, QFont.Bold))
            self.layout_main.addWidget(label)
            self.labels[key] = label

        if self.hidden_count > 0:
            more = QLabel(f"+{self.hidden_count}")
            more.setObjectName("CompanionMetric")
            more.setFont(QFont("Segoe UI", self.text_size, QFont.Bold))
            more.setToolTip("Additional sensors are hidden due to limited taskbar space")
            self.layout_main.addWidget(more)

        self.layout_main.addStretch()
        self._resize_to_content()

    def set_compact_mode(self, enabled):
        self.compact_three_mode = bool(enabled)
        self.rebuild_sensors(self.active_keys)

    def set_text_size(self, size):
        clamped = max(8, min(18, int(size)))
        if clamped != self.text_size:
            self.text_size = clamped
            self.rebuild_sensors(self.active_keys)

    def update_metrics(self, values, freshness):
        for key, label in self.labels.items():
            meta = SENSOR_METADATA.get(key)
            if not meta:
                continue
            val = values.get(key)
            info = freshness.get(key, {})
            state = info.get("state", "fresh")
            suffix = "*" if state == "cached" else ""

            if val is None:
                label.setText(f"{meta['short']}: N/A")
            elif "temp" in key:
                label.setText(f"{meta['short']}: {val}{meta['unit']}{suffix}")
            else:
                label.setText(f"{meta['short']}: {val:.0f}{meta['unit']}{suffix}")

        self._resize_to_content()
        self.reanchor()

    def _resize_to_content(self):
        self.container.adjustSize()
        width_limit = self._get_width_limit()
        width = max(220, min(self.container.sizeHint().width(), width_limit))
        height = max(32, self.container.sizeHint().height())
        self.setFixedSize(width, height)
        self.container.setFixedSize(width, height)

    def _get_width_limit(self):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return 520
        avail = screen.availableGeometry().width()
        return max(240, min(560, int(avail * 0.45)))

    def _compute_visible_keys(self):
        if self.compact_three_mode:
            return self.active_keys[:3]

        width_limit = self._get_width_limit()
        self._last_layout_limit = width_limit

        # Approximate per-metric width budget in this compact bar.
        slot_width = 92
        base_padding = 24
        capacity = max(1, int((width_limit - base_padding) / slot_width))

        if len(self.active_keys) <= capacity:
            return self.active_keys

        # Reserve one slot for +N overflow indicator when truncated.
        visible_capacity = max(1, capacity - 1)
        return self.active_keys[:visible_capacity]

    def _refresh_layout_if_needed(self):
        current_limit = self._get_width_limit()
        if self._last_layout_limit is None or abs(current_limit - self._last_layout_limit) >= 20:
            self.rebuild_sensors(self.active_keys)

    def _show_context_menu(self, _pos):
        self.menu.exec(QCursor.pos())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_flyout_callback()
        elif event.button() == Qt.RightButton:
            self.menu.exec(QCursor.pos())
        super().mousePressEvent(event)

    def reanchor(self):
        self._refresh_layout_if_needed()
        x, y = self.anchor.get_widget_position(self.width(), self.height(), margin=8)
        self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        self.reanchor()


class MeterTray(QObject):
    """The central tray controller, managing a series of individual system tray icons in custom order"""
    def __init__(self, uninstall_callback=None, parent=None):
        super().__init__(parent)
        self.uninstall_callback = uninstall_callback
        
        self.cfg = config.load_config()
        self.tray_icons = []
        
        self.menu = QMenu()
        self.setup_menu()

        self._ipc_server = None
        self.setup_ipc_server()
        
        self.flyout = FlyoutPanel(self.open_config_dialog, self.quit_app)
        self.companion_bar = TaskbarCompanionBar(
            self.menu,
            self.toggle_flyout,
            text_size=self.cfg.get("companion_font_size", 11)
        )
        self._setup_flyout_shortcuts()
        self.companion_bar.rebuild_sensors(self.cfg.get("active_sensors", ["cpu_usage", "ram_usage"]))
        self.companion_bar.set_compact_mode(self.cfg.get("companion_compact_mode", False))
        self.apply_companion_visibility()

        # Keep expensive temperature probes off the UI polling path.
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._cpu_temp_future = None
        self._cpu_temp_cache = None
        self._cpu_temp_updated_at = None
        self._cpu_temp_last_request = 0.0
        self._cpu_temp_min_interval = 10.0
        self._disk_temp_futures = {}
        self._disk_temp_cache = {}
        self._disk_temp_updated_at = {}
        self._disk_temp_last_request = {}
        self._disk_temp_min_interval = 20.0
        
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

        self.icon_size_menu = QMenu("Tray Icon Number Size", self.menu)
        self.icon_size_group = QActionGroup(self)
        for size in (8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 22, 24):
            act = QAction(f"{size} pt", self, checkable=True)
            act.setChecked(self.cfg.get("tray_icon_font_size", 10) == size)
            act.setData(size)
            act.triggered.connect(self.on_tray_icon_size_changed)
            self.icon_size_group.addAction(act)
            self.icon_size_menu.addAction(act)
        tray_size_up = QAction("Increase Tray Number Size (+)", self)
        tray_size_up.triggered.connect(self.increase_tray_icon_size)
        tray_size_down = QAction("Decrease Tray Number Size (-)", self)
        tray_size_down.triggered.connect(self.decrease_tray_icon_size)
        self.menu.addAction(tray_size_up)
        self.menu.addAction(tray_size_down)
        self.menu.addMenu(self.icon_size_menu)

        self.companion_font_menu = QMenu("Companion Text Size", self.menu)
        self.companion_font_group = QActionGroup(self)
        for size in (9, 10, 11, 12, 13, 14, 15, 16):
            act = QAction(f"{size} pt", self, checkable=True)
            act.setChecked(self.cfg.get("companion_font_size", 11) == size)
            act.setData(size)
            act.triggered.connect(self.on_companion_text_size_changed)
            self.companion_font_group.addAction(act)
            self.companion_font_menu.addAction(act)
        comp_size_up = QAction("Increase Companion Text Size (+)", self)
        comp_size_up.triggered.connect(self.increase_companion_text_size)
        comp_size_down = QAction("Decrease Companion Text Size (-)", self)
        comp_size_down.triggered.connect(self.decrease_companion_text_size)
        self.menu.addAction(comp_size_up)
        self.menu.addAction(comp_size_down)
        self.menu.addMenu(self.companion_font_menu)
        
        self.startup_action = QAction("Launch on Startup", self, checkable=True)
        self.startup_action.setChecked(self.cfg.get("launch_on_startup", True))
        self.startup_action.triggered.connect(self.on_startup_toggled)
        self.menu.addAction(self.startup_action)

        self.companion_action = QAction("Show Taskbar Companion Bar", self, checkable=True)
        self.companion_action.setChecked(self.cfg.get("show_companion_bar", True))
        self.companion_action.triggered.connect(self.on_companion_bar_toggled)
        self.menu.addAction(self.companion_action)

        self.companion_compact_action = QAction("Companion Compact Mode (3 Metrics)", self, checkable=True)
        self.companion_compact_action.setChecked(self.cfg.get("companion_compact_mode", False))
        self.companion_compact_action.triggered.connect(self.on_companion_compact_toggled)
        self.menu.addAction(self.companion_compact_action)
        
        self.menu.addSeparator()
        
        uninstall_action = QAction("Uninstall App...", self)
        uninstall_action.triggered.connect(self.trigger_uninstallation)
        self.menu.addAction(uninstall_action)
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.quit_app)
        self.menu.addAction(exit_action)

    def _setup_flyout_shortcuts(self):
        # Shortcuts are active only while the dashboard (flyout) has focus.
        self._flyout_shortcuts = []

        tray_inc_keys = ["Ctrl++", "Ctrl+="]
        tray_dec_keys = ["Ctrl+-", "Ctrl+_"]
        companion_inc_keys = ["Ctrl+Shift++", "Ctrl+Shift+="]
        companion_dec_keys = ["Ctrl+Shift+-", "Ctrl+Shift+_"]

        for seq in tray_inc_keys:
            shortcut = QShortcut(QKeySequence(seq), self.flyout)
            shortcut.activated.connect(self.increase_tray_icon_size)
            self._flyout_shortcuts.append(shortcut)

        for seq in tray_dec_keys:
            shortcut = QShortcut(QKeySequence(seq), self.flyout)
            shortcut.activated.connect(self.decrease_tray_icon_size)
            self._flyout_shortcuts.append(shortcut)

        for seq in companion_inc_keys:
            shortcut = QShortcut(QKeySequence(seq), self.flyout)
            shortcut.activated.connect(self.increase_companion_text_size)
            self._flyout_shortcuts.append(shortcut)

        for seq in companion_dec_keys:
            shortcut = QShortcut(QKeySequence(seq), self.flyout)
            shortcut.activated.connect(self.decrease_companion_text_size)
            self._flyout_shortcuts.append(shortcut)
        
    def update_timer_interval(self):
        self.timer.setInterval(self.cfg["poll_rate"] * 1000)
        
    def on_poll_rate_changed(self):
        sender = self.sender()
        if sender:
            sec = sender.data()
            self.cfg["poll_rate"] = sec
            config.save_config(self.cfg)
            self.update_timer_interval()

    def on_tray_icon_size_changed(self):
        sender = self.sender()
        if sender:
            self._set_tray_icon_size(int(sender.data()))

    def increase_tray_icon_size(self):
        self._set_tray_icon_size(self.cfg.get("tray_icon_font_size", 10) + 1)

    def decrease_tray_icon_size(self):
        self._set_tray_icon_size(self.cfg.get("tray_icon_font_size", 10) - 1)

    def _set_tray_icon_size(self, size):
        clamped = max(8, min(24, int(size)))
        self.cfg["tray_icon_font_size"] = clamped
        config.save_config(self.cfg)

        for act in self.icon_size_group.actions():
            act.setChecked(int(act.data()) == clamped)

        # Rebuild flyout cards so both gauge geometry and panel size are recalculated.
        was_visible = self.flyout.isVisible()
        if was_visible:
            # Hide briefly to force a clean Qt layout recalculation on resize down
            self.flyout.hide()

        self.flyout.rebuild_cards()
        
        if was_visible:
            self.flyout.position_above_clock()
            self.flyout.show()
            self.flyout.activateWindow()

        self.poll_metrics()

    def on_companion_text_size_changed(self):
        sender = self.sender()
        if sender:
            self._set_companion_text_size(int(sender.data()))

    def increase_companion_text_size(self):
        self._set_companion_text_size(self.cfg.get("companion_font_size", 11) + 1)

    def decrease_companion_text_size(self):
        self._set_companion_text_size(self.cfg.get("companion_font_size", 11) - 1)

    def _set_companion_text_size(self, size):
        clamped = max(8, min(18, int(size)))
        self.cfg["companion_font_size"] = clamped
        config.save_config(self.cfg)

        for act in self.companion_font_group.actions():
            act.setChecked(int(act.data()) == clamped)

        self.companion_bar.set_text_size(clamped)
        self.companion_bar.reanchor()
            
    def on_startup_toggled(self):
        self.cfg["launch_on_startup"] = self.startup_action.isChecked()
        config.save_config(self.cfg)
        self.update_startup_registry()

    def on_companion_bar_toggled(self):
        self.cfg["show_companion_bar"] = self.companion_action.isChecked()
        config.save_config(self.cfg)
        self.apply_companion_visibility()

    def on_companion_compact_toggled(self):
        enabled = self.companion_compact_action.isChecked()
        self.cfg["companion_compact_mode"] = enabled
        config.save_config(self.cfg)
        self.companion_bar.set_compact_mode(enabled)
        self.poll_metrics()

    def apply_companion_visibility(self):
        should_show = self.cfg.get("show_companion_bar", True)
        if should_show:
            self.companion_bar.show()
            self.companion_bar.reanchor()
        else:
            self.companion_bar.hide()
        
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
        self.companion_bar.set_compact_mode(self.cfg.get("companion_compact_mode", False))
        self.companion_bar.set_text_size(self.cfg.get("companion_font_size", 11))
        self.flyout.rebuild_cards()
        self.companion_bar.rebuild_sensors(self.cfg.get("active_sensors", ["cpu_usage", "ram_usage"]))
        # Also update gauge sizes in existing cards
        font_size = self.cfg.get("tray_icon_font_size", 10)
        for card_info in self.flyout.cards.values():
            card_info["progress_widget"].set_font_size(font_size)
        if hasattr(self, "companion_action"):
            self.companion_action.setChecked(self.cfg.get("show_companion_bar", True))
        if hasattr(self, "companion_compact_action"):
            self.companion_compact_action.setChecked(self.cfg.get("companion_compact_mode", False))
        if hasattr(self, "icon_size_group"):
            for act in self.icon_size_group.actions():
                act.setChecked(int(act.data()) == int(self.cfg.get("tray_icon_font_size", 10)))
        if hasattr(self, "companion_font_group"):
            for act in self.companion_font_group.actions():
                act.setChecked(int(act.data()) == int(self.cfg.get("companion_font_size", 11)))
        self.apply_companion_visibility()
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
            
        # Create tray icons in reversed order because Windows prepends new system tray icons
        # (meaning the last one registered is shown on the left). Reversing this ensures
        # the taskbar layout matches active_list sequence from left-to-right.
        for key in reversed(active_list):
            tray_icon = QSystemTrayIcon(self)
            tray_icon.activated.connect(self.on_tray_activated)
            tray_icon.setContextMenu(self.menu)
            tray_icon.show()
            self.tray_icons.append((key, tray_icon))
            
    def poll_metrics(self):
        now = time.monotonic()
        wall_now = time.time()
        cpu_usage = metrics.get_cpu_usage()
        cpu_temp, cpu_temp_info = self._get_cpu_temp_cached(now)
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
        freshness = {
            "cpu_usage": {"state": "fresh", "updated_at": wall_now},
            "cpu_temp": cpu_temp_info,
            "ram_usage": {"state": "fresh", "updated_at": wall_now},
            "gpu_usage": {"state": "fresh", "updated_at": wall_now},
            "gpu_temp": {"state": "fresh", "updated_at": wall_now},
        }
        
        # Populate each dynamic disk partition usage and temperature
        for d in disk_usage_list:
            dev_name = d["device"]
            dev_clean = dev_name.lower().replace(':', '').replace(' ', '_')
            
            usage_key = f"disk_usage_{dev_clean}"
            values[usage_key] = d["percent"]
            freshness[usage_key] = {"state": "fresh", "updated_at": wall_now}
            
            temp_key = f"disk_temp_{dev_clean}"
            values[temp_key], freshness[temp_key] = self._get_drive_temp_cached(dev_name, now)
        
        self.flyout.update_metrics(values, freshness)
        self.companion_bar.update_metrics(values, freshness)
        
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
            if freshness.get(key, {}).get("state") == "cached":
                tooltip = f"{tooltip} (cached)"
            tray_icon.setToolTip(f"Taskbar Metering\n{tooltip}")
            
    def create_sensor_icon(self, key, val):
        base_font_size = int(self.cfg.get("tray_icon_font_size", 10))
        base_font_size = max(8, min(24, base_font_size))

        # Windows notification area downscales aggressively; keeping 32px yields crisper numerals.
        icon_size = 32
        pixmap = QPixmap(icon_size, icon_size)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        meta = SENSOR_METADATA[key]
        color = QColor(meta["color"])

        # Scale visual weight within fixed 32x32 tray slot.
        scale = (base_font_size - 8) / 16.0
        pad = max(1, 4 - int(scale * 3))
        diameter = icon_size - (2 * pad)
        pen_w = 2.0 + (scale * 1.2)
        text_inset = max(2, 8 - int(scale * 6))
        text_rect = pixmap.rect().adjusted(text_inset, text_inset, -text_inset, -text_inset)

        def fit_font(text, preferred_size, min_size=7):
            size = max(min_size, int(preferred_size))
            while size >= min_size:
                font = QFont("Segoe UI", size, QFont.Bold)
                painter.setFont(font)
                metrics = painter.fontMetrics()
                if metrics.horizontalAdvance(text) <= text_rect.width() and metrics.height() <= text_rect.height():
                    return font
                size -= 1
            return QFont("Segoe UI", min_size, QFont.Bold)
        
        # 1. Background dark ring
        bg_pen = QPen(QColor(50, 50, 55, 140), pen_w)
        painter.setPen(bg_pen)
        painter.drawEllipse(pad, pad, diameter, diameter)
        
        # 2. Foreground active colored arc
        if val is not None:
            percent = min(max(val, 0.0), meta["max"])
            ratio = percent / meta["max"]
            span = -int(ratio * 360 * 16)
            
            fg_pen = QPen(color, pen_w)
            painter.setPen(fg_pen)
            painter.drawArc(pad, pad, diameter, diameter, 90 * 16, span)
            
            # 3. Numeric text in center
            painter.setPen(QColor("#FFFFFF"))
            val_rounded = int(round(val))
            val_str = f"{val_rounded}"
            preferred = min(28, max(10, base_font_size + 5))
            if len(val_str) >= 3:
                preferred -= 2
            font = fit_font(val_str, preferred)
            painter.setFont(font)
            
            painter.drawText(text_rect, Qt.AlignCenter, val_str)
        else:
            # Unsupported/N/A dotted ring
            dot_pen = QPen(QColor(110, 110, 115), pen_w, Qt.DashLine)
            painter.setPen(dot_pen)
            painter.drawArc(pad, pad, diameter, diameter, 0, 360 * 16)
            
            painter.setPen(QColor("#90A4AE"))
            font = fit_font("--", max(7, base_font_size - 1))
            painter.setFont(font)
            painter.drawText(text_rect, Qt.AlignCenter, "--")
            
        painter.end()
        return QIcon(pixmap)
        
    def trigger_uninstallation(self):
        if self.uninstall_callback:
            self.uninstall_callback()
        else:
            self.quit_app()

    def setup_ipc_server(self):
        try:
            QLocalServer.removeServer(config.APP_IPC_SERVER_NAME)
        except Exception:
            pass

        self._ipc_server = QLocalServer(self)
        self._ipc_server.newConnection.connect(self._on_ipc_connection)
        self._ipc_server.listen(config.APP_IPC_SERVER_NAME)

    def _on_ipc_connection(self):
        while self._ipc_server and self._ipc_server.hasPendingConnections():
            socket = self._ipc_server.nextPendingConnection()
            socket.readyRead.connect(lambda s=socket: self._handle_ipc_socket(s))
            socket.disconnected.connect(socket.deleteLater)

    def _handle_ipc_socket(self, socket):
        raw = bytes(socket.readAll()).decode("utf-8", errors="ignore")
        commands = [line.strip().upper() for line in raw.splitlines() if line.strip()]
        for cmd in commands:
            if cmd in ("EXIT", "UNINSTALL"):
                QTimer.singleShot(0, self.quit_app)
            elif cmd in ("SHOW", "TOGGLE"):
                QTimer.singleShot(0, self.toggle_flyout)

        try:
            socket.write(b"OK\n")
            socket.flush()
        except Exception:
            pass
        socket.disconnectFromServer()

    def _get_cpu_temp_cached(self, now):
        completed_now = False
        if self._cpu_temp_future and self._cpu_temp_future.done():
            try:
                self._cpu_temp_cache = self._cpu_temp_future.result()
                self._cpu_temp_updated_at = time.time()
                completed_now = True
            except Exception:
                pass
            self._cpu_temp_future = None

        if self._cpu_temp_future is None and (now - self._cpu_temp_last_request) >= self._cpu_temp_min_interval:
            self._cpu_temp_last_request = now
            self._cpu_temp_future = self._executor.submit(metrics.get_cpu_temp)

        state = "fresh" if completed_now else ("cached" if self._cpu_temp_cache is not None else "unknown")
        return self._cpu_temp_cache, {"state": state, "updated_at": getattr(self, "_cpu_temp_updated_at", None)}

    def _get_drive_temp_cached(self, drive_letter, now):
        completed_now = False
        future = self._disk_temp_futures.get(drive_letter)
        if future and future.done():
            try:
                self._disk_temp_cache[drive_letter] = future.result()
                self._disk_temp_updated_at[drive_letter] = time.time()
                completed_now = True
            except Exception:
                pass
            self._disk_temp_futures.pop(drive_letter, None)

        last_req = self._disk_temp_last_request.get(drive_letter, 0.0)
        if drive_letter not in self._disk_temp_futures and (now - last_req) >= self._disk_temp_min_interval:
            self._disk_temp_last_request[drive_letter] = now
            self._disk_temp_futures[drive_letter] = self._executor.submit(metrics.get_drive_temp, drive_letter)

        val = self._disk_temp_cache.get(drive_letter)
        state = "fresh" if completed_now else ("cached" if val is not None else "unknown")
        return val, {"state": state, "updated_at": self._disk_temp_updated_at.get(drive_letter)}
            
    def quit_app(self):
        for _, icon in self.tray_icons:
            icon.hide()
        self.companion_bar.hide()
        self.flyout.hide()
        if self._ipc_server:
            try:
                self._ipc_server.close()
                QLocalServer.removeServer(config.APP_IPC_SERVER_NAME)
            except Exception:
                pass
        self._executor.shutdown(wait=False)
        metrics.cleanup_metrics()
        QApplication.quit()


def run_app(uninstall_callback=None):
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    singleton = QSharedMemory("TaskbarMeteringSingleton")
    if not singleton.create(1):
        send_ipc_command("SHOW")
        return
    app.singleton_lock = singleton

    app.tray_ref = MeterTray(uninstall_callback)
    sys.exit(app.exec())
