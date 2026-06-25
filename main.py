import sys
import os

# Redirect standard streams to devnull in GUI mode to prevent crashes from prints
if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, 'w')
    except Exception:
        pass
if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, 'w')
    except Exception:
        pass

import socket
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtCore import QThread, pyqtSignal, QTimer

# Import custom modules
from config import ConfigManager
from audio import AudioController
from hotkey import GlobalHotkeyListener
from ui import SettingsWindow, OSDWindow, UIRunnerSignals, create_dynamic_tray_icon

# Single Instance TCP Port
PORT = 49281

class SingleInstanceServer(QThread):
    """Listens on a local port. If a connection is made, raises the settings window."""
    show_window_signal = pyqtSignal()

    def __init__(self, port):
        super().__init__()
        self.port = port
        self.server = None
        self.running = True

    def run(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server.bind(('127.0.0.1', self.port))
            self.server.listen(1)
        except Exception as e:
            print(f"[InstanceServer] Bind failed: {e}")
            return

        while self.running:
            try:
                self.server.settimeout(1.0)
                conn, addr = self.server.accept()
                data = conn.recv(1024).decode('utf-8')
                if data == "SHOW":
                    self.show_window_signal.emit()
                conn.close()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[InstanceServer] Socket exception: {e}")
                break

    def stop(self):
        self.running = False
        if self.server:
            try:
                # Force close the socket to wake up accept loop
                self.server.close()
            except Exception:
                pass


def check_running_instance(port):
    """Try to connect to the port. If successful, notify running instance to show and return True."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(('127.0.0.1', port))
        s.sendall(b"SHOW")
        s.close()
        return True
    except (ConnectionRefusedError, socket.timeout):
        return False
    except Exception as e:
        print(f"Error checking single instance: {e}")
        return False


class WinAudioControllerApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)  # Keep running when dashboard is closed
        
        # 1. Initialize settings & audio controller
        self.config_manager = ConfigManager()
        self.audio_controller = AudioController()
        
        # 2. Thread-safe communication signals
        self.signals = UIRunnerSignals()
        
        # 3. Create OSD overlay window
        self.osd_window = OSDWindow()
        self.signals.show_osd_signal.connect(self.on_show_osd_signal)
        
        # 4. Global keyboard hotkey listener
        self.action_callbacks = {
            "mic_mute": lambda: self.signals.hotkey_triggered.emit("mic_mute"),
            "sound_mute": lambda: self.signals.hotkey_triggered.emit("sound_mute"),
            "volume_up": lambda: self.signals.hotkey_triggered.emit("volume_up"),
            "volume_down": lambda: self.signals.hotkey_triggered.emit("volume_down")
        }
        self.hotkey_listener = GlobalHotkeyListener(self.config_manager, self.action_callbacks)
        self.hotkey_listener.start()
        
        # Connect the hotkey trigger signal to the main thread handler
        self.signals.hotkey_triggered.connect(self.handle_hotkey_action)
        
        # 5. Create Settings Window (hidden by default)
        self.settings_window = SettingsWindow(
            self.config_manager, 
            self.audio_controller, 
            self.hotkey_listener, 
            self.signals
        )
        self.signals.refresh_ui_signal.connect(self.settings_window.refresh_ui)
        
        # 6. Initialize System Tray Icon
        self.tray_icon = QSystemTrayIcon(self.settings_window)
        self.setup_tray()
        
        # 7. Single Instance Server
        self.instance_server = SingleInstanceServer(PORT)
        self.instance_server.show_window_signal.connect(self.show_settings_window)
        self.instance_server.start()
        
        # 8. Dynamic state sync timer (polls Windows audio system to handle changes made outside the app)
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.sync_audio_states)
        self.sync_timer.start(2000)  # Check every 2 seconds
        
        # Initial tray state update
        self.sync_audio_states()
        
        # Show a tray notification on first launch (if not configured to run on startup)
        if not self.config_manager.config.get("run_on_startup", False):
            # First launch hint
            QTimer.singleShot(1000, lambda: self.tray_icon.showMessage(
                "Zero Audio",
                "App is running in the background. Press Numpad / to toggle mic, Numpad * for sound.",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            ))

    def setup_tray(self):
        """Build the tray icon menu and double-click actions."""
        self.tray_icon.activated.connect(self.on_tray_activated)
        
        # Create context menu
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #1E1E24;
                color: #E4E4E7;
                border: 1px solid #2D2D35;
            }
            QMenu::item {
                padding: 6px 20px;
            }
            QMenu::item:selected {
                background-color: #0088FF;
                color: #FFFFFF;
            }
        """)
        
        action_settings = menu.addAction("Settings...")
        action_settings.triggered.connect(self.show_settings_window)
        
        menu.addSeparator()
        
        self.action_tray_mic_mute = menu.addAction("Mute Microphone")
        self.action_tray_mic_mute.triggered.connect(self.on_mic_mute)
        
        self.action_tray_sound_mute = menu.addAction("Mute Sound")
        self.action_tray_sound_mute.triggered.connect(self.on_sound_mute)
        
        menu.addSeparator()
        
        action_exit = menu.addAction("Exit")
        action_exit.triggered.connect(self.exit_app)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        """Handle clicking tray icon."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_settings_window()

    def show_settings_window(self):
        """Show the dashboard window, bring to foreground."""
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def sync_audio_states(self):
        """Poll speaker and mic states, update system tray and context menu labels."""
        _, mic_muted = self.audio_controller.get_mic_state()
        _, speaker_muted = self.audio_controller.get_speaker_state()
        
        # 1. Update dynamic icon
        self.tray_icon.setIcon(create_dynamic_tray_icon(mic_muted, speaker_muted))
        
        # 2. Update context menu action text
        self.action_tray_mic_mute.setText("Unmute Microphone" if mic_muted else "Mute Microphone")
        self.action_tray_sound_mute.setText("Unmute Sound" if speaker_muted else "Mute Sound")
        
        # 3. Update tooltip
        tooltip = (
            f"Zero Audio\n"
            f"Speakers: {'MUTED' if speaker_muted else 'Active'}\n"
            f"Microphone: {'MUTED' if mic_muted else 'Active'}"
        )
        self.tray_icon.setToolTip(tooltip)

    # --- Hotkey Callbacks (run on GUI thread via signal marshalling) ---
    
    def handle_hotkey_action(self, action):
        """Thread-safe slot to handle hotkeys triggered on background thread."""
        if action == "mic_mute":
            self.on_mic_mute()
        elif action == "sound_mute":
            self.on_sound_mute()
        elif action == "volume_up":
            self.on_volume_up()
        elif action == "volume_down":
            self.on_volume_down()

    def on_mic_mute(self):
        cfg = self.config_manager.config
        muted, msg = self.audio_controller.toggle_mic_mute()
        if muted is not None:
            if cfg.get("osd_on_mic_mute", True):
                self.signals.show_osd_signal.emit("mic_mute" if muted else "mic", msg, -1)
            self.sync_audio_states()
            self.signals.refresh_ui_signal.emit()

    def on_sound_mute(self):
        cfg = self.config_manager.config
        muted, msg = self.audio_controller.toggle_speaker_mute()
        if muted is not None:
            if cfg.get("osd_on_sound_mute", True):
                self.signals.show_osd_signal.emit("sound_mute" if muted else "sound", msg, -1)
            self.sync_audio_states()
            self.signals.refresh_ui_signal.emit()

    def on_volume_up(self):
        cfg = self.config_manager.config
        step = cfg.get("volume_step", 0.05)
        pct, msg = self.audio_controller.adjust_speaker_volume(step)
        if pct is not None:
            if cfg.get("osd_on_volume", True):
                self.signals.show_osd_signal.emit("sound", msg, pct)
            self.sync_audio_states()
            self.signals.refresh_ui_signal.emit()

    def on_volume_down(self):
        cfg = self.config_manager.config
        step = cfg.get("volume_step", 0.05)
        pct, msg = self.audio_controller.adjust_speaker_volume(-step)
        if pct is not None:
            if cfg.get("osd_on_volume", True):
                self.signals.show_osd_signal.emit("sound", msg, pct)
            self.sync_audio_states()
            self.signals.refresh_ui_signal.emit()

    def on_show_osd_signal(self, icon_type, message, progress_val):
        """Thread-safe slot: OSD gating is handled per-action above."""
        self.osd_window.show_osd(icon_type, message, progress_val)

    def exit_app(self):
        """Cleanup resources and exit."""
        self.sync_timer.stop()
        self.instance_server.stop()
        self.hotkey_listener.stop()
        self.tray_icon.hide()
        self.app.quit()
        sys.exit(0)

    def run(self):
        return self.app.exec()


if __name__ == "__main__":
    try:
        # Ensure only a single instance of the utility runs at a time
        if check_running_instance(PORT):
            print("Zero Audio is already running. Notified running instance to show itself.")
            sys.exit(0)
            
        # Start app
        controller_app = WinAudioControllerApp()
        sys.exit(controller_app.run())
    except Exception as e:
        import traceback
        try:
            with open("crash_log.txt", "w", encoding="utf-8") as f:
                f.write(f"Exception: {e}\n")
                traceback.print_exc(file=f)
        except Exception:
            pass
        sys.exit(1)
