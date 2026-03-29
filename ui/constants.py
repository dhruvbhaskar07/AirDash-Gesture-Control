AVAILABLE_GESTURES = [
    "Pinch",
    "Closed Fist",
    "Open Palm",
    "Swipe_Left",
    "Swipe_Right",
    "Swipe_Up",
    "Swipe_Down",
    "Peace",
    "Pinky_Only",
    "Spiderman",
]

ACTION_TYPES = ["shortcut", "mouse_click", "mouse_right_click", "launch"]

SHORTCUT_PRESETS = {
    "Show Desktop": "win+d",
    "Copy": "ctrl+c",
    "Paste": "ctrl+v",
    "Cut": "ctrl+x",
    "Undo": "ctrl+z",
    "Redo": "ctrl+y",
    "Select All": "ctrl+a",
    "Save": "ctrl+s",
    "Close Window": "alt+f4",
    "Switch Window": "alt+tab",
    "Task View": "win+tab",
    "Lock Screen": "win+l",
    "Screenshot": "win+shift+s",
    "Play/Pause Media": "playpause",
    "Next Track": "nexttrack",
    "Previous Track": "prevtrack",
    "Volume Up": "volup",
    "Volume Down": "voldown",
    "Volume Mute": "volmute",
    "Minimize All": "win+m",
    "Open Settings": "win+i",
    "Open Explorer": "win+e",
}

GESTURE_ICONS = {
    "Pinch": "\U0001F90F",
    "Closed Fist": "\u270A",
    "Open Palm": "\U0001F91A",
    "Swipe_Left": "\u2B05",
    "Swipe_Right": "\u27A1",
    "Swipe_Up": "\u2B06",
    "Swipe_Down": "\u2B07",
    "Peace": "\u270C",
    "Pinky_Only": "\U0001F91E",
    "Spiderman": "\U0001F918",
}

GESTURE_DESCRIPTIONS = {
    "Pinch": "Thumb and index finger together",
    "Closed Fist": "All fingers closed",
    "Open Palm": "All five fingers extended",
    "Swipe_Left": "Open palm moving left",
    "Swipe_Right": "Open palm moving right",
    "Swipe_Up": "Open palm moving up",
    "Swipe_Down": "Open palm moving down",
    "Peace": "Index and middle fingers up",
    "Pinky_Only": "Only pinky finger raised",
    "Spiderman": "Index, pinky and thumb extended",
}

ACTION_LABELS = {
    "shortcut": "Keyboard Shortcut",
    "mouse_click": "Mouse Click",
    "mouse_right_click": "Right Click",
    "launch": "Launch App",
}

ACTION_ICONS = {
    "shortcut": "\u2328",
    "mouse_click": "\U0001F5B1",
    "mouse_right_click": "\U0001F5B1",
    "launch": "\U0001F680",
}

FONT_FAMILY = "Segoe UI"

# â”€â”€ Dark theme palette (same black tones, refined) â”€â”€
CLR_BG = "#050505"
CLR_BG_ALT = "#0B0B0B"
CLR_SIDEBAR = "#0A0A0A"
CLR_CARD = "#111111"
CLR_CARD_HOVER = "#171717"
CLR_BORDER = "#232323"
CLR_BORDER_SOFT = "#1A1A1A"
CLR_INPUT = "#141414"
CLR_ACCENT = "#2D2D2D"
CLR_ACCENT_HOVER = "#3A3A3A"
CLR_ACCENT_DIM = "#1B1B1B"
CLR_ACCENT_GLOW = "#555555"
CLR_CYAN = "#7F7F7F"
CLR_CYAN_DIM = "#3E3E3E"
CLR_GREEN = "#4ADE80"
CLR_GREEN_DIM = "#1A3A2A"
CLR_RED = "#F87171"
CLR_RED_DIM = "#3A1A1A"
CLR_RED_BG = "#1A1010"
CLR_ORANGE = "#FBBF24"
CLR_ORANGE_DIM = "#3A2A10"
CLR_TEXT = "#D2D2D2"
CLR_TEXT_DIM = "#A0A0A0"
CLR_TEXT_MUTED = "#6B6B6B"
CLR_WHITE = "#F0F0F0"
CLR_SURFACE = "#101010"
CLR_GLASS = "#151515"
CLR_GLASS_ALT = "#111111"
CLR_GLOW_LEFT = "#0D0D0D"
CLR_GLOW_RIGHT = "#101010"
CLR_SELECTED = "#1E1E1E"

# Preset categories for easier browsing
PRESET_CATEGORIES = {
    "Media": ["Play/Pause Media", "Next Track", "Previous Track", "Volume Up", "Volume Down", "Volume Mute"],
    "Editing": ["Copy", "Paste", "Cut", "Undo", "Redo", "Select All", "Save"],
    "Windows": ["Show Desktop", "Close Window", "Switch Window", "Task View", "Lock Screen", "Minimize All"],
    "System": ["Screenshot", "Open Settings", "Open Explorer"],
}

# Common apps for launch search â€” organized by category
LAUNCHABLE_APPS_BY_CATEGORY = {
    "Browsers": {
        "Google Chrome": {"cmd": "chrome", "icon": "\U0001F310"},
        "Microsoft Edge": {"cmd": "msedge", "icon": "\U0001F310"},
        "Firefox": {"cmd": "firefox", "icon": "\U0001F525"},
        "Opera": {"cmd": "opera", "icon": "\U0001F310"},
        "Brave": {"cmd": "brave", "icon": "\U0001F310"},
    },
    "Social & Chat": {
        "WhatsApp": {"cmd": "whatsapp", "icon": "\U0001F4AC"},
        "Telegram": {"cmd": "telegram", "icon": "\U0001F4AC"},
        "Discord": {"cmd": "discord", "icon": "\U0001F4AC"},
        "Slack": {"cmd": "slack", "icon": "\U0001F4AC"},
        "Zoom": {"cmd": "zoom", "icon": "\U0001F4F9"},
        "Microsoft Teams": {"cmd": "msteams", "icon": "\U0001F4AC"},
        "Skype": {"cmd": "skype", "icon": "\U0001F4AC"},
    },
    "Media & Music": {
        "Spotify": {"cmd": "spotify", "icon": "\U0001F3B5"},
        "VLC Player": {"cmd": "vlc", "icon": "\U0001F3AC"},
        "Windows Media Player": {"cmd": "wmplayer", "icon": "\U0001F3B5"},
        "iTunes": {"cmd": "itunes", "icon": "\U0001F3B5"},
        "OBS Studio": {"cmd": "obs64", "icon": "\U0001F3AC"},
        "Photos": {"cmd": "ms-photos:", "icon": "\U0001F4F7"},
        "Movies & TV": {"cmd": "mswindowsvideo:", "icon": "\U0001F3AC"},
        "Groove Music": {"cmd": "mswindowsmusic:", "icon": "\U0001F3B5"},
    },
    "Productivity": {
        "Word": {"cmd": "winword", "icon": "\U0001F4C4"},
        "Excel": {"cmd": "excel", "icon": "\U0001F4CA"},
        "PowerPoint": {"cmd": "powerpnt", "icon": "\U0001F4CA"},
        "OneNote": {"cmd": "onenote", "icon": "\U0001F4D3"},
        "Outlook": {"cmd": "outlook", "icon": "\U0001F4E7"},
        "Notepad": {"cmd": "notepad", "icon": "\U0001F4DD"},
        "WordPad": {"cmd": "wordpad", "icon": "\U0001F4DD"},
        "Calculator": {"cmd": "calc", "icon": "\U0001F522"},
        "Sticky Notes": {"cmd": "ms-actioncenter:", "icon": "\U0001F4CC"},
        "Calendar": {"cmd": "outlookcal:", "icon": "\U0001F4C5"},
    },
    "Development": {
        "VS Code": {"cmd": "code", "icon": "\U0001F4BB"},
        "Visual Studio": {"cmd": "devenv", "icon": "\U0001F4BB"},
        "Command Prompt": {"cmd": "cmd", "icon": "\u2328"},
        "PowerShell": {"cmd": "powershell", "icon": "\u2328"},
        "Windows Terminal": {"cmd": "wt", "icon": "\u2328"},
        "Git Bash": {"cmd": "git-bash", "icon": "\u2328"},
        "Notepad++": {"cmd": "notepad++", "icon": "\U0001F4DD"},
        "Sublime Text": {"cmd": "subl", "icon": "\U0001F4DD"},
    },
    "Gaming": {
        "Steam": {"cmd": "steam", "icon": "\U0001F3AE"},
        "Epic Games": {"cmd": "EpicGamesLauncher", "icon": "\U0001F3AE"},
        "Xbox App": {"cmd": "xbox:", "icon": "\U0001F3AE"},
    },
    "System Tools": {
        "File Explorer": {"cmd": "explorer", "icon": "\U0001F4C1"},
        "Task Manager": {"cmd": "taskmgr", "icon": "\u2699"},
        "Control Panel": {"cmd": "control", "icon": "\u2699"},
        "Snipping Tool": {"cmd": "snippingtool", "icon": "\u2702"},
        "Paint": {"cmd": "mspaint", "icon": "\U0001F3A8"},
        "Registry Editor": {"cmd": "regedit", "icon": "\u2699"},
        "Disk Management": {"cmd": "diskmgmt.msc", "icon": "\U0001F4BF"},
        "Device Manager": {"cmd": "devmgmt.msc", "icon": "\u2699"},
        "System Info": {"cmd": "msinfo32", "icon": "\u2139"},
        "Resource Monitor": {"cmd": "resmon", "icon": "\U0001F4CA"},
        "Event Viewer": {"cmd": "eventvwr.msc", "icon": "\U0001F4CB"},
        "Disk Cleanup": {"cmd": "cleanmgr", "icon": "\U0001F5D1"},
        "Defragment": {"cmd": "dfrgui", "icon": "\U0001F4BF"},
        "Remote Desktop": {"cmd": "mstsc", "icon": "\U0001F5A5"},
        "Character Map": {"cmd": "charmap", "icon": "A"},
        "On-Screen Keyboard": {"cmd": "osk", "icon": "\u2328"},
        "Magnifier": {"cmd": "magnify", "icon": "\U0001F50D"},
    },
    "Windows Settings": {
        "Settings Home": {"cmd": "ms-settings:", "icon": "\u2699"},
        "Wi-Fi Settings": {"cmd": "ms-settings:network-wifi", "icon": "\U0001F4F6"},
        "Bluetooth Settings": {"cmd": "ms-settings:bluetooth", "icon": "\U0001F4F6"},
        "Display Settings": {"cmd": "ms-settings:display", "icon": "\U0001F5A5"},
        "Sound Settings": {"cmd": "ms-settings:sound", "icon": "\U0001F50A"},
        "Notifications": {"cmd": "ms-settings:notifications", "icon": "\U0001F514"},
        "Battery & Power": {"cmd": "ms-settings:batterysaver", "icon": "\U0001F50B"},
        "Storage Settings": {"cmd": "ms-settings:storagesense", "icon": "\U0001F4BF"},
        "Apps & Features": {"cmd": "ms-settings:appsfeatures", "icon": "\U0001F4E6"},
        "Default Apps": {"cmd": "ms-settings:defaultapps", "icon": "\U0001F4E6"},
        "Privacy Settings": {"cmd": "ms-settings:privacy", "icon": "\U0001F512"},
        "Windows Update": {"cmd": "ms-settings:windowsupdate", "icon": "\U0001F504"},
        "Personalization": {"cmd": "ms-settings:personalization", "icon": "\U0001F3A8"},
        "Wallpaper": {"cmd": "ms-settings:personalization-background", "icon": "\U0001F5BC"},
        "Themes": {"cmd": "ms-settings:themes", "icon": "\U0001F3A8"},
        "Lock Screen": {"cmd": "ms-settings:lockscreen", "icon": "\U0001F512"},
        "Taskbar Settings": {"cmd": "ms-settings:taskbar", "icon": "\U0001F5A5"},
        "Mouse Settings": {"cmd": "ms-settings:mousetouchpad", "icon": "\U0001F5B1"},
        "Keyboard Settings": {"cmd": "ms-settings:typing", "icon": "\u2328"},
        "Date & Time": {"cmd": "ms-settings:dateandtime", "icon": "\U0001F552"},
        "Language & Region": {"cmd": "ms-settings:regionlanguage", "icon": "\U0001F30D"},
        "About This PC": {"cmd": "ms-settings:about", "icon": "\u2139"},
        "Accounts": {"cmd": "ms-settings:yourinfo", "icon": "\U0001F464"},
        "Sign-in Options": {"cmd": "ms-settings:signinoptions", "icon": "\U0001F511"},
        "Gaming Settings": {"cmd": "ms-settings:gaming-gamebar", "icon": "\U0001F3AE"},
        "Accessibility": {"cmd": "ms-settings:easeofaccess", "icon": "\u267F"},
        "Night Light": {"cmd": "ms-settings:nightlight", "icon": "\U0001F319"},
        "Multitasking": {"cmd": "ms-settings:multitasking", "icon": "\U0001F5A5"},
        "Proxy Settings": {"cmd": "ms-settings:network-proxy", "icon": "\U0001F310"},
        "VPN Settings": {"cmd": "ms-settings:network-vpn", "icon": "\U0001F512"},
    },
    "Websites": {
        "YouTube": {"cmd": "https://www.youtube.com", "icon": "\u25B6"},
        "Google": {"cmd": "https://www.google.com", "icon": "\U0001F310"},
        "Gmail": {"cmd": "https://mail.google.com", "icon": "\U0001F4E7"},
        "GitHub": {"cmd": "https://github.com", "icon": "\U0001F4BB"},
        "ChatGPT": {"cmd": "https://chat.openai.com", "icon": "\U0001F916"},
        "Twitter / X": {"cmd": "https://x.com", "icon": "\U0001F310"},
        "Instagram": {"cmd": "https://www.instagram.com", "icon": "\U0001F4F7"},
        "LinkedIn": {"cmd": "https://www.linkedin.com", "icon": "\U0001F4BC"},
        "Reddit": {"cmd": "https://www.reddit.com", "icon": "\U0001F4AC"},
        "Netflix": {"cmd": "https://www.netflix.com", "icon": "\U0001F3AC"},
        "Amazon": {"cmd": "https://www.amazon.com", "icon": "\U0001F6D2"},
    },
}

# Flat lookup for submit (maps friendly name -> info)
LAUNCHABLE_APPS = {}
for _cat, _apps in LAUNCHABLE_APPS_BY_CATEGORY.items():
    LAUNCHABLE_APPS.update(_apps)


