import json
import os
import time
import subprocess
import threading
import pyautogui
import keyboard

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
KEY_ALIASES = {
    "playpause": "play/pause media",
    "play_pause": "play/pause media",
    "nexttrack": "next track",
    "next_track": "next track",
    "prevtrack": "previous track",
    "previoustrack": "previous track",
    "prev_track": "previous track",
    "volup": "volume up",
    "voldown": "volume down",
    "volmute": "volume mute",
}

class ActionMapper:
    def __init__(self):
        self.mappings = {}
        self.last_action_time = {}
        self.cooldown = 0.35 # per-gesture cooldown (seconds)
        self.recent_targets = []
        self._lock = threading.Lock()
        self.load_config()

    @staticmethod
    def _default_mappings():
        return [
            {
                "id": "default-pinch",
                "gesture": "Pinch",
                "action_type": "shortcut",
                "keys": ["win", "d"],
                "description": "Show Desktop",
            },
            {
                "id": "default-swipe-left",
                "gesture": "Swipe_Left",
                "action_type": "shortcut",
                "keys": ["prevtrack"],
                "description": "Previous Track",
            },
            {
                "id": "default-swipe-right",
                "gesture": "Swipe_Right",
                "action_type": "shortcut",
                "keys": ["nexttrack"],
                "description": "Next Track",
            },
            {
                "id": "default-peace",
                "gesture": "Peace",
                "action_type": "shortcut",
                "keys": ["playpause"],
                "description": "Play/Pause Media",
            },
        ]

    def _load_default_mappings(self):
        self.mappings = {
            mapping["gesture"]: dict(mapping)
            for mapping in self._default_mappings()
        }

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    loaded_mappings = data.get("mappings", [])
                    if loaded_mappings:
                        self.mappings = {mapping["gesture"]: mapping for mapping in loaded_mappings}
                        if self._normalize_mappings():
                            self.save_config()
                    else:
                        self._load_default_mappings()
                        self.save_config()
            except Exception as e:
                print(f"Error loading config: {e}")
                self._load_default_mappings()
                self.save_config()
        else:
            print("Config file not found. Creating default settings...")
            self._load_default_mappings()
            self.save_config()

    def execute_action(self, gesture):
        if gesture in self.mappings:
            now = time.time()
            last = self.last_action_time.get(gesture, 0.0)
            if now - last < self.cooldown:
                return False
                
            self.last_action_time[gesture] = now
            action = self.mappings[gesture]
            action_type = action.get("action_type")
            keys = action.get("keys", [])
            
            print(f"Executing: {gesture} -> {keys}")
            
            try:
                if action_type == "shortcut":
                    normalized_keys = self._normalize_keys(keys)
                    if normalized_keys:
                        keyboard.send('+'.join(normalized_keys))
                elif action_type == "mouse_click":
                    pyautogui.click()
                elif action_type == "mouse_right_click":
                    pyautogui.rightClick()
                elif action_type == "launch":
                    if keys:
                        cmd = keys[0] if isinstance(keys, list) else keys
                        try:
                            os.startfile(cmd)
                        except Exception:
                            # Fallback: try via Windows start command (handles
                            # app names like "chrome", "spotify", etc.)
                            subprocess.Popen(["cmd", "/c", "start", "", cmd])
            except Exception as e:
                print(f"Error executing gesture '{gesture}': {e}")
                return False
                
            return True
            
        return False

    def add_mapping(self, gesture, keys, action_type="shortcut", description="Custom", custom_rule=None):
        normalized_keys = self._normalize_keys(keys) if action_type == "shortcut" else list(keys)
        mapping = {
            "id": str(int(time.time())),
            "gesture": gesture,
            "action_type": action_type,
            "keys": normalized_keys,
            "description": description
        }
        if custom_rule:
            mapping["custom_rule"] = custom_rule
        self.mappings[gesture] = mapping
        self.save_config()

    @staticmethod
    def _normalize_key(key_name):
        normalized = str(key_name or "").strip().lower().replace("-", " ")
        return KEY_ALIASES.get(normalized, normalized)

    def _normalize_keys(self, keys):
        if isinstance(keys, str):
            raw_keys = keys.split("+") if keys else []
        else:
            raw_keys = keys or []
        return [self._normalize_key(key) for key in raw_keys if str(key).strip()]

    def _normalize_mappings(self):
        changed = False
        for mapping in self.mappings.values():
            if mapping.get("action_type") != "shortcut":
                continue
            original_keys = mapping.get("keys", [])
            normalized_keys = self._normalize_keys(original_keys)
            if normalized_keys != original_keys:
                mapping["keys"] = normalized_keys
                changed = True
        return changed
        
    def delete_mapping(self, gesture):
        if gesture in self.mappings:
            del self.mappings[gesture]
            self.save_config()

    def get_mapping_descriptions(self):
        """Returns a string list of gestures and their descriptions."""
        desc_list = []
        for g_name, mapping in self.mappings.items():
            desc = mapping.get('description', 'No description')
            desc_list.append(f"- Gesture: {g_name} | Action: {desc}")
        return "\n".join(desc_list)

    def trigger_gesture(self, gesture_name):
        """Triggers an action by gesture name."""
        # Normalize and find the gesture
        target = gesture_name.strip().replace(" ", "_")
        for g_name in self.mappings:
            if g_name.lower() == target.lower():
                return self.execute_action(g_name)
        return False

    def launch_app(self, app_name):
        """Attempts to launch an application by name (heuristic)."""
        try:
            # Common Windows app names/commands
            common_apps = {
                "chrome": "chrome",
                "browser": "chrome",
                "notepad": "notepad",
                "calculator": "calc",
                "youtube": "https://www.youtube.com",
                "spotify": "spotify",
                "vscode": "code",
                "word": "winword",
                "excel": "excel",
                "powerpoint": "powerpnt",
                "edge": "msedge"
            }
            target = common_apps.get(app_name.lower(), app_name)
            os.startfile(target)
            with self._lock:
                self.recent_targets.append({"name": app_name.lower(), "command": target})
                self.recent_targets = self.recent_targets[-30:]
            return True
        except Exception:
            # Try searching via start command
            try:
                subprocess.Popen(["cmd", "/c", "start", "", app_name])
                with self._lock:
                    self.recent_targets.append({"name": app_name.lower(), "command": app_name})
                    self.recent_targets = self.recent_targets[-30:]
                return True
            except Exception:
                return False

    def close_app(self, app_name):
        """Attempts to close an application by name using taskkill."""
        try:
            normalized = app_name.strip().lower()
            if normalized in {"recent", "recently opened", "last", "it", "that"}:
                with self._lock:
                    if self.recent_targets:
                        normalized = self.recent_targets[-1]["name"]

            # Map common names to executable names
            common_exes = {
                "chrome": "chrome.exe",
                "browser": "chrome.exe",
                "notepad": "notepad.exe",
                "calculator": "CalculatorApp.exe",
                "spotify": "Spotify.exe",
                "vscode": "Code.exe",
                "word": "WINWORD.EXE",
                "excel": "EXCEL.EXE",
                "edge": "msedge.exe"
            }
            exe_name = common_exes.get(normalized, f"{normalized}.exe")
            # /F forces closure, /IM targets the image name.
            result = subprocess.run(["taskkill", "/F", "/IM", exe_name, "/T"], capture_output=True, text=True)
            if result.returncode == 0:
                with self._lock:
                    self.recent_targets = [t for t in self.recent_targets if t["name"] != normalized]
                return True
            return False
        except Exception as e:
            print(f"Error closing app: {e}")
            return False

    def execute_raw(self, r_type, payload):
        """Executes a direct raw system command."""
        try:
            print(f"Deep Integration Execution: {r_type} -> {payload}")
            if r_type == "shortcut":
                keyboard.send('+'.join(self._normalize_keys(payload)))
            elif r_type == "type":
                pyautogui.write(payload)
            elif r_type == "system":
                # Handle special hardware keys
                if payload == "volumeup":
                    keyboard.send("volume up")
                elif payload == "volumedown":
                    keyboard.send("volume down")
                elif payload == "volumemute":
                    keyboard.send("volume mute")
                elif payload == "brightup":
                    # Note: Brightness often requires specific DLLs or WMIs on Windows
                    # This is a fallback attempt
                    os.system("powershell (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,100)")
            return True
        except Exception as e:
            print(f"Error in Raw Execution: {e}")
            return False

    def save_config(self):
        CONFIG_DIR = os.path.dirname(CONFIG_FILE)
        if not os.path.exists(CONFIG_DIR):
            try:
                os.makedirs(CONFIG_DIR)
            except Exception as e:
                print(f"Failed to create config dir: {e}")

        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            data = {"visuals": {"show_feed": True, "theme": "Dr. Strange"}}
            
        data["mappings"] = list(self.mappings.values())
        
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
