import os
import json

APP_VERSION = "1.2.0"

DEFAULT_CONFIG = {
    "active_sensors": [
        "cpu_usage",
        "ram_usage"
    ],
    "poll_rate": 5,  # in seconds
    "installed": False,
    "run_as_admin": False,
    "launch_on_startup": True,
    "show_companion_bar": True,
    "companion_compact_mode": False,
    "tray_icon_font_size": 10,
    "companion_font_size": 11,
    "thresholds": {},
    "hotkey_enabled": True
}

APP_IPC_SERVER_NAME = "TaskbarMeteringIPC"

def get_config_dir():
    # Store settings in standard Windows Local AppData
    appdata = os.environ.get("LOCALAPPDATA")
    if not appdata:
        appdata = os.path.expanduser("~")
    config_dir = os.path.join(appdata, "TaskbarMetering")
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

def get_config_path():
    return os.path.join(get_config_dir(), "config.json")

def load_config():
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                # Merge defaults to ensure any missing fields are populated
                merged = DEFAULT_CONFIG.copy()
                merged.update(config)
                return merged
        except Exception:
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(config):
    config_path = get_config_path()
    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
        return True
    except Exception:
        return False
