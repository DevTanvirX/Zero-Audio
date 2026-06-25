from pynput import keyboard

# Virtual Key (VK) code friendly names mapping for Windows
VK_FRIENDLY_NAMES = {
    # Numpad keys
    96: "Numpad 0",
    97: "Numpad 1",
    98: "Numpad 2",
    99: "Numpad 3",
    100: "Numpad 4",
    101: "Numpad 5",
    102: "Numpad 6",
    103: "Numpad 7",
    104: "Numpad 8",
    105: "Numpad 9",
    106: "Numpad *",
    107: "Numpad +",
    108: "Numpad Enter",
    109: "Numpad -",
    110: "Numpad .",
    111: "Numpad /",
    
    # Arrow keys and standard control keys
    37: "Left Arrow",
    38: "Up Arrow",
    39: "Right Arrow",
    40: "Down Arrow",
    45: "Insert",
    46: "Delete",
    33: "Page Up",
    34: "Page Down",
    35: "End",
    36: "Home",
    27: "Escape",
    13: "Enter",
    32: "Space",
    8: "Backspace",
    9: "Tab",
    20: "Caps Lock",
    144: "Num Lock",
    145: "Scroll Lock",
    
    # Function keys
    112: "F1", 113: "F2", 114: "F3", 115: "F4", 116: "F5", 117: "F6",
    118: "F7", 119: "F8", 120: "F9", 121: "F10", 122: "F11", 123: "F12"
}

KEY_FRIENDLY_NAMES = {
    "Key.space": "Space",
    "Key.enter": "Enter",
    "Key.tab": "Tab",
    "Key.backspace": "Backspace",
    "Key.esc": "Escape",
    "Key.caps_lock": "Caps Lock",
    "Key.num_lock": "Num Lock",
    "Key.scroll_lock": "Scroll Lock",
    "Key.shift": "Shift",
    "Key.shift_r": "Right Shift",
    "Key.ctrl_l": "Ctrl",
    "Key.ctrl_r": "Right Ctrl",
    "Key.alt_l": "Alt",
    "Key.alt_r": "Right Alt",
    "Key.cmd": "Windows Key",
    "Key.menu": "Menu",
    "Key.print_screen": "Print Screen",
    "Key.pause": "Pause",
    "Key.insert": "Insert",
    "Key.delete": "Delete",
    "Key.home": "Home",
    "Key.end": "End",
    "Key.page_up": "Page Up",
    "Key.page_down": "Page Down",
    "Key.up": "Up Arrow",
    "Key.down": "Down Arrow",
    "Key.left": "Left Arrow",
    "Key.right": "Right Arrow",
    "Key.media_volume_up": "Media Volume Up",
    "Key.media_volume_down": "Media Volume Down",
    "Key.media_volume_mute": "Media Mute",
    "Key.media_play_pause": "Media Play/Pause",
    "Key.media_next": "Media Next",
    "Key.media_previous": "Media Previous"
}

def serialize_key(key):
    """Serialize a pynput key event into a dict for config saving."""
    if isinstance(key, keyboard.Key):
        key_str = str(key)
        friendly = KEY_FRIENDLY_NAMES.get(key_str, key_str.replace("Key.", "").replace("_", " ").title())
        return {"type": "name", "value": key_str, "display": friendly}
    elif isinstance(key, keyboard.KeyCode):
        # First priority: Check if VK is in our known friendly list (like Numpad keys)
        if key.vk is not None and key.vk in VK_FRIENDLY_NAMES:
            return {"type": "vk", "value": key.vk, "display": VK_FRIENDLY_NAMES[key.vk]}
        # Second priority: Standard character keys
        if key.char is not None:
            return {"type": "char", "value": key.char.lower(), "display": key.char.upper()}
        # Fallback: Virtual key code
        if key.vk is not None:
            return {"type": "vk", "value": key.vk, "display": f"VK {key.vk}"}
    return None

def keys_match(key_event, key_config):
    """Check if key_event matches a saved key_config dictionary."""
    if not key_config:
        return False
    
    cfg_type = key_config.get("type")
    cfg_val = key_config.get("value")
    
    if cfg_type == "name":
        return isinstance(key_event, keyboard.Key) and str(key_event) == cfg_val
    elif cfg_type == "vk":
        return isinstance(key_event, keyboard.KeyCode) and key_event.vk == cfg_val
    elif cfg_type == "char":
        return isinstance(key_event, keyboard.KeyCode) and key_event.char is not None and key_event.char.lower() == cfg_val
    return False

class GlobalHotkeyListener:
    def __init__(self, config_manager, action_callbacks):
        """
        config_manager: ConfigManager instance.
        action_callbacks: Dict mapping action name (e.g. 'mic_mute') to callable function.
        """
        self.config_manager = config_manager
        self.action_callbacks = action_callbacks
        self.recording_callback = None
        self.listener = None

    def start_recording(self, callback):
        """Put listener in recording mode, running callback with key_data on next keypress."""
        self.recording_callback = callback

    def cancel_recording(self):
        """Cancel recording mode."""
        self.recording_callback = None

    def _on_press(self, key):
        # Recording mode intercepts the press completely
        if self.recording_callback:
            key_data = serialize_key(key)
            if key_data:
                cb = self.recording_callback
                self.recording_callback = None
                cb(key_data)
            return

        # Regular hotkey matching
        config = self.config_manager.config
        hotkeys = config.get("hotkeys", {})
        
        for action, hotkey_data in hotkeys.items():
            if keys_match(key, hotkey_data):
                callback = self.action_callbacks.get(action)
                if callback:
                    try:
                        callback()
                    except Exception as e:
                        print(f"Error executing callback for {action}: {e}")
                break

    def start(self):
        """Start the background keyboard hook listener."""
        self.listener = keyboard.Listener(on_press=self._on_press)
        self.listener.daemon = True
        self.listener.start()

    def stop(self):
        """Stop the listener."""
        if self.listener:
            self.listener.stop()
