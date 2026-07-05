import sys
import os
import json
import win32con
import win32gui
from PIL import Image, ImageDraw
from pystray import Icon as TrayIcon, Menu as TrayMenu, MenuItem as TrayOption
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QMetaObject, Q_ARG
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush

# --- Configuration Management ---
CONFIG_FILE = "timer_config.json"

DEFAULT_SETTINGS = {
    "timer_minutes": 15,
    "position": "top_left",
    "monitor_indexes": [0],
    "opacity": 0.8,
    "speed_multiplier": 1.0,
    "active_theme": "Cyberpunk",
    "themes": {
        "Cyberpunk": {
            "active": "#00FF66",
            "overtime": "#FF3333",
            "paused": "#FFA500"
        },
        "Deep Purple": {
            "active": "#D8BFD8",
            "overtime": "#FF00FF",
            "paused": "#8A2BE2"
        },
        "Sunset Gold": {
            "active": "Gold",
            "overtime": "Tomato",
            "paused": "DarkOrange"
        }
    }
}

def load_settings():
    """Loads settings from a JSON file, falling back to defaults if missing or corrupt."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                if "themes" in loaded:
                    themes = {**DEFAULT_SETTINGS["themes"], **loaded["themes"]}
                    loaded["themes"] = themes
                if "monitor_index" in loaded and "monitor_indexes" not in loaded:
                    loaded["monitor_indexes"] = [loaded["monitor_index"]]
                return {**DEFAULT_SETTINGS, **loaded}
        except (json.JSONDecodeError, IOError):
            pass
    save_settings(DEFAULT_SETTINGS)
    return DEFAULT_SETTINGS.copy()

def save_settings(settings_dict):
    """Saves the current configuration settings to the JSON file."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(settings_dict, f, indent=4)
    except IOError as e:
        print(f"Error saving settings: {e}")


class TraySignalBridge(QObject):
    """Bridges system tray actions to the PyQt GUI thread safely using queued invocations."""
    show_hide_triggered = pyqtSignal()
    toggle_pause_triggered = pyqtSignal()
    exit_triggered = pyqtSignal()
    change_position = pyqtSignal(str)
    toggle_monitor = pyqtSignal(int)
    change_opacity = pyqtSignal(float)
    change_theme = pyqtSignal(str)
    change_duration = pyqtSignal(int)

    def safe_emit(self, signal_name, *args):
        """Dispatches an invocation payload to marshal safely back onto the main Qt event loop thread."""
        QMetaObject.invokeMethod(
            self, 
            signal_name, 
            Qt.ConnectionType.QueuedConnection, 
            *[Q_ARG(type(arg), arg) for arg in args]
        )


class CountdownOverlay(QWidget):
    def __init__(self, settings, monitor_index, shared_state):
        super().__init__()
        self.settings = settings
        self.monitor_index = monitor_index
        self.state = shared_state
        
        self.position_setting = settings["position"]
        self.opacity_setting = settings["opacity"]
        
        self.themes = settings["themes"]
        self.current_theme_name = settings["active_theme"]
        if self.current_theme_name not in self.themes:
            self.current_theme_name = list(self.themes.keys())[0]

        self.init_ui()
        self.apply_window_properties()

    def init_ui(self):
        """Initializes the frameless, transparent UI."""
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowOpacity(self.opacity_setting)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        self.label = QLabel(self.format_time(self.state["time_left"]), self)
        
        self.update_label_style()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        self.setLayout(layout)
        
        self.adjust_screen_position()

    def update_label_style(self):
        """Updates CSS colors dynamically mapping back to active runtime states."""
        theme = self.themes[self.current_theme_name]
        
        if self.state["is_paused"]:
            text_color = theme["paused"]
        elif self.state["is_counting_up"]:
            text_color = theme["overtime"]
        else:
            text_color = theme["active"]

        self.label.setStyleSheet(f"""
            QLabel {{
                background-color: rgb(30, 30, 30);
                color: {text_color};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 18px;
                font-weight: bold;
                padding: 8px 12px;
                border-radius: 6px;
                border: none;
            }}
        """)

    def paintEvent(self, event):
        """Custom paint engine that draws the dynamic, reactive border progress track."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(2, 2, -2, -2)
        radius = 6
        
        theme = self.themes[self.current_theme_name]
        
        if self.state["is_paused"]:
            border_color = QColor(theme["paused"])
        elif self.state["is_counting_up"]:
            border_color = QColor(theme["overtime"])
            border_color.setAlpha(self.state["pulse_alpha"])
        else:
            border_color = QColor(theme["active"])

        if not self.state["is_counting_up"] and self.state["initial_duration"] > 0:
            progress_ratio = self.state["time_left"] / self.state["initial_duration"]
            
            base_pen = QPen(QColor(255, 255, 255, 30), 2)
            painter.setPen(base_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)

            progress_pen = QPen(border_color, 2)
            painter.setPen(progress_pen)
            
            if progress_ratio >= 0.99:
                painter.drawRoundedRect(rect, radius, radius)
            elif progress_ratio > 0:
                painter.save()
                painter.drawRoundedRect(rect, radius, radius)
                painter.restore()
        else:
            pen = QPen(border_color, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)

    def refresh_display(self):
        """Forces string updates and repaints driven from core state tracking thread updates."""
        if not self.state["is_counting_up"]:
            self.label.setText(self.format_time(self.state["time_left"]))
        else:
            self.label.setText(f"+{self.format_time(self.state['count_up_seconds'])}")
        self.update()

    def adjust_screen_position(self, position=None):
        """Positions the widget safely using its explicitly designated display screen boundary contexts."""
        if position:
            self.position_setting = position
            
        self.adjustSize()
        if self.layout() and self.layout().sizeHint().isValid():
            self.setFixedSize(self.layout().sizeHint().width() + 12, self.layout().sizeHint().height() + 12)
        
        screens = QApplication.screens()
        if self.monitor_index < 0 or self.monitor_index >= len(screens):
            return
            
        target_screen = screens[self.monitor_index]
        screen_geo = target_screen.availableGeometry()
        widget_geo = self.geometry()
        
        margin = 20
        
        if self.position_setting == "top_left":
            self.move(screen_geo.left() + margin, screen_geo.top() + margin)
        elif self.position_setting == "top_center":
            x = screen_geo.left() + (screen_geo.width() - widget_geo.width()) // 2
            self.move(x, screen_geo.top() + margin)
        elif self.position_setting == "top_right":
            self.move(screen_geo.left() + screen_geo.width() - widget_geo.width() - margin, screen_geo.top() + margin)
        elif self.position_setting == "bottom_left":
            self.move(screen_geo.left() + margin, screen_geo.top() + screen_geo.height() - widget_geo.height() - margin)
        elif self.position_setting == "bottom_center":
            x = screen_geo.left() + (screen_geo.width() - widget_geo.width()) // 2
            self.move(x, screen_geo.top() + screen_geo.height() - widget_geo.height() - margin)
        elif self.position_setting == "bottom_right":
            self.move(screen_geo.left() + screen_geo.width() - widget_geo.width() - margin, screen_geo.top() + screen_geo.height() - widget_geo.height() - margin)

    def update_opacity(self, opacity_value: float):
        self.opacity_setting = opacity_value
        self.setWindowOpacity(opacity_value)

    def update_theme(self, theme_name: str):
        if theme_name in self.themes:
            self.current_theme_name = theme_name
            self.update_label_style()
            self.update()

    def apply_window_properties(self):
        self.show()
        self.hwnd = self.winId().__int__()
        self.set_click_through(not self.state["is_counting_up"])

    def set_click_through(self, click_through: bool):
        extended_style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_EXSTYLE)
        if click_through:
            extended_style |= win32con.WS_EX_TRANSPARENT
        else:
            extended_style &= ~win32con.WS_EX_TRANSPARENT
            
        self.update_label_style()
        win32gui.SetWindowLong(self.hwnd, win32con.GWL_EXSTYLE, extended_style)
        self.update()

    def mousePressEvent(self, event):
        """Broadcasts manual reset requests upstream if an interactive pane layout surface is clicked."""
        if self.state["is_counting_up"] and event.button() == Qt.MouseButton.LeftButton:
            window_manager.reset_global_timer()

    @staticmethod
    def format_time(seconds):
        mins, secs = divmod(seconds, 60)
        return f"{mins:02d}:{secs:02d}"


class OverlayWindowManager:
    """Manages the centralized global timing loop state and handles multi-window instantiation mappings."""
    def __init__(self, settings, bridge):
        self.settings = settings
        self.bridge = bridge
        self.windows = {}  # Map: monitor_index -> CountdownOverlay window instance
        
        self.state = {
            "initial_duration": settings["timer_minutes"] * 60,
            "time_left": settings["timer_minutes"] * 60,
            "is_paused": False,
            "is_counting_up": False,
            "count_up_seconds": 0,
            "pulse_alpha": 255,
            "pulse_direction": -15
        }
        
        self.speed_multiplier = max(0.1, settings.get("speed_multiplier", 1.0))
        self.active_monitors = set(settings.get("monitor_indexes", [0]))
        
        self.setup_timer()
        self.sync_windows()

    def setup_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.handle_global_tick)
        interval = int(1000 / self.speed_multiplier)
        self.timer.start(interval)

    def sync_windows(self):
        """Instantiates or purges separate hardware surface overlays depending on selected options lists."""
        for idx in list(self.windows.keys()):
            if idx not in self.active_monitors:
                self.windows[idx].close()
                del self.windows[idx]
        
        for idx in self.active_monitors:
            if idx not in self.windows:
                self.windows[idx] = CountdownOverlay(self.settings, idx, self.state)
                
        self.refresh_all_windows()

    def handle_global_tick(self):
        """Updates engine logic matrices down onto all listening downstream interfaces safely."""
        if not self.state["is_counting_up"]:
            if self.state["time_left"] > 0:
                self.state["time_left"] -= 1
                
                if self.state["time_left"] == 0:
                    self.state["is_counting_up"] = True
                    self.state["count_up_seconds"] = 0
                    for win in self.windows.values():
                        win.set_click_through(False)
        else:
            self.state["count_up_seconds"] += 1
            self.state["pulse_alpha"] += self.state["pulse_direction"]
            if self.state["pulse_alpha"] <= 100 or self.state["pulse_alpha"] >= 255:
                self.state["pulse_direction"] *= -1

        self.refresh_all_windows()

    def refresh_all_windows(self):
        for win in self.windows.values():
            win.refresh_display()

    def toggle_pause_global(self):
        if self.state["is_paused"]:
            self.state["is_paused"] = False
            interval = int(1000 / self.speed_multiplier)
            self.timer.start(interval)
        else:
            self.state["is_paused"] = True
            self.timer.stop()
            
        for win in self.windows.values():
            win.update_label_style()
            win.update()

    def reset_global_timer(self):
        self.state["time_left"] = self.state["initial_duration"]
        self.state["count_up_seconds"] = 0
        self.state["pulse_alpha"] = 255
        self.state["pulse_direction"] = -15
        self.state["is_paused"] = False
        self.state["is_counting_up"] = False
        
        for win in self.windows.values():
            win.set_click_through(True)
            win.adjust_screen_position()
            
        interval = int(1000 / self.speed_multiplier)
        self.timer.start(interval)
        self.refresh_all_windows()

    def update_global_position(self, new_pos):
        self.settings["position"] = new_pos
        save_settings(self.settings)
        for win in self.windows.values():
            win.adjust_screen_position(new_pos)

    def toggle_monitor_selection(self, idx):
        """Adds or removes a monitor index depending on its previous state."""
        if idx in self.active_monitors:
            if len(self.active_monitors) > 1:
                self.active_monitors.remove(idx)
        else:
            self.active_monitors.add(idx)
            
        self.settings["monitor_indexes"] = list(self.active_monitors)
        save_settings(self.settings)
        self.sync_windows()

    def update_global_opacity(self, new_opacity):
        self.settings["opacity"] = new_opacity
        save_settings(self.settings)
        for win in self.windows.values():
            win.update_opacity(new_opacity)

    def update_global_theme(self, new_theme):
        self.settings["active_theme"] = new_theme
        save_settings(self.settings)
        for win in self.windows.values():
            win.update_theme(new_theme)

    def update_global_duration(self, minutes):
        self.settings["timer_minutes"] = minutes
        save_settings(self.settings)
        self.state["initial_duration"] = minutes * 60
        self.reset_global_timer()

    def toggle_global_visibility(self):
        any_visible = any(win.isVisible() for win in self.windows.values())
        for win in self.windows.values():
            win.hide() if any_visible else win.show()


# --- System Tray Menu Builder ---

def create_tray_image():
    """Generates a default green circle icon for the system tray canvas."""
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse([8, 8, 56, 56], fill=(0, 255, 102, 255))
    return image


def build_menu(bridge: TraySignalBridge, current_pos: str, active_monitors: set, current_opacity: float, is_paused: bool, available_themes: dict, active_theme: str, current_duration: int):
    """Generates an expanded Menu structure supporting multi-checkbox selection paths."""
    def is_pos(pos_str):
        return lambda item: current_pos == pos_str

    def is_monitor_checked(idx):
        return lambda item: idx in active_monitors

    def is_opacity(val):
        return lambda item: abs(current_opacity - val) < 0.01

    def is_theme(theme_name):
        return lambda item: active_theme == theme_name

    def is_duration(minutes):
        return lambda item: current_duration == minutes

    def make_monitor_callback(idx):
        return lambda icon, item: bridge.safe_emit('toggle_monitor', idx)

    def make_theme_callback(theme_name):
        return lambda icon, item: bridge.safe_emit('change_theme', theme_name)

    def make_duration_callback(minutes):
        return lambda icon, item: bridge.safe_emit('change_duration', minutes)

    position_menu = TrayMenu(
        TrayOption('Top Left', lambda: bridge.safe_emit('change_position', 'top_left'), checked=is_pos('top_left'), radio=True),
        TrayOption('Top Center', lambda: bridge.safe_emit('change_position', 'top_center'), checked=is_pos('top_center'), radio=True),
        TrayOption('Top Right', lambda: bridge.safe_emit('change_position', 'top_right'), checked=is_pos('top_right'), radio=True),
        TrayMenu.SEPARATOR,
        TrayOption('Bottom Left', lambda: bridge.safe_emit('change_position', 'bottom_left'), checked=is_pos('bottom_left'), radio=True),
        TrayOption('Bottom Center', lambda: bridge.safe_emit('change_position', 'bottom_center'), checked=is_pos('bottom_center'), radio=True),
        TrayOption('Bottom Right', lambda: bridge.safe_emit('change_position', 'bottom_right'), checked=is_pos('bottom_right'), radio=True),
    )

    screen_count = len(QApplication.screens())
    monitor_options = []
    for i in range(screen_count):
        label = f"Monitor {i + 1} (Primary)" if i == 0 else f"Monitor {i + 1}"
        monitor_options.append(
            TrayOption(label, make_monitor_callback(i), checked=is_monitor_checked(i))
        )
    monitor_menu = TrayMenu(*monitor_options)

    opacity_menu = TrayMenu(
        TrayOption('100% (Solid)', lambda: bridge.safe_emit('change_opacity', 1.0), checked=is_opacity(1.0), radio=True),
        TrayOption('90%', lambda: bridge.safe_emit('change_opacity', 0.9), checked=is_opacity(0.9), radio=True),
        TrayOption('80%', lambda: bridge.safe_emit('change_opacity', 0.8), checked=is_opacity(0.8), radio=True),
        TrayOption('70%', lambda: bridge.safe_emit('change_opacity', 0.7), checked=is_opacity(0.7), radio=True),
        TrayOption('60%', lambda: bridge.safe_emit('change_opacity', 0.6), checked=is_opacity(0.6), radio=True),
        TrayOption('50%', lambda: bridge.safe_emit('change_opacity', 0.5), checked=is_opacity(0.5), radio=True),
        TrayOption('40%', lambda: bridge.safe_emit('change_opacity', 0.4), checked=is_opacity(0.4), radio=True),
        TrayOption('30%', lambda: bridge.safe_emit('change_opacity', 0.3), checked=is_opacity(0.3), radio=True),
        TrayOption('20%', lambda: bridge.safe_emit('change_opacity', 0.2), checked=is_opacity(0.2), radio=True),
        TrayOption('10% (Ghost)', lambda: bridge.safe_emit('change_opacity', 0.1), checked=is_opacity(0.1), radio=True),
    )

    theme_options = []
    for name in available_themes.keys():
        theme_options.append(
            TrayOption(name, make_theme_callback(name), checked=is_theme(name), radio=True)
        )
    theme_menu = TrayMenu(*theme_options)

    duration_presets = [
        ('5 Minutes', 5),
        ('10 Minutes', 10),
        ('15 Minutes', 15),
        ('25 Minutes (Pomodoro)', 25),
        ('45 Minutes', 45),
        ('60 Minutes', 60),
    ]
    duration_options = []
    for label, mins in duration_presets:
        duration_options.append(
            TrayOption(label, make_duration_callback(mins), checked=is_duration(mins), radio=True)
        )
    duration_menu = TrayMenu(*duration_options)

    pause_resume_text = "Resume Timer" if is_paused else "Pause Timer"

    return TrayMenu(
        TrayOption('Show / Hide', lambda: bridge.safe_emit('show_hide_triggered')),
        TrayOption(pause_resume_text, lambda: bridge.safe_emit('toggle_pause_triggered')),
        TrayMenu.SEPARATOR,
        TrayOption('Timer Duration', duration_menu),
        TrayOption('Target Monitors', monitor_menu),
        TrayOption('Position', position_menu),
        TrayOption('Transparency', opacity_menu),
        TrayOption('Color Theme', theme_menu),
        TrayMenu.SEPARATOR,
        TrayOption('Exit', lambda: bridge.safe_emit('exit_triggered'))
    )


# --- Main Application Loop ---

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    current_settings = load_settings()
    signal_bridge = TraySignalBridge()
    
    window_manager = OverlayWindowManager(settings=current_settings, bridge=signal_bridge)
    
    initial_menu = build_menu(
        signal_bridge, 
        current_settings["position"], 
        window_manager.active_monitors,
        current_settings["opacity"], 
        window_manager.state["is_paused"],
        current_settings["themes"],
        current_settings["active_theme"],
        current_settings["timer_minutes"]
    )
    
    tray_icon = TrayIcon("OverlayTimer", create_tray_image(), "Timer Overlay", initial_menu)
    tray_icon.run_detached()
    
    def rebuild_tray_context():
        tray_icon.menu = build_menu(
            signal_bridge, 
            window_manager.settings["position"], 
            window_manager.active_monitors, 
            window_manager.settings["opacity"], 
            window_manager.state["is_paused"], 
            window_manager.settings["themes"], 
            window_manager.settings["active_theme"], 
            window_manager.settings["timer_minutes"]
        )

    def toggle_visibility():
        window_manager.toggle_global_visibility()

    def toggle_pause_state():
        window_manager.toggle_pause_global()
        rebuild_tray_context()

    def update_tray_and_position(new_pos):
        window_manager.update_global_position(new_pos)
        rebuild_tray_context()

    def update_tray_and_monitor(monitor_idx):
        window_manager.toggle_monitor_selection(monitor_idx)
        rebuild_tray_context()

    def update_tray_and_opacity(new_opacity):
        window_manager.update_global_opacity(new_opacity)
        rebuild_tray_context()

    def update_tray_and_theme(new_theme):
        window_manager.update_global_theme(new_theme)
        rebuild_tray_context()

    def update_tray_and_duration(new_mins):
        window_manager.update_global_duration(new_mins)
        rebuild_tray_context()

    def quit_application():
        tray_icon.stop()
        QApplication.quit()

    signal_bridge.show_hide_triggered.connect(toggle_visibility)
    signal_bridge.toggle_pause_triggered.connect(toggle_pause_state)
    signal_bridge.change_position.connect(update_tray_and_position)
    signal_bridge.toggle_monitor.connect(update_tray_and_monitor)
    signal_bridge.change_opacity.connect(update_tray_and_opacity)
    signal_bridge.change_theme.connect(update_tray_and_theme)
    signal_bridge.change_duration.connect(update_tray_and_duration)
    signal_bridge.exit_triggered.connect(quit_application)
    
    sys.exit(app.exec())