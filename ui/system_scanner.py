import os
import winreg
import shlex
import re
import subprocess
from pathlib import Path
from typing import Optional
from threading import Thread
import cv2
from .constants import LAUNCHABLE_APPS


_MAX_SYSTEM_APPS = 250
_VIRTUAL_CAMERA_KEYWORDS = (
    "virtual",
    "obs",
    "manycam",
    "xsplit",
    "droidcam",
    "iriun",
    "epoccam",
    "camo",
    "snap camera",
    "ndi",
    "stream",
    "smart connect",
    "connect camera",
    "vcam",
    "ip camera",
)
_PHYSICAL_CAMERA_HINTS = (
    "integrated",
    "internal",
    "built-in",
    "builtin",
    "webcam",
    "usb camera",
    "hd camera",
    "facetime",
    "realsense",
)
_WINDOWS_CAMERA_NAME_CACHE = None


def _get_windows_camera_names_fallback():
    """Fallback camera names from Windows PnP when DirectShow names are unavailable."""
    global _WINDOWS_CAMERA_NAME_CACHE
    if _WINDOWS_CAMERA_NAME_CACHE is not None:
        return list(_WINDOWS_CAMERA_NAME_CACHE)

    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-CimInstance Win32_PnPEntity | "
            "Where-Object { $_.Name -and ($_.PNPClass -eq 'Camera' -or $_.Service -eq 'usbvideo') } | "
            "Select-Object -ExpandProperty Name"
        ),
    ]
    names = []
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=2)
        if proc.returncode == 0:
            lines = [str(line or "").strip() for line in (proc.stdout or "").splitlines()]
            names = [line for line in lines if line]
    except Exception:
        names = []

    _WINDOWS_CAMERA_NAME_CACHE = names
    return list(_WINDOWS_CAMERA_NAME_CACHE)


def _can_read_from_camera(index: int, backend=None, read_attempts: int = 4) -> bool:
    """Fast probe: camera is usable only if at least one frame can be read."""
    cap = None
    try:
        cap = cv2.VideoCapture(index, backend) if backend is not None else cv2.VideoCapture(index)
        if not cap.isOpened():
            return False
        for _ in range(max(1, int(read_attempts))):
            ok, frame = cap.read()
            if ok and frame is not None:
                return True
        return False
    except Exception:
        return False
    finally:
        if cap is not None:
            cap.release()


def _clean_display_name(name: str) -> str:
    cleaned = str(name or "").strip()
    if cleaned.endswith(".exe"):
        cleaned = cleaned[:-4]
    # Collapse common duplicate suffixes from different sources
    cleaned = re.sub(r"\s*\((user|system|x64|x86)\)\s*$", "", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def _normalize_cmd(value: str) -> str:
    cmd = str(value or "").strip().replace('"', "")
    cmd = re.sub(r",\d+$", "", cmd).strip()
    # Some registry values look like: C:\App\app.exe,0
    if ".exe," in cmd.lower():
        cmd = cmd[: cmd.lower().rfind(".exe") + 4]
    return cmd.strip()


def _looks_like_noise(name: str) -> bool:
    lowered = name.lower()
    junk_tokens = (
        "update",
        "updater",
        "redistributable",
        "runtime",
        "driver",
        "hotfix",
        "service pack",
        "uninstall",
        "setup",
        "installer",
        "repair",
        "telemetry",
        "helper",
        "service",
    )
    return any(token in lowered for token in junk_tokens)


def _extract_executable_from_command(command: str) -> Optional[str]:
    cmd = str(command or "").strip()
    if not cmd:
        return None

    if cmd.startswith('"') and '"' in cmd[1:]:
        first = cmd[1:].split('"', 1)[0].strip()
        if first:
            return first

    try:
        tokens = shlex.split(cmd, posix=False)
    except Exception:
        tokens = cmd.split()

    for token in tokens:
        cleaned = token.strip('"')
        if cleaned.lower().endswith(".exe") or os.path.exists(cleaned):
            return cleaned
    return None


def _add_app(apps_found: dict, app_name: str, cmd: str, icon: str = "📦"):
    name = _clean_display_name(app_name)
    command = _normalize_cmd(cmd)
    if not name or not command:
        return
    if "${" in name or "}" in name:
        return
    blocked_commands = (
        "msiexec",
        "rundll32",
        "uninstall",
        "\\package cache\\",
        "installshield installation information",
    )
    command_lower = command.lower()
    if any(token in command_lower for token in blocked_commands):
        return
    if command_lower.endswith(".ico") or command_lower.endswith(".dll") or command_lower.endswith("setup.exe"):
        return
    if Path(command_lower).name.startswith("unins"):
        return
    if os.path.isdir(command):
        try:
            candidates = [p for p in Path(command).glob("*.exe")][:10]
        except OSError:
            candidates = []
        preferred = None
        name_tokens = set(name.lower().split())
        for candidate in candidates:
            stem = candidate.stem.lower()
            if stem in {"setup", "uninstall", "update", "installer"}:
                continue
            if any(token in stem for token in name_tokens if len(token) > 2):
                preferred = candidate
                break
            if preferred is None:
                preferred = candidate
        if preferred is None:
            return
        command = str(preferred)
        command_lower = command.lower()
    if len(name) > 70 or _looks_like_noise(name):
        return
    if name in LAUNCHABLE_APPS:
        return
    if name not in apps_found:
        apps_found[name] = {"cmd": command, "icon": icon}


def _scan_registry_uninstall_entries(apps_found: dict):
    uninstall_paths = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]
    hives = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]

    for hive in hives:
        for reg_path in uninstall_paths:
            try:
                with winreg.OpenKey(hive, reg_path) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                display_name = None
                                for value_name in ["DisplayName", "QuietDisplayName"]:
                                    try:
                                        display_name = winreg.QueryValueEx(subkey, value_name)[0]
                                        if display_name:
                                            break
                                    except OSError:
                                        continue
                                if not display_name:
                                    continue

                                cmd = None
                                for field in ["DisplayIcon", "InstallLocation", "UninstallString", "QuietUninstallString"]:
                                    try:
                                        raw_value = winreg.QueryValueEx(subkey, field)[0]
                                    except OSError:
                                        continue
                                    if not raw_value:
                                        continue
                                    if field in {"UninstallString", "QuietUninstallString"}:
                                        extracted = _extract_executable_from_command(raw_value)
                                        if extracted:
                                            cmd = extracted
                                            break
                                    else:
                                        cmd = raw_value
                                        break

                                if cmd:
                                    _add_app(apps_found, display_name, cmd)
                        except OSError:
                            continue
            except OSError:
                continue


def _scan_registry_app_paths(apps_found: dict):
    app_paths = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
        try:
            with winreg.OpenKey(hive, app_paths) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            default_value, _ = winreg.QueryValueEx(subkey, "")
                            app_name = Path(subkey_name).stem
                            _add_app(apps_found, app_name, default_value)
                    except OSError:
                        continue
        except OSError:
            continue


def _scan_start_menu_shortcuts(apps_found: dict):
    start_menu_dirs = [
        os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
    ]

    for root_dir in start_menu_dirs:
        if not root_dir or not os.path.isdir(root_dir):
            continue
        found = 0
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d.lower() not in {"startup", "accessories"}][:25]
            for file_name in files:
                if not file_name.lower().endswith(".lnk"):
                    continue
                app_name = Path(file_name).stem
                cmd = os.path.join(root, file_name)
                _add_app(apps_found, app_name, cmd)
                found += 1
                if found >= 180:
                    break
            if found >= 180:
                break


def _scan_windows_app_aliases(apps_found: dict):
    aliases_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\WindowsApps")
    if not aliases_dir or not os.path.isdir(aliases_dir):
        return

    try:
        for file_name in os.listdir(aliases_dir):
            if not file_name.lower().endswith(".exe"):
                continue
            app_name = Path(file_name).stem
            if app_name.lower() in {"python", "python3", "winget"}:
                continue
            _add_app(apps_found, app_name, app_name)
    except OSError:
        return


def _scan_program_files(apps_found: dict):
    drive_candidates = [Path("C:/"), Path("D:/"), Path("E:/")]
    for drive in drive_candidates:
        for program_root in [drive / "Program Files", drive / "Program Files (x86)"]:
            if not program_root.exists():
                continue
            try:
                folders = list(program_root.iterdir())[:50]
            except OSError:
                continue
            for folder in folders:
                if not folder.is_dir():
                    continue
                try:
                    files = list(folder.glob("*.exe"))
                except OSError:
                    continue
                for exe_file in files[:3]:
                    lowered = exe_file.name.lower()
                    if lowered in {"uninstall.exe", "setup.exe", "update.exe"}:
                        continue
                    _add_app(apps_found, folder.name.replace("_", " "), str(exe_file))
                    break


def _scan_installed_apps():
    """Scan Windows app sources and build a launchable app list."""
    apps_found = {}
    _scan_registry_uninstall_entries(apps_found)
    _scan_registry_app_paths(apps_found)
    _scan_start_menu_shortcuts(apps_found)
    _scan_windows_app_aliases(apps_found)
    _scan_program_files(apps_found)
    return dict(list(apps_found.items())[:_MAX_SYSTEM_APPS])

# Cache for scanned apps (populated on first search)
_SYSTEM_APPS_CACHE = None
_SCAN_IN_PROGRESS = False


def _get_system_apps():
    """Get cached system apps, or scan if not done yet."""
    global _SYSTEM_APPS_CACHE, _SCAN_IN_PROGRESS

    if _SYSTEM_APPS_CACHE is None and not _SCAN_IN_PROGRESS:
        _SCAN_IN_PROGRESS = True

        def scan_bg():
            global _SYSTEM_APPS_CACHE, _SCAN_IN_PROGRESS
            try:
                _SYSTEM_APPS_CACHE = _scan_installed_apps()
            finally:
                _SCAN_IN_PROGRESS = False

        Thread(target=scan_bg, daemon=True).start()
        return {}

    return _SYSTEM_APPS_CACHE or {}


def _get_directshow_camera_names():
    """
    Best-effort camera name list in DirectShow index order.
    Falls back to empty list when pygrabber/comtypes is unavailable.
    """
    try:
        from pygrabber.dshow_graph import FilterGraph  # Optional dependency
    except Exception:
        return _get_windows_camera_names_fallback()

    try:
        names = FilterGraph().get_input_devices() or []
    except Exception:
        names = []

    if not names:
        names = _get_windows_camera_names_fallback()

    clean = []
    for name in names:
        value = str(name or "").strip()
        clean.append(value)
    return clean


def _is_virtual_camera_name(camera_name: str) -> bool:
    lowered = str(camera_name or "").strip().lower()
    if not lowered:
        return False
    return any(token in lowered for token in _VIRTUAL_CAMERA_KEYWORDS)


def _camera_priority_key(index: int, camera_names: list):
    name = ""
    if 0 <= index < len(camera_names):
        name = camera_names[index]
    lowered = str(name or "").strip().lower()
    is_virtual = _is_virtual_camera_name(name)
    has_physical_hint = any(token in lowered for token in _PHYSICAL_CAMERA_HINTS)
    # Lower tuple sorts first:
    # 1) prefer non-virtual
    # 2) prefer cameras whose names look physical
    # 3) keep lower index as stable tie-breaker
    return (1 if is_virtual else 0, 0 if has_physical_hint else 1, index)


def _get_preferred_start_camera(max_index: int = 8, fallback: int = 0):
    """
    Fast startup hint: pick a likely physical camera index before probing opens.
    """
    names = _get_directshow_camera_names()
    if not names:
        # When camera names are unavailable, probe usable devices and avoid
        # index 0 if multiple cameras exist (common virtual-camera default).
        discovered = _discover_cameras(max_index=max_index)
        if discovered:
            if len(discovered) > 1 and int(fallback) in discovered:
                non_fallback = [idx for idx in discovered if idx != int(fallback)]
                if non_fallback:
                    return non_fallback[0]
            return discovered[0]
        return int(fallback)

    upper_bound = max(1, int(max_index))
    candidates = [idx for idx in range(min(len(names), upper_bound))]
    if not candidates:
        return int(fallback)
    ranked = sorted(candidates, key=lambda idx: _camera_priority_key(idx, names))
    return ranked[0]


def _discover_cameras(max_index: int = 5):
    """Return available camera indices that can open quickly."""
    camera_names = _get_directshow_camera_names()
    found = []
    for idx in range(max_index):
        try:
            # Accept camera only when at least one frame can be read.
            opened = False
            if hasattr(cv2, "CAP_DSHOW"):
                opened = _can_read_from_camera(idx, cv2.CAP_DSHOW)
            if not opened and hasattr(cv2, "CAP_MSMF"):
                opened = _can_read_from_camera(idx, cv2.CAP_MSMF)
            if not opened:
                opened = _can_read_from_camera(idx, None)
            if opened:
                found.append(idx)
        except Exception:
            pass
    if not found:
        if camera_names:
            upper = min(len(camera_names), max_index)
            fallback_indices = list(range(upper))
            return sorted(fallback_indices, key=lambda idx: _camera_priority_key(idx, camera_names))
        return found
    return sorted(found, key=lambda idx: _camera_priority_key(idx, camera_names))


