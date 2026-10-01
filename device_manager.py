# -*- coding: utf-8 -*-
"""
device_manager.py
=================
Discovers, verifies, and connects to Android Emulators and physical devices via ADB.
Provides structured preflight diagnostics and actionable remediation advice.
"""

import os
import sys
import json
import shutil
import subprocess
import time
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple


MUMU_CLI = r"C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe"
MUMU_ADB = r"C:\Program Files\Netease\MuMuPlayer\nx_device\15.0\shell\adb.exe"


@dataclass
class DeviceInfo:
    serial: str
    adb_path: str
    android_version: str
    sdk_version: str
    model: str
    is_emulator: bool
    screen_size: str = ""
    mumu_index: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AdbNotFoundError(RuntimeError):
    pass


class NoDeviceError(RuntimeError):
    pass


class DeviceOfflineError(RuntimeError):
    pass


class DeviceManager:
    def __init__(self, adb_path: Optional[str] = None, preferred_serial: Optional[str] = None):
        self.configured_adb_path = adb_path
        self.preferred_serial = preferred_serial
        try:
            self.adb_path = self._resolve_adb(adb_path)
        except AdbNotFoundError:
            self.adb_path = adb_path or "adb"

    def get_device(self) -> DeviceInfo:
        """Finds and connects to the active device or emulator."""
        self._assert_adb_exists()
        self._start_adb_server()
        self._ensure_mumu_connected()
        devices = self._list_adb_devices()

        if not devices:
            raise NoDeviceError(
                "لم يتم العثور على أي محاكي أو جهاز متصل عبر ADB.\n"
                "يرجى فتح محاكي MuMu Player والتأكد من تفعيل وضع المطورين وتصحيح USB (USB Debugging)."
            )

        # 1. Match preferred serial if specified
        if self.preferred_serial:
            for serial, state in devices:
                if serial == self.preferred_serial:
                    return self._build_device_info(serial, state)

        # 2. Match first online device
        for serial, state in devices:
            if state == "device":
                return self._build_device_info(serial, state)

        # 3. If devices exist but are unauthorized/offline
        serial, state = devices[0]
        raise DeviceOfflineError(
            f"الجهاز {serial} متصل ولكن حالته: '{state}'.\n"
            "يرجى الموافقة على تنبيه تصحيح USB داخل المحاكي أو إعادة تشغيل خادم ADB:\n"
            "adb kill-server && adb start-server"
        )

    def list_all_devices(self) -> List[DeviceInfo]:
        """Returns all connected and ready devices."""
        try:
            self._assert_adb_exists()
            self._start_adb_server()
            self._ensure_mumu_connected()
            result = []
            for serial, state in self._list_adb_devices():
                if state == "device":
                    try:
                        result.append(self._build_device_info(serial, state))
                    except Exception:
                        pass
            return result
        except Exception:
            return []

    def get_adb_version(self) -> str:
        try:
            if not self.adb_path or not os.path.exists(self.adb_path) and not shutil.which(self.adb_path):
                return ""
            res = subprocess.run([self.adb_path, "version"], capture_output=True, text=True, timeout=4)
            lines = res.stdout.strip().splitlines()
            return lines[0] if lines else ""
        except Exception:
            return ""

    def run_preflight(self, package_name: str = "com.moh.nusukapp") -> Dict[str, Any]:
        """Comprehensive structured diagnostic of the host, Python, ADB, and device environment."""
        report: Dict[str, Any] = {
            "python": {
                "version": sys.version.split()[0],
                "executable": sys.executable,
                "is_ok": sys.version_info >= (3, 8)
            },
            "packages": self._check_required_packages(),
            "adb": {
                "configured_path": self.configured_adb_path or "",
                "resolved_path": self.adb_path,
                "exists": os.path.exists(self.adb_path) if self.adb_path else False,
                "version": self.get_adb_version(),
                "is_ok": False
            },
            "emulator": {
                "mumu_installed": os.path.exists(MUMU_CLI) or os.path.exists(MUMU_ADB),
                "running_processes": self._detect_running_emulators()
            },
            "device": None,
            "app": {
                "package": package_name,
                "is_installed": False,
                "is_focused": False,
                "apk_path": ""
            },
            "status": "DISCONNECTED",
            "remediation": []
        }

        # Validate ADB
        report["adb"]["is_ok"] = bool(report["adb"]["version"])

        if not report["adb"]["is_ok"]:
            report["remediation"].append(
                "لم يتم العثور على أداة adb.exe صالحة. يرجى تثبيت Android SDK Platform-Tools أو تثبيت محاكي MuMu Player."
            )

        # Check devices
        try:
            dev = self.get_device()
            report["device"] = dev.to_dict()
            report["status"] = "CONNECTED"

            # Check app installation
            out, code = self._run_adb("-s", dev.serial, "shell", "pm", "path", package_name)
            if "package:" in out:
                report["app"]["is_installed"] = True
                report["app"]["apk_path"] = out.strip().replace("package:", "")

            # Check app focus
            out_win, _ = self._run_adb("-s", dev.serial, "shell", "dumpsys", "window", "windows")
            if package_name in out_win:
                report["app"]["is_focused"] = True

            if not report["app"]["is_installed"]:
                report["remediation"].append(
                    f"تطبيق نسك ({package_name}) غير مثبت على المحاكي. يرجى تثبيته من متجر Google Play داخل المحاكي."
                )

        except (NoDeviceError, DeviceOfflineError) as e:
            report["status"] = "OFFLINE"
            report["remediation"].append(str(e))
        except AdbNotFoundError as e:
            report["status"] = "NO_ADB"
            report["remediation"].append(str(e))
        except Exception as e:
            report["status"] = "ERROR"
            report["remediation"].append(f"خطأ أثناء فحص الجهاز: {e}")

        return report

    def _resolve_adb(self, explicit_path: Optional[str] = None) -> str:
        if explicit_path and (os.path.exists(explicit_path) or shutil.which(explicit_path)):
            return explicit_path

        # 1. Bundled platform-tools in project folder
        bundled_adb = os.path.join(os.path.dirname(__file__), "platform-tools", "adb.exe")
        if os.path.exists(bundled_adb):
            return bundled_adb

        # 2. Check system PATH
        in_path = shutil.which("adb")
        if in_path:
            return in_path

        # 3. Check candidate filesystem locations
        candidates = [
            MUMU_ADB,
            r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
            r"C:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe",
            r"C:\Program Files\Netease\MuMuPlayerGlobal\nx_device\15.0\shell\adb.exe",
            r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0\shell\adb.exe",
            r"C:\Program Files (x86)\MuMu\emulator\nexus\bin\adb.exe",
            r"C:\platform-tools\adb.exe",
            r"C:\tools\platform-tools\adb.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe"),
            os.path.join(os.environ.get("ANDROID_HOME", ""), "platform-tools", "adb.exe"),
            r"C:\LDPlayer\LDPlayer9\adb.exe",
            r"C:\Program Files\Nox\bin\nox_adb.exe",
            r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
            r"C:\Microvirt\MEmu\adb.exe",
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path

        raise AdbNotFoundError(
            "لم يتم العثور على adb.exe في المسار المحدد أو في PATH أو داخل مجلدات المحاكيات الشائعة."
        )

    def _assert_adb_exists(self):
        if not self.adb_path or not os.path.exists(self.adb_path) and not shutil.which(self.adb_path):
            self.adb_path = self._resolve_adb(self.configured_adb_path)

    def _start_adb_server(self):
        try:
            subprocess.run([self.adb_path, "start-server"], capture_output=True, timeout=5)
        except Exception:
            pass

    def _ensure_mumu_connected(self):
        # 1. Always attempt connecting to preferred serial (default 127.0.0.1:16384)
        target = self.preferred_serial or "127.0.0.1:16384"
        if self._adb_connect(target):
            return

        # 2. Fast check on MuMu 6 fallback port (7555)
        self._adb_connect("127.0.0.1:7555")

    def _adb_connect(self, serial: str) -> bool:
        try:
            res = subprocess.run([self.adb_path, "connect", serial],
                                 capture_output=True, text=True, timeout=1.0)
            return "connected" in res.stdout.lower() or "already" in res.stdout.lower()
        except Exception:
            return False

    def _list_adb_devices(self) -> List[Tuple[str, str]]:
        try:
            res = subprocess.run([self.adb_path, "devices"],
                                 capture_output=True, text=True, timeout=6)
            lines = res.stdout.strip().splitlines()
            result = []
            for line in lines[1:]:
                parts = line.strip().split()
                if len(parts) >= 2:
                    result.append((parts[0], parts[1]))
            return result
        except Exception:
            return []

    def _build_device_info(self, serial: str, state: str) -> DeviceInfo:
        if state != "device":
            raise DeviceOfflineError(f"الجهاز {serial} غير جاهز (الحالة: {state})")

        def prop(name: str) -> str:
            try:
                r = subprocess.run([self.adb_path, "-s", serial, "shell", "getprop", name],
                                   capture_output=True, text=True, timeout=4)
                return r.stdout.strip()
            except Exception:
                return ""

        # Query screen size
        screen_size = ""
        try:
            r = subprocess.run([self.adb_path, "-s", serial, "shell", "wm", "size"],
                               capture_output=True, text=True, timeout=4)
            for line in r.stdout.splitlines():
                if "size:" in line.lower():
                    screen_size = line.split(":")[-1].strip()
                    break
        except Exception:
            pass

        is_emu = ("emulator" in serial.lower() or "127.0.0.1" in serial or "localhost" in serial)
        mumu_idx = 0 if (is_emu and "16384" in serial) else None

        return DeviceInfo(
            serial=serial,
            adb_path=self.adb_path,
            android_version=prop("ro.build.version.release") or "unknown",
            sdk_version=prop("ro.build.version.sdk") or "0",
            model=prop("ro.product.model") or serial,
            is_emulator=is_emu,
            screen_size=screen_size,
            mumu_index=mumu_idx
        )

    def _run_adb(self, *args, timeout: float = 6.0) -> Tuple[str, int]:
        try:
            cmd = [self.adb_path] + list(args)
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return res.stdout + res.stderr, res.returncode
        except Exception as e:
            return str(e), -1

    def _check_required_packages(self) -> Dict[str, bool]:
        packages = ["requests", "openpyxl", "PIL", "appium"]
        results = {}
        for pkg in packages:
            try:
                __import__(pkg)
                results[pkg] = True
            except ImportError:
                results[pkg] = False
        return results

    def _detect_running_emulators(self) -> List[str]:
        running = []
        target_names = {
            "MuMuPlayer.exe": "MuMu Player",
            "NemuPlayer.exe": "MuMu Player 6",
            "dnplayer.exe": "LDPlayer",
            "Nox.exe": "Nox Player",
            "HD-Player.exe": "BlueStacks",
            "MEmu.exe": "MEmu"
        }
        try:
            res = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=4)
            for proc, label in target_names.items():
                if proc.lower() in res.stdout.lower():
                    running.append(label)
        except Exception:
            pass
        return running
