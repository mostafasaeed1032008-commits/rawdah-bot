# -*- coding: utf-8 -*-
"""
appium_controller.py
====================
Appium session manager for NusukBot PC.

Error hierarchy:
  AppiumNotRunningError -> server not running and could not start
  AppiumSessionError    -> session creation failed

Falls back gracefully: if Appium is unavailable or fails to connect,
is_connected returns False and callers (AdbController / NusukEngine)
fall back to direct ADB commands.
"""

import os
import socket
import subprocess
import sys
import time
from typing import Optional

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from appium import webdriver as appium_webdriver
    from appium.options.android import UiAutomator2Options
    APPIUM_AVAILABLE = True
except ImportError:
    APPIUM_AVAILABLE = False

from device_manager import DeviceManager, DeviceInfo, AdbNotFoundError, NoDeviceError, DeviceOfflineError

NODE_EXE = r"C:\Program Files\nodejs\node.exe"
APPIUM_PORT = 4723
NUSUK_PACKAGE = "com.moh.nusukapp"
NUSUK_ACTIVITY = "com.moh.nusukapp.MainActivity"


class AppiumNotRunningError(RuntimeError):
    pass


class AppiumSessionError(RuntimeError):
    pass


class AppiumController:
    """
    Manages the full Appium lifecycle for NusukBot.

    Usage
    -----
    ctrl = AppiumController()
    ctrl.connect()                  # discover device -> start Appium -> create session
    ctrl.tap(x, y)
    el = ctrl.find_element(text="Rawdah")
    el.click()
    ctrl.disconnect()
    """

    def __init__(self,
                 adb_path: Optional[str] = None,
                 preferred_serial: Optional[str] = None,
                 appium_host: str = "127.0.0.1",
                 appium_port: int = APPIUM_PORT,
                 package: str = NUSUK_PACKAGE,
                 activity: str = NUSUK_ACTIVITY):
        self.dm = DeviceManager(adb_path=adb_path, preferred_serial=preferred_serial)
        self.appium_host = appium_host
        self.appium_port = appium_port
        self.package = package
        self.activity = activity
        self.device: Optional[DeviceInfo] = None
        self.driver = None
        self._server_proc = None
        self._connected = False

    # ── Main API ──────────────────────────────────────────────────────────────
    def connect(self, auto_start_server: bool = True) -> bool:
        """Discovers device, verifies Appium server, and creates WebDriver session."""
        # 1. Discover device
        try:
            self.device = self.dm.get_device()
            print(f"[Appium] تم اكتشاف الجهاز: {self.device.serial} "
                  f"(Android {self.device.android_version} - SDK {self.device.sdk_version})")
        except (AdbNotFoundError, NoDeviceError, DeviceOfflineError):
            raise

        if not APPIUM_AVAILABLE:
            print("[Appium] مكتبة Appium-Python-Client غير مثبتة. يرجى تثبيتها: pip install Appium-Python-Client")
            return False

        # 2. Start Appium Server if not running
        if auto_start_server and not self._is_appium_running():
            self._start_appium_server()

        if not self._is_appium_running():
            raise AppiumNotRunningError(
                f"خادم Appium لا يعمل على المنفذ {self.appium_port}.\n"
                f"يمكن تشغيله يدوياً عبر: appium --port {self.appium_port}"
            )

        # 3. Create Session with UiAutomator2Options
        try:
            self._create_session()
            self._connected = True
            print(f"[Appium] تم إنشاء جلسة Appium بنجاح للجهاز: {self.device.serial}")
            return True
        except Exception as exc:
            self._connected = False
            raise AppiumSessionError(f"فشل إنشاء جلسة Appium WebDriver: {exc}") from exc

    def disconnect(self):
        """Closes the current Appium WebDriver session."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        self._connected = False
        print("[Appium] تم إغلاق جلسة Appium.")

    def stop_server(self):
        """Stops the local Appium server process if started by this instance."""
        if self._server_proc and self._server_proc.poll() is None:
            self._server_proc.terminate()
            self._server_proc = None
            print("[Appium] تم إيقاف خادم Appium.")

    @property
    def is_connected(self) -> bool:
        return self._connected and self.driver is not None

    # ── Interactions ──────────────────────────────────────────────────────────
    def tap(self, x: int, y: int):
        if not self.is_connected:
            raise RuntimeError("جلسة Appium غير نشطة")
        try:
            self.driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
        except Exception:
            # Fallback: W3C tap script
            try:
                from appium.webdriver.common.appiumby import AppiumBy
                self.driver.tap([(x, y)])
            except Exception:
                pass

    def find_element(self, text: str = "", res_id: str = "", xpath: str = ""):
        if not self.is_connected:
            return None
        try:
            from appium.webdriver.common.appiumby import AppiumBy
            if res_id:
                return self.driver.find_element(AppiumBy.ID, res_id)
            if xpath:
                return self.driver.find_element(AppiumBy.XPATH, xpath)
            if text:
                return self.driver.find_element(
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    f'new UiSelector().text("{text}")'
                )
        except Exception:
            return None

    def find_and_tap(self, text: str) -> bool:
        el = self.find_element(text=text)
        if el:
            try:
                el.click()
                return True
            except Exception:
                pass
        return False

    def type_text(self, text: str):
        if not self.is_connected:
            return
        try:
            self.driver.switch_to.active_element.send_keys(text)
        except Exception:
            pass

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        if not self.is_connected:
            return
        try:
            self.driver.swipe(x1, y1, x2, y2, duration_ms)
        except Exception:
            pass

    def get_page_source(self) -> str:
        if not self.is_connected:
            return ""
        try:
            return self.driver.page_source
        except Exception:
            return ""

    def screenshot_base64(self) -> str:
        if not self.is_connected:
            return ""
        try:
            return self.driver.get_screenshot_as_base64()
        except Exception:
            return ""

    def launch_app(self):
        if not self.is_connected:
            return
        try:
            self.driver.activate_app(self.package)
        except Exception:
            pass

    def press_back(self):
        if not self.is_connected:
            return
        try:
            self.driver.press_keycode(4)
        except Exception:
            pass

    # ── Capabilities ─────────────────────────────────────────────────────────
    def _create_session(self):
        if not self.device:
            raise AppiumSessionError("لم يتم اكتشاف جهاز متصل.")

        opts = UiAutomator2Options()
        opts.platform_name = "Android"
        opts.device_name = self.device.model
        opts.udid = self.device.serial
        opts.platform_version = self.device.android_version
        opts.app_package = self.package
        opts.app_activity = self.activity
        opts.no_reset = True
        opts.full_reset = False
        opts.auto_grant_permissions = True
        opts.new_command_timeout = 120
        opts.adb_exec_timeout = 20000
        opts.set_capability("appium:adbPath", self.device.adb_path)

        url = f"http://{self.appium_host}:{self.appium_port}"
        self.driver = appium_webdriver.Remote(url, options=opts)

    # ── Server management ─────────────────────────────────────────────────────
    def _is_appium_running(self) -> bool:
        try:
            with socket.create_connection((self.appium_host, self.appium_port), timeout=2):
                return True
        except (ConnectionRefusedError, OSError):
            return False

    def _start_appium_server(self, wait_seconds: float = 12.0):
        candidates = [
            os.path.join(os.environ.get("APPDATA", ""), "npm", "appium.cmd"),
            r"C:\Users\Aljazeera\AppData\Roaming\npm\appium.cmd",
            "appium.cmd",
            "appium"
        ]
        appium_bin = next((p for p in candidates if os.path.exists(p)), None)
        if not appium_bin:
            print("[Appium] appium.cmd غير موجود في المسارات المعروفة.")
            return

        print(f"[Appium] جاري تشغيل خادم Appium على المنفذ {self.appium_port}...")
        env = os.environ.copy()
        env["PATH"] = r"C:\Program Files\nodejs;" + env.get("PATH", "")

        self._server_proc = subprocess.Popen(
            [appium_bin, "--port", str(self.appium_port),
             "--relaxed-security", "--log-level", "warn"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if self._is_appium_running():
                print(f"[Appium] خادم Appium جاهز ويعمل على المنفذ {self.appium_port}!")
                return
            time.sleep(0.5)
        print("[Appium] لم يبدأ خادم Appium خلال الوقت المحدد.")

    def __repr__(self) -> str:
        status = "متصل" if self.is_connected else "غير متصل"
        device = self.device.serial if self.device else "لا يوجد"
        return f"AppiumController(device='{device}', status='{status}')"
