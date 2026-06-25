import sys
import os
from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QSlider, QCheckBox, 
    QVBoxLayout, QHBoxLayout, QGridLayout, QSystemTrayIcon, QMenu,
    QScrollArea, QSizePolicy, QAbstractButton
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QPoint, QObject, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QGuiApplication

def get_asset_path(filename):
    """Get the absolute path to the asset file, handling PyInstaller packaging."""
    if getattr(sys, 'frozen', False):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.argv[0])))
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, 'asset', filename)

class ToggleSwitch(QAbstractButton):
    """A clean, modern Windows 11 style Toggle Switch."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
    def sizeHint(self):
        return QSize(40, 20)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Track
        track_rect = self.rect()
        painter.setPen(Qt.PenStyle.NoPen)
        if self.isChecked():
            painter.setBrush(QBrush(QColor("#0088FF")))
        else:
            painter.setBrush(QBrush(QColor("#3F3F46")))
        painter.drawRoundedRect(track_rect, 10, 10)
        
        # Thumb
        thumb_radius = 8
        cy = track_rect.height() // 2
        if self.isChecked():
            cx = track_rect.width() - thumb_radius - 2
            painter.setBrush(QBrush(QColor("#FFFFFF")))
        else:
            cx = thumb_radius + 2
            painter.setBrush(QBrush(QColor("#E4E4E7")))
        painter.drawEllipse(QPoint(cx, cy), thumb_radius, thumb_radius)
        painter.end()

def create_dynamic_tray_icon(mic_muted, speaker_muted=False):
    """Load system tray icon from PNG assets based on mic state (speaker state ignored)."""
    filename = "mic_off.png" if mic_muted else "mic_on.png"
    icon_path = get_asset_path(filename)
    if os.path.exists(icon_path):
        return QIcon(icon_path)
    
    # Fallback to a programmatic dot if PNG is missing
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if mic_muted:
        painter.setBrush(QBrush(QColor("#EF4444")))
    else:
        painter.setBrush(QBrush(QColor("#10B981")))
    painter.drawEllipse(8, 8, 16, 16)
    painter.end()
    return QIcon(pixmap)


# Thread-safe Signal marshaller
class UIRunnerSignals(QObject):
    hotkey_recorded = pyqtSignal(str, dict)       # (action_name, key_data)
    show_osd_signal = pyqtSignal(str, str, int)   # (icon_type, message, progress_val)
    refresh_ui_signal = pyqtSignal()              # request UI labels update
    hotkey_triggered = pyqtSignal(str)            # action to execute on main thread


# --- Mini-drawing helpers for scaled OSD icons ---

def draw_mini_speaker(painter, rect, color, muted=False):
    """Draw a small vector speaker icon centered in rect (ideal for 16x16 or 18x18)."""
    cx = rect.center().x()
    cy = rect.center().y()
    
    painter.setPen(QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(QBrush(color))
    
    # Mini speaker cone path
    path = QPainterPath()
    path.moveTo(cx - 5, cy - 3)
    path.lineTo(cx - 2, cy - 3)
    path.lineTo(cx + 1, cy - 6)
    path.lineTo(cx + 1, cy + 6)
    path.lineTo(cx - 2, cy + 3)
    path.lineTo(cx - 5, cy + 3)
    path.closeSubpath()
    painter.fillPath(path, QBrush(color))
    
    if muted:
        painter.setPen(QPen(QColor("#EF4444"), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(cx - 6, cy - 6, cx + 6, cy + 6)
    else:
        painter.setPen(QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        # Draw a single wave arc
        painter.drawArc(cx - 2, cy - 4, 8, 8, -50 * 16, 100 * 16)

def draw_mini_microphone(painter, rect, color):
    """Draw a small vector microphone icon centered in rect (ideal for 16x16 or 18x18)."""
    cx = rect.center().x()
    cy = rect.center().y()
    
    painter.setPen(QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    
    # Capsule
    painter.drawRoundedRect(cx - 2, cy - 5, 4, 9, 2, 2)
    # U-bracket
    painter.drawArc(cx - 4, cy - 2, 8, 5, 180 * 16, 180 * 16)
    # Stem & Base
    painter.drawLine(cx, cy + 3, cx, cy + 6)
    painter.drawLine(cx - 3, cy + 6, cx + 3, cy + 6)


# --- On-Screen Display (OSD) Overlay ---

class OSDWindow(QWidget):
    def __init__(self):
        super().__init__()
        # Frameless, stays on top, tool window (doesn't show in taskbar), click-through
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool | 
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.icon_type = "sound"
        self.message = ""
        self.progress_val = -1
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.start_fade_out)
        
        self.anim = None
        self.resize(220, 32)
        
    def show_osd(self, icon_type, message, progress_val=-1):
        self.icon_type = icon_type
        # Clean up message for minimal look
        if "MUTED" in message:
            self.message = message.replace("MUTED", "Muted")
        elif "UNMUTED" in message:
            self.message = message.replace("UNMUTED", "Unmuted")
        else:
            self.message = message
            
        self.progress_val = progress_val
        
        # Position at bottom-center of the screen
        screen = QGuiApplication.primaryScreen()
        if screen:
            screen_geom = screen.geometry()
            x = screen_geom.x() + (screen_geom.width() - self.width()) // 2
            y = screen_geom.y() + screen_geom.height() - self.height() - 100
            self.move(x, y)
        
        if self.anim:
            self.anim.stop()
            
        self.setWindowOpacity(0.95)
        self.show()
        self.update()
        
        # Keep OSD visible for 1.5 seconds, then fade out
        self.timer.stop()
        self.timer.start(1500)
        
    def start_fade_out(self):
        self.timer.stop()
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(250)
        self.anim.setStartValue(0.95)
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self.hide)
        self.anim.start()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Render dark capsule background (15px border radius makes 32px height a pill shape)
        painter.setPen(QPen(QColor("#2D2D35"), 1))
        painter.setBrush(QBrush(QColor("#18181A")))
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 15, 15)
        
        # Icon rect
        icon_rect = QRect(12, 8, 16, 16)
        
        # Determine icon color
        icon_color = QColor("#0088FF")  # Default Blue
        if "mute" in self.icon_type:
            icon_color = QColor("#EF4444")  # Red for mute
        elif self.icon_type == "mic":
            icon_color = QColor("#10B981")  # Green for active mic
            
        if "mic" in self.icon_type:
            draw_mini_microphone(painter, icon_rect, icon_color)
        else:
            draw_mini_speaker(painter, icon_rect, icon_color, muted=(self.icon_type == "sound_mute"))
            
        # Draw Text / State info
        painter.setPen(QColor("#E4E4E7"))
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        
        if self.progress_val >= 0:
            # Draw Progress Bar (volume percentage) next to icon
            # x=36, y=14, w=120, h=4
            bar_rect = QRect(36, 14, 120, 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#2D2D35")))
            painter.drawRoundedRect(bar_rect, 2, 2)
            
            # Active fill
            active_width = int(120 * (self.progress_val / 100.0))
            if active_width > 0:
                active_rect = QRect(36, 14, active_width, 4)
                painter.setBrush(QBrush(QColor("#0088FF")))  # Blue active bar
                painter.drawRoundedRect(active_rect, 2, 2)
                
            # Draw percent value
            painter.setPen(QColor("#E4E4E7"))
            painter.drawText(166, 20, f"{self.progress_val}%")
        else:
            # Single-line status (Mute/Unmute toggle)
            painter.drawText(36, 20, self.message)


# --- Settings GUI Window ---

class SettingsWindow(QWidget):
    def __init__(self, config_manager, audio_controller, listener, signals):
        super().__init__()
        self.config_manager = config_manager
        self.audio_controller = audio_controller
        self.listener = listener
        self.signals = signals
        self.recording_action = None

        self.setWindowTitle("Zero Audio")
        self.setMinimumSize(420, 500)
        self.resize(440, 580)
        self.setWindowIcon(create_dynamic_tray_icon(False, False))

        self.setStyleSheet("""
            QWidget {
                background-color: #111113;
                color: #D4D4D8;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            QLabel#SectionLabel {
                color: #A1A1AA;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QFrame#Row {
                background-color: #18181B;
                border: 1px solid #27272A;
                border-radius: 7px;
            }
            QLabel#RowTitle {
                color: #E4E4E7;
                font-size: 13px;
            }
            QLabel#RowSub {
                color: #8B8B92;
                font-size: 11px;
            }
            QPushButton#KeyBtn {
                background-color: #27272A;
                color: #0088FF;
                border: 1px solid #3F3F46;
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: bold;
                min-width: 90px;
                max-height: 26px;
            }
            QPushButton#KeyBtn:hover {
                background-color: #3F3F46;
                border-color: #0088FF;
            }
            QPushButton#KeyBtn:checked {
                background-color: #0088FF;
                color: #FFFFFF;
                border-color: #0088FF;
            }
            QScrollArea {
                background-color: #111113;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: #111113;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #27272A;
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #0088FF;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #27272A;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #0088FF;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 2px solid #0088FF;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #33A3FF;
            }
            QPushButton#TrayBtn {
                background-color: #27272A;
                color: #A1A1AA;
                border: 1px solid #3F3F46;
                border-radius: 6px;
                padding: 7px 16px;
                font-size: 12px;
            }
            QPushButton#TrayBtn:hover {
                background-color: #3F3F46;
                color: #E4E4E7;
            }
        """)

        self.init_layout()
        self.refresh_ui()
        self.signals.hotkey_recorded.connect(self.handle_recorded_key)
        self.signals.refresh_ui_signal.connect(self.refresh_ui)

    # ------------------------------------------------------------------ #
    #  helpers                                                             #
    # ------------------------------------------------------------------ #

    def _section(self, text):
        lbl = QLabel(text.upper())
        lbl.setObjectName("SectionLabel")
        lbl.setContentsMargins(2, 0, 0, 0)
        return lbl

    def _row(self, title, subtitle=None, right_widget=None):
        frame = QFrame()
        frame.setObjectName("Row")
        row_h = QHBoxLayout(frame)
        row_h.setContentsMargins(14, 10, 14, 10)
        row_h.setSpacing(10)
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        t = QLabel(title)
        t.setObjectName("RowTitle")
        text_col.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("RowSub")
            text_col.addWidget(s)
        row_h.addLayout(text_col)
        row_h.addStretch()
        if right_widget:
            row_h.addWidget(right_widget)
        return frame

    def _toggle(self, config_key, default=True):
        cb = ToggleSwitch()
        cb.setChecked(self.config_manager.config.get(config_key, default))
        cb.toggled.connect(lambda v, k=config_key: self.config_manager.set(k, v))
        return cb

    # ------------------------------------------------------------------ #
    #  layout                                                              #
    # ------------------------------------------------------------------ #

    def init_layout(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header (static, doesn't scroll)
        hdr = QFrame()
        hdr.setStyleSheet("background:#18181B; border-bottom:1px solid #27272A;")
        hdr_l = QVBoxLayout(hdr)
        hdr_l.setContentsMargins(20, 14, 20, 14)
        hdr_l.setSpacing(2)
        title_lbl = QLabel("Zero Audio")
        title_lbl.setStyleSheet("font-size:16px; font-weight:bold; color:#FFFFFF;")
        sub_lbl = QLabel("Hotkeys  |  Volume  |  OSD  |  Startup")
        sub_lbl.setStyleSheet("font-size:11px; color:#A1A1AA;")
        hdr_l.addWidget(title_lbl)
        hdr_l.addWidget(sub_lbl)
        outer.addWidget(hdr)

        # Scroll Area for the settings body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Body container
        body = QWidget()
        body.setObjectName("BodyWidget")
        body.setStyleSheet("background-color: #111113;")
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(16, 14, 16, 14)
        body_l.setSpacing(10)

        # -- HOTKEYS --
        body_l.addWidget(self._section("Hotkeys"))
        self.hotkey_buttons = {}
        hotkey_defs = [
            ("mic_mute",   "Mic Mute / Unmute",    "Toggle default microphone"),
            ("sound_mute", "Speaker Mute / Unmute", "Toggle playback speakers"),
            ("volume_up",  "Volume Up",              "Raise system volume"),
            ("volume_down","Volume Down",             "Lower system volume"),
        ]
        for action, title, sub in hotkey_defs:
            btn = QPushButton("—")
            btn.setObjectName("KeyBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _c, a=action: self.start_key_recording(a))
            self.hotkey_buttons[action] = btn
            body_l.addWidget(self._row(title, sub, btn))

        # -- VOLUME STEP --
        body_l.addSpacing(4)
        body_l.addWidget(self._section("Volume"))

        self.vol_step_val_lbl = QLabel("5%")
        self.vol_step_val_lbl.setStyleSheet("color:#0088FF; font-weight:bold; min-width:28px;")
        self.slider_step = QSlider(Qt.Orientation.Horizontal)
        self.slider_step.setRange(1, 20)
        self.slider_step.setValue(5)
        self.slider_step.setFixedWidth(120)
        self.slider_step.valueChanged.connect(self.on_slider_changed)
        slider_wrap = QWidget()
        slider_wrap.setStyleSheet("background:transparent;")
        sw_l = QHBoxLayout(slider_wrap)
        sw_l.setContentsMargins(0, 0, 0, 0)
        sw_l.setSpacing(8)
        sw_l.addWidget(self.slider_step)
        sw_l.addWidget(self.vol_step_val_lbl)
        body_l.addWidget(self._row("Volume step per key press", "1% to 20%", slider_wrap))

        # -- OSD --
        body_l.addSpacing(4)
        body_l.addWidget(self._section("On-Screen Display (OSD)"))

        self.chk_osd_mic   = self._toggle("osd_on_mic_mute",   True)
        self.chk_osd_sound = self._toggle("osd_on_sound_mute", True)
        self.chk_osd_vol   = self._toggle("osd_on_volume",     True)

        body_l.addWidget(self._row("OSD on mic mute / unmute",    "", self.chk_osd_mic))
        body_l.addWidget(self._row("OSD on speaker mute / unmute","", self.chk_osd_sound))
        body_l.addWidget(self._row("OSD on volume change",        "", self.chk_osd_vol))

        # -- SYSTEM --
        body_l.addSpacing(4)
        body_l.addWidget(self._section("System"))

        self.chk_startup = self._toggle("run_on_startup", False)
        body_l.addWidget(self._row("Run on Windows Startup", "Registers to HKCU Run key", self.chk_startup))

        body_l.addStretch()
        
        scroll.setWidget(body)
        outer.addWidget(scroll)

        # Footer (static, doesn't scroll)
        ftr = QFrame()
        ftr.setStyleSheet("background:#18181B; border-top:1px solid #27272A;")
        ftr_l = QHBoxLayout(ftr)
        ftr_l.setContentsMargins(16, 10, 16, 10)
        tray_btn = QPushButton("Minimize to Tray")
        tray_btn.setObjectName("TrayBtn")
        tray_btn.clicked.connect(self.hide)
        ftr_l.addStretch()
        ftr_l.addWidget(tray_btn)
        outer.addWidget(ftr)

    # ------------------------------------------------------------------ #
    #  refresh / slots                                                     #
    # ------------------------------------------------------------------ #

    def refresh_ui(self):
        cfg = self.config_manager.config
        for action, btn in self.hotkey_buttons.items():
            btn.setChecked(False)
            btn.setEnabled(True)
            hk = cfg.get("hotkeys", {}).get(action, {})
            btn.setText(hk.get("display", "—"))

        step_pct = int(cfg.get("volume_step", 0.05) * 100)
        self.slider_step.blockSignals(True)
        self.slider_step.setValue(step_pct)
        self.slider_step.blockSignals(False)
        self.vol_step_val_lbl.setText(f"{step_pct}%")

        self.chk_osd_mic.blockSignals(True)
        self.chk_osd_sound.blockSignals(True)
        self.chk_osd_vol.blockSignals(True)
        self.chk_startup.blockSignals(True)

        self.chk_osd_mic.setChecked(cfg.get("osd_on_mic_mute",    True))
        self.chk_osd_sound.setChecked(cfg.get("osd_on_sound_mute", True))
        self.chk_osd_vol.setChecked(cfg.get("osd_on_volume",       True))
        self.chk_startup.setChecked(cfg.get("run_on_startup",       False))

        self.chk_osd_mic.blockSignals(False)
        self.chk_osd_sound.blockSignals(False)
        self.chk_osd_vol.blockSignals(False)
        self.chk_startup.blockSignals(False)

    def on_slider_changed(self, val):
        self.vol_step_val_lbl.setText(f"{val}%")
        self.config_manager.set_volume_step(val / 100.0)

    def start_key_recording(self, action):
        if self.recording_action is not None:
            old = self.hotkey_buttons[self.recording_action]
            old.setChecked(False)
            old.setText(self.config_manager.config["hotkeys"][self.recording_action].get("display", "—"))
        self.recording_action = action
        btn = self.hotkey_buttons[action]
        btn.setChecked(True)
        btn.setText("Press any key...")
        for a, b in self.hotkey_buttons.items():
            if a != action:
                b.setEnabled(False)
        self.listener.start_recording(
            lambda kd: self.signals.hotkey_recorded.emit(action, kd)
        )

    def handle_recorded_key(self, action, key_data):
        if self.recording_action == action:
            self.config_manager.update_hotkey(action, key_data)
            self.recording_action = None
            self.refresh_ui()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
