# -*- coding: utf-8 -*-
"""
adb_controller.py
=================
Low-level Android device and emulator controller via ADB and optional Appium.
Features:
- Screen resolution discovery & automatic coordinate scaling
- UI Hierarchy search prioritized by: Resource-ID -> Exact Text -> Partial Text -> Bounds Center
- Clamped coordinate taps and swipes
- Timestamped audit artifacts (screenshots and XML dumps)
- Resilient connection management and bounded timeouts
"""

import os
import sys
import shutil
import subprocess
import time
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any


class AdbController:
    REFERENCE_WIDTH = 900
    REFERENCE_HEIGHT = 1600

    def __init__(self,
                 adb_path: str = "",
                 serial: str = "127.0.0.1:16384",
                 package_name: str = "com.moh.nusukapp",
                 appium_ctrl=None):
        self.adb = adb_path or self._find_adb()
        self.serial = serial
        self.package = package_name
        self.appium = appium_ctrl

        self.cache_dir = os.path.join(os.path.dirname(__file__) or ".", "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.last_ui_root: Optional[ET.Element] = None
        self._cached_screen_size: Optional[Tuple[int, int]] = None
        self._last_size_check_time: float = 0.0

    # ── Raw ADB execution ─────────────────────────────────────────────────────
    def run(self, *args, timeout: float = 8.0) -> Tuple[str, int]:
        if not self.adb:
            return "NO_ADB", -1
        cmd = [self.adb, "-s", self.serial] + list(args)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=timeout, encoding="utf-8", errors="replace")
            return res.stdout + res.stderr, res.returncode
        except subprocess.TimeoutExpired:
            return "TIMEOUT", -1
        except Exception as e:
            return str(e), -1

    # ── Connection management ─────────────────────────────────────────────────
    def connect(self) -> bool:
        if not self.adb:
            return False
        # 1. Try preferred serial
        try:
            res = subprocess.run([self.adb, "connect", self.serial],
                                 capture_output=True, text=True, timeout=5.0,
                                 encoding="utf-8", errors="replace")
            if "connected" in res.stdout.lower() or "already" in res.stdout.lower():
                return True
        except Exception:
            pass

        # 2. Try common emulator fallback ports (MuMu 12: 16384, MuMu 6: 7555, generic: 5555)
        fallback_ports = ["127.0.0.1:16384", "127.0.0.1:7555", "127.0.0.1:5555"]
        for s in fallback_ports:
            if s == self.serial:
                continue
            try:
                res = subprocess.run([self.adb, "connect", s],
                                     capture_output=True, text=True, timeout=3.0,
                                     encoding="utf-8", errors="replace")
                if "connected" in res.stdout.lower() or "already" in res.stdout.lower():
                    self.serial = s
                    return True
            except Exception:
                pass
        return False

    def is_connected(self) -> bool:
        if not self.adb:
            return False
        try:
            res = subprocess.run([self.adb, "devices"],
                                 capture_output=True, text=True, timeout=3.0,
                                 encoding="utf-8", errors="replace")
            devices = []
            for line in res.stdout.splitlines()[1:]:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[1] == "device":
                    devices.append(parts[0])

            if self.serial in devices:
                return True
            # If preferred serial is not connected but another device is online, adopt it
            if devices:
                self.serial = devices[0]
                return True
            return False
        except Exception:
            return False

    def ensure_connected(self) -> bool:
        if not self.is_connected():
            return self.connect()
        return True

    # ── Screen dimensions and scaling ─────────────────────────────────────────
    def get_screen_size(self, force_refresh: bool = False) -> Tuple[int, int]:
        """Queries physical/override display resolution via ADB."""
        now = time.time()
        if not force_refresh and self._cached_screen_size and (now - self._last_size_check_time < 60.0):
            return self._cached_screen_size

        if not self.is_connected():
            return (self.REFERENCE_WIDTH, self.REFERENCE_HEIGHT)

        out, code = self.run("shell", "wm", "size", timeout=4.0)
        # Parse output like:
        # Physical size: 720x1280
        # Override size: 900x1600
        override_match = re.search(r"Override size:\s*(\d+)x(\d+)", out)
        if override_match:
            size = (int(override_match.group(1)), int(override_match.group(2)))
            self._cached_screen_size = size
            self._last_size_check_time = now
            return size

        phys_match = re.search(r"Physical size:\s*(\d+)x(\d+)", out)
        if phys_match:
            size = (int(phys_match.group(1)), int(phys_match.group(2)))
            self._cached_screen_size = size
            self._last_size_check_time = now
            return size

        # Fallback default
        return (self.REFERENCE_WIDTH, self.REFERENCE_HEIGHT)

    def scale_coords(self, x: int, y: int, base_w: int = REFERENCE_WIDTH, base_h: int = REFERENCE_HEIGHT) -> Tuple[int, int]:
        """Scales reference coordinates (e.g. 900x1600) to the actual active device resolution and clamps them."""
        actual_w, actual_h = self.get_screen_size()
        if base_w <= 0 or base_h <= 0:
            return (x, y)

        scaled_x = int((x / base_w) * actual_w)
        scaled_y = int((y / base_h) * actual_h)

        # Clamp inside actual screen boundaries
        clamped_x = max(0, min(actual_w - 1, scaled_x))
        clamped_y = max(0, min(actual_h - 1, scaled_y))
        return (clamped_x, clamped_y)

    # ── Screenshots and UI Dumps ──────────────────────────────────────────────
    def screencap(self, filename: str = "current_screen.png", save_audit_copy: bool = False) -> str:
        """Captures device screen and caches it locally."""
        self.ensure_connected()
        local_path = os.path.join(self.cache_dir, filename)

        # 1. Prefer Appium if available
        if self.appium and self.appium.is_connected:
            try:
                import base64
                b64 = self.appium.screenshot_base64()
                if b64:
                    with open(local_path, "wb") as f:
                        f.write(base64.b64decode(b64))
                    if save_audit_copy:
                        self._save_audit_artifact(local_path, "png")
                    return local_path
            except Exception:
                pass

        # 2. ADB fallback
        self.run("shell", "screencap", "-p", "/sdcard/tmp_sc.png", timeout=4.0)
        self.run("pull", "/sdcard/tmp_sc.png", local_path, timeout=4.0)

        if save_audit_copy and os.path.exists(local_path):
            self._save_audit_artifact(local_path, "png")

        return local_path

    def dump_ui(self, save_audit_copy: bool = False) -> Optional[ET.Element]:
        """Dumps UI hierarchy via uiautomator and returns root XML element."""
        if not self.ensure_connected():
            return None

        self.run("shell", "uiautomator", "dump", "/sdcard/tmp_ui.xml", timeout=5.0)
        local_xml = os.path.join(self.cache_dir, "ui_dump.xml")
        _, code = self.run("pull", "/sdcard/tmp_ui.xml", local_xml, timeout=4.0)

        if code == 0 and os.path.exists(local_xml):
            try:
                tree = ET.parse(local_xml)
                self.last_ui_root = tree.getroot()
                if save_audit_copy:
                    self._save_audit_artifact(local_xml, "xml")
                return self.last_ui_root
            except Exception:
                pass
        return None

    def _save_audit_artifact(self, source_path: str, ext: str):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        audit_file = os.path.join(self.cache_dir, f"audit_{timestamp}.{ext}")
        try:
            shutil.copy2(source_path, audit_file)
        except Exception:
            pass

    # ── Touch & gesture actions ───────────────────────────────────────────────
    def tap(self, x: int, y: int, delay: float = 0.2, auto_scale: bool = False):
        """Tap at coordinates (optionally scaled from reference 900x1600)."""
        actual_x, actual_y = self.scale_coords(x, y) if auto_scale else (x, y)

        if self.appium and self.appium.is_connected:
            try:
                self.appium.tap(actual_x, actual_y)
                if delay > 0:
                    time.sleep(delay)
                return
            except Exception:
                pass

        self.ensure_connected()
        self.run("shell", "input", "tap", str(actual_x), str(actual_y))
        if delay > 0:
            time.sleep(delay)

    def swipe(self, x1: int, y1: int, x2: int, y2: int,
              duration_ms: int = 300, delay: float = 0.3, auto_scale: bool = False):
        ax1, ay1 = self.scale_coords(x1, y1) if auto_scale else (x1, y1)
        ax2, ay2 = self.scale_coords(x2, y2) if auto_scale else (x2, y2)

        if self.appium and self.appium.is_connected:
            try:
                self.appium.swipe(ax1, ay1, ax2, ay2, duration_ms)
                if delay > 0:
                    time.sleep(delay)
                return
            except Exception:
                pass

        self.ensure_connected()
        self.run("shell", "input", "swipe",
                 str(ax1), str(ay1), str(ax2), str(ay2), str(duration_ms))
        if delay > 0:
            time.sleep(delay)

    def press_key(self, keycode: str, delay: float = 0.2):
        self.ensure_connected()
        self.run("shell", "input", "keyevent", keycode)
        if delay > 0:
            time.sleep(delay)

    def press_back(self, delay: float = 0.3):
        if self.appium and self.appium.is_connected:
            try:
                self.appium.press_back()
                if delay > 0:
                    time.sleep(delay)
                return
            except Exception:
                pass
        self.press_key("KEYCODE_BACK", delay)

    def press_home(self, delay: float = 0.3):
        self.press_key("KEYCODE_HOME", delay)

    def is_keyboard_open(self) -> bool:
        """Returns True if Android software keyboard is currently visible."""
        if not self.is_connected():
            return False
        out, _ = self.run("shell", "dumpsys", "input_method")
        return "mInputShown=true" in out

    def hide_keyboard(self, delay: float = 0.3):
        """Hides the keyboard safely without navigating back if keyboard is already hidden."""
        if self.is_keyboard_open():
            self.press_back(delay)

    def clear_text(self, count: int = 40):
        """Clears text in the currently focused input by sending KEYCODE_DEL."""
        self.ensure_connected()
        self.run("shell", "input", "keyevent", *(["67"] * count))

    def type_text(self, text: str, delay: float = 0.2):
        """Types text safely via input text or Appium."""
        if not text:
            return
        if self.appium and self.appium.is_connected:
            try:
                self.appium.type_text(text)
                if delay > 0:
                    time.sleep(delay)
                return
            except Exception:
                pass

        self.ensure_connected()
        escaped = text.replace(" ", "%s")
        for ch in ["&", "<", ">", "(", ")", "'", '"', ";", "|", "*", "$"]:
            escaped = escaped.replace(ch, "\\" + ch)
        self.run("shell", "input", "text", escaped)
        if delay > 0:
            time.sleep(delay)

    # ── App lifecycle ─────────────────────────────────────────────────────────
    def launch_app(self, delay: float = 3.0):
        if self.appium and self.appium.is_connected:
            try:
                self.appium.launch_app()
                if delay > 0:
                    time.sleep(delay)
                return
            except Exception:
                pass
        self.ensure_connected()
        self.run("shell", "monkey", "-p", self.package,
                 "-c", "android.intent.category.LAUNCHER", "1")
        if delay > 0:
            time.sleep(delay)

    def force_stop(self, delay: float = 1.0):
        self.ensure_connected()
        self.run("shell", "am", "force-stop", self.package)
        if delay > 0:
            time.sleep(delay)

    def get_focused_activity(self) -> str:
        if not self.is_connected():
            return ""
        out, _ = self.run("shell", "dumpsys", "window", "windows")
        m = re.search(r"mCurrentFocus=Window\{[^ ]+ [^ ]+ ([^}]+)\}", out)
        if m:
            return m.group(1)
        m2 = re.search(r"mFocusedApp=ActivityRecord\{[^ ]+ [^ ]+ ([^ ]+)", out)
        return m2.group(1) if m2 else ""

    # ── Element search & interaction (Hierarchy-first) ────────────────────────
    @staticmethod
    def parse_bounds(bounds_str: str) -> Optional[Tuple[int, int]]:
        m = re.findall(r"\[(\d+),(\d+)\]", bounds_str)
        if len(m) == 2:
            x1, y1 = int(m[0][0]), int(m[0][1])
            x2, y2 = int(m[1][0]), int(m[1][1])
            return ((x1 + x2) // 2, (y1 + y2) // 2)
        return None

    def find_node(self, text: str = "", partial: bool = True,
                  res_id: str = "", cls: str = "") -> Optional[Dict[str, Any]]:
        """
        Searches UI hierarchy in priority order:
        1. Exact/partial Resource-ID
        2. Exact/partial Text or Content Description
        """
        root = self.dump_ui()
        if root is None:
            return None
        target_lower = text.lower().strip() if text else ""

        for node in root.iter():
            n_text = node.get("text", "").strip()
            n_desc = node.get("content-desc", "").strip()
            n_res = node.get("resource-id", "").strip()
            n_cls = node.get("class", "").strip()
            n_bounds = node.get("bounds", "").strip()

            # Resource ID match
            if res_id and res_id not in n_res:
                continue

            # Class match
            if cls and cls not in n_cls:
                continue

            # Text match
            if text:
                if partial:
                    matched = (target_lower in n_text.lower()) or (target_lower in n_desc.lower())
                else:
                    matched = (text == n_text) or (text == n_desc)
                if not matched:
                    continue

            center = self.parse_bounds(n_bounds)
            return {
                "text": n_text,
                "desc": n_desc,
                "class": n_cls,
                "resource_id": n_res,
                "bounds": n_bounds,
                "center": center,
                "clickable": node.get("clickable") == "true",
                "enabled": node.get("enabled") == "true",
            }
        return None

    def find_all_nodes(self, text: str = "", partial: bool = True,
                       cls: str = "", res_id: str = "") -> List[Dict[str, Any]]:
        root = self.dump_ui()
        if root is None:
            return []
        results = []
        target_lower = text.lower().strip() if text else ""

        for node in root.iter():
            n_text = node.get("text", "").strip()
            n_desc = node.get("content-desc", "").strip()
            n_cls = node.get("class", "").strip()
            n_res = node.get("resource-id", "").strip()
            n_bounds = node.get("bounds", "").strip()

            if res_id and res_id not in n_res:
                continue
            if cls and cls not in n_cls:
                continue

            if text:
                if partial:
                    matched = (target_lower in n_text.lower()) or (target_lower in n_desc.lower())
                else:
                    matched = (text == n_text) or (text == n_desc)
                if not matched:
                    continue

            center = self.parse_bounds(n_bounds)
            results.append({
                "text": n_text,
                "desc": n_desc,
                "class": n_cls,
                "resource_id": n_res,
                "bounds": n_bounds,
                "center": center,
                "clickable": node.get("clickable") == "true",
                "enabled": node.get("enabled") == "true",
            })
        return results

    def click_node(self, node: Dict[str, Any], delay: float = 0.3) -> bool:
        if node and node.get("center"):
            cx, cy = node["center"]
            self.tap(cx, cy, delay=delay)
            return True
        return False

    def click_text(self, text: str, partial: bool = True, delay: float = 0.3) -> bool:
        """Clicks an element by text using element bounds first; falls back to Appium."""
        if self.appium and self.appium.is_connected:
            if self.appium.find_and_tap(text):
                if delay > 0:
                    time.sleep(delay)
                return True

        node = self.find_node(text=text, partial=partial)
        if node and node.get("center"):
            self.tap(node["center"][0], node["center"][1], delay=delay)
            return True
        return False

    def click_resource_id(self, res_id: str, delay: float = 0.3) -> bool:
        node = self.find_node(res_id=res_id)
        if node and node.get("center"):
            self.tap(node["center"][0], node["center"][1], delay=delay)
            return True
        return False

    @staticmethod
    def _find_adb() -> str:
        # 1. Bundled platform-tools in project folder
        bundled = os.path.join(os.path.dirname(__file__), "platform-tools", "adb.exe")
        if os.path.exists(bundled):
            return bundled

        # 2. System PATH
        in_path = shutil.which("adb")
        if in_path:
            return in_path

        # 3. Common MuMu Player and Android SDK locations
        candidates = [
            r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
            r"C:\Program Files\Netease\MuMuPlayer\nx_device\15.0\shell\adb.exe",
            r"C:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe",
            r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0\shell\adb.exe",
            r"C:\platform-tools\adb.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe"),
        ]
        for p in candidates:
            if p and os.path.exists(p):
                return p
        return "adb"
