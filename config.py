import os
import json
import sys
import winreg

# AppData configuration directory
APP_DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'ZeroAudio')
CONFIG_FILE = os.path.join(APP_DATA_DIR, 'config.json')

DEFAULT_CONFIG = {
    "hotkeys": {
        "mic_mute":    {"type": "vk", "value": 111, "display": "Numpad /"},
        "sound_mute":  {"type": "vk", "value": 106, "display": "Numpad *"},
        "volume_up":   {"type": "vk", "value": 107, "display": "Numpad +"},
        "volume_down": {"type": "vk", "value": 109, "display": "Numpad -"}
    },
    "volume_step": 0.05,        # 5% step per key press

    # --- Startup / System ---
    "run_on_startup": False,

    # --- OSD toggles ---
    "osd_on_mic_mute":   True,   # Show OSD when mic is muted/unmuted
    "osd_on_sound_mute": True,   # Show OSD when speakers are muted/unmuted
    "osd_on_volume":     True,   # Show OSD when volume is changed
}

class ConfigManager:
    def __init__(self):
        self.config = {}
        self._load_defaults()
        self.load()

    def _load_defaults(self):
        import copy
        self.config = copy.deepcopy(DEFAULT_CONFIG)

    def load(self):
        """Load configuration from file, merging over defaults."""
        if not os.path.exists(APP_DATA_DIR):
            try:
                os.makedirs(APP_DATA_DIR)
            except Exception as e:
                print(f"Error creating AppData dir: {e}")

        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self._merge_dicts(self.config, loaded)
            except Exception as e:
                print(f"Error loading config: {e}")
        else:
            self.save()

    def _merge_dicts(self, target, source):
        """Recursively merge source into target."""
        for k, v in source.items():
            if k in target and isinstance(target[k], dict) and isinstance(v, dict):
                self._merge_dicts(target[k], v)
            else:
                target[k] = v

    def save(self):
        """Persist config to disk."""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def update_hotkey(self, name, key_data):
        if name in self.config["hotkeys"]:
            self.config["hotkeys"][name] = key_data
            self.save()

    def set_volume_step(self, step):
        self.config["volume_step"] = max(0.01, min(0.20, step))
        self.save()

    def set(self, key, value):
        """Generic setter for any top-level boolean or numeric setting."""
        self.config[key] = value
        self.save()
        if key == "run_on_startup":
            self.apply_startup_setting(bool(value))

    # Keep legacy shim used from older signal connections
    def toggle_bool_setting(self, key, value):
        self.set(key, bool(value))

    def apply_startup_setting(self, enabled):
        """Add/remove registry entry for Windows startup."""
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "ZeroAudio"
        if getattr(sys, 'frozen', False):
            cmd = f'"{sys.executable}"'
        else:
            python_exe = sys.executable.replace("python.exe", "pythonw.exe")
            script_path = os.path.abspath(sys.argv[0])
            cmd = f'"{python_exe}" "{script_path}"'
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
            if enabled:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            return True
        except Exception as e:
            print(f"Registry error: {e}")
            return False
