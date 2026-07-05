# Windows Frameless Overlay Timer

An elegant, production-grade, frameless countdown timer overlay for Windows built using **PyQt6**, **pystray**, and **pywin32**. Designed specifically for stream layouts, presentations, monitoring setups, or focus work (Pomodoro), it supports seamless multi-monitor duplication, asynchronous thread-safe system tray operations, and click-through window modes.

![alt text](images/image.png)
![alt text](images/image-1.png)


## ✨ Features

* **📺 Multi-Monitor Architecture:** Mirror the timer overlay across selected displays concurrently with active dynamic repositioning.
* **🔒 Click-Through Interactivity:** The window runs fully transparently to input (clicks pass directly to background apps) during standard counts, automatically locking interactions to accept click resets when the duration is exceeded.
* **🧵 Asynchronous Thread-Safety:** Fully decoupled `pystray` system tray loop and Qt GUI loop using queued `QMetaObject` invocations to eliminate race conditions and thread crosstalk crashes.
* **🎨 Dynamic Themes & Custom Borders:** Built-in presets (Cyberpunk, Deep Purple, Sunset Gold) complete with glowing, real-time border progress tracks and adaptive status coloring.
* **⚙️ Persistent Configurations:** Settings such as position presets, transparency overrides, selected active screens, and custom intervals automatically serialize to a local `timer_config.json` file.

---

## 🚀 Installation & Setup

Ensure you have Python 3.11+ installed. Clone this repository and follow the initialization workflow below.

### 1. Install Dependencies

Install the necessary platform-native bindings and package runtimes:

```bash
pip install PyQt6 pystray Pillow pywin32
```

### 2. Run the Application

Launch the main overlay loop:

```bash
python overlay_timer.py
```

---

## 🕹️ Usage

### System Tray Controls

Right-click the status tray icon (green circle target indicator) to configure global states in real time:

* **Show / Hide:** Instantly toggle display visibilities globally across all active monitor canvases.
* **Pause / Resume Timer:** Halts or continues the ticking execution cycle safely.
* **Timer Duration:** Jump directly into standard presets (`5 min`, `15 min`, `25 min Pomodoro`, `60 min`). Changing durations automatically executes an internal hot-reset.
* **Target Monitors:** Use native checkbox items to dynamically add or drop rendered instances across multiple hardware screens.
* **Position:** Teleport the active overlay geometry into layout anchors (`Top Left`, `Top Center`, `Bottom Right`, etc.) adjusting to target taskbar limits automatically.
* **Transparency:** Apply continuous background alpha ranges from `100% Solid` down to `10% Ghost` styling parameters.
* **Color Theme:** Instantly swap operational CSS sheets under design presets.

### Overtime Behavior

* When the counter reaches `00:00`, it seamlessly turns into a count-up tracking timer (`+MM:SS`).
* The border line switches to a breathing, alphanumeric warning visual pulse (using adaptive alpha-shifting).
* The underlying windows temporarily disable their OS click-through bindings. Simply **Left-Click directly on any visible timer text overlay block** to immediately drop out of overtime, reset the timeline duration, and revert the workspace back to standard mouse-transparent operation.

---

## 🛠️ Configuration Architecture (`timer_config.json`)

The application generates a state configuration file on its first run loop. You can modify properties inside the tray app or manually change parameters directly inside `timer_config.json`:

```json
{
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
        }
    }
}
```

* `monitor_indexes`: Array list mapping to active target systems (e.g., `[0, 1]` duplicates the view across primary and secondary monitors).
* `speed_multiplier`: Useful for testing or rapid workflow monitoring (e.g., set to `60.0` to process 1 minute per actual second).

---

## 🛡️ License

Distributed under the MIT License. See `LICENSE` for more details.
