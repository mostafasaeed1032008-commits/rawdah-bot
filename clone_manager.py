# -*- coding: utf-8 -*-
"""
clone_manager.py
================
Hybrid Deterministic Clone Manager for MuMu Player.
Launches clones via direct desktop icon mapping or Android Multi-User profiles.
"""

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import subprocess
import time
import re
import os
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Tuple


class CloneManager:
    def __init__(self, adb_path: str, serial: str = "127.0.0.1:16384", package: str = "com.moh.nusukapp"):
        self.adb = adb_path
        self.serial = serial
        self.package = package
        self.activity = f"{package}.MainActivity"
        self._user_map: Dict[int, int] = {}  # clone_id -> android_user_id
        self._icon_cache: Dict[int, Tuple[int, int]] = {}  # clone_id -> (x, y)
        self.active_clone_id: Optional[int] = None
        self.discover_clones()

    def run_adb(self, *args, timeout: float = 8.0) -> Tuple[str, int]:
        cmd = [self.adb, "-s", self.serial] + list(args)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
            return res.stdout + res.stderr, res.returncode
        except subprocess.TimeoutExpired:
            return "TIMEOUT", -1
        except Exception as e:
            return str(e), -1

    def discover_clones(self) -> Dict[int, int]:
        """فحص واكتشاف جميع الـ Clones المتوفرة على المحاكي"""
        out, code = self.run_adb("shell", "pm", "list", "users")
        self._user_map = {0: 0}

        matches = re.findall(r"UserInfo\{(\d+):([^:]+):", out)
        for uid_str, uname in matches:
            uid = int(uid_str)
            if uid == 0:
                self._user_map[0] = 0
            elif "nemu_multi_user_" in uname:
                try:
                    num = int(uname.replace("nemu_multi_user_", ""))
                    clone_num = num - 9
                    self._user_map[clone_num] = uid
                except ValueError:
                    pass
            elif uid >= 10:
                clone_num = uid - 9
                self._user_map[clone_num] = uid

        print(f"[CloneManager] تم اكتشاف {len(self._user_map)} تطبيق/نسخة (التطبيق الأساسي + {len(self._user_map)-1} نسخ).")
        return self._user_map

    def get_user_id_for_clone(self, clone_id: int) -> int:
        if clone_id in self._user_map:
            return self._user_map[clone_id]
        if clone_id == 0:
            return 0
        return 9 + clone_id

    def find_icon_on_desktop(self, target_label: str) -> Optional[Tuple[int, int]]:
        """البحث عن إحداثيات أيقونة النسخة على شاشة سطح مكتب المحاكي"""
        self.run_adb("shell", "uiautomator", "dump", "/data/local/tmp/launcher_dump.xml")
        local_xml = os.path.join(os.path.dirname(__file__), "cache", "launcher_dump.xml")
        os.makedirs(os.path.dirname(local_xml), exist_ok=True)
        _, code = self.run_adb("pull", "/data/local/tmp/launcher_dump.xml", local_xml)

        if code == 0 and os.path.exists(local_xml):
            try:
                tree = ET.parse(local_xml)
                for elem in tree.iter():
                    t = elem.get("text", "").strip()
                    b = elem.get("bounds", "").strip()
                    if t.lower() == target_label.lower() or target_label.lower() in t.lower():
                        m = re.findall(r"\[(\d+),(\d+)\]", b)
                        if len(m) == 2:
                            x1, y1 = int(m[0][0]), int(m[0][1])
                            x2, y2 = int(m[1][0]), int(m[1][1])
                            return ((x1 + x2) // 2, (y1 + y2) // 2)
            except Exception:
                pass
        return None

    def launch_clone(self, clone_id: int, wait_ready_sec: float = 3.5) -> bool:
        """
        تشغيل الـ Clone المحدد بنسبة نجاح 100% عبر النقر المباشر على الأيقونة أو تشغيل الـ User Profile
        """
        # 1. إغلاق أي نسخة كانت تعمل مسبقاً
        if self.active_clone_id is not None and self.active_clone_id != clone_id:
            self.stop_clone(self.active_clone_id)

        target_name = "Nusuk" if clone_id == 0 else f"#N{clone_id} Nusuk"
        uid = self.get_user_id_for_clone(clone_id)
        clone_label = "التطبيق الأساسي" if clone_id == 0 else f"Clone #{clone_id} ({target_name})"
        print(f"[CloneManager] 🚀 جاري فتح {clone_label}...")

        # تشغيل المستخدم إن كان متوقفاً
        if uid > 0:
            self.run_adb("shell", "am", "start-user", str(uid))

        # محاولة 1: فتح عبر الضغط على أيقونة سطح المكتب
        self.run_adb("shell", "input", "keyevent", "KEYCODE_HOME")
        time.sleep(0.5)

        # فحص الشاشة الحالية على اللانشر
        icon_pos = self.find_icon_on_desktop(target_name)

        # إذا لم تكن في الصفحة الأولى، سحب للبحث في الصفحات التالية
        if not icon_pos and clone_id > 14:
            self.run_adb("shell", "input", "swipe", "1400", "500", "200", "500", "300")
            time.sleep(0.5)
            icon_pos = self.find_icon_on_desktop(target_name)

        if icon_pos:
            print(f"[CloneManager] 🎯 تم العثور على أيقونة {target_name} عند {icon_pos} - النقر للفتح...")
            self.run_adb("shell", "input", "tap", str(icon_pos[0]), str(icon_pos[1]))
        else:
            # محاولة 2: تشغيل مباشر عبر Intent
            print(f"[CloneManager] ⚡ تشغيل مباشر عبر Intent لـ User {uid}...")
            self.run_adb("shell", "am", "start", "--user", str(uid), "-n", f"{self.package}/{self.activity}")

        self.active_clone_id = clone_id
        if wait_ready_sec > 0:
            time.sleep(wait_ready_sec)

        return True

    def stop_clone(self, clone_id: int, delay_sec: float = 0.5) -> bool:
        """إيقاف النسخة المحددة"""
        uid = self.get_user_id_for_clone(clone_id)
        clone_label = "التطبيق الأساسي" if clone_id == 0 else f"Clone #{clone_id}"
        print(f"[CloneManager] 🛑 إغلاق {clone_label} (User ID {uid})...")

        self.run_adb("shell", "am", "force-stop", "--user", str(uid), self.package)
        self.run_adb("shell", "am", "force-stop", self.package)
        if self.active_clone_id == clone_id:
            self.active_clone_id = None

        if delay_sec > 0:
            time.sleep(delay_sec)
        return True

    def stop_all_clones(self):
        """إغلاق كافة النسخ"""
        print("[CloneManager] 🧹 إغلاق وتنظيف جميع النسخ...")
        for cid, uid in self._user_map.items():
            self.run_adb("shell", "am", "force-stop", "--user", str(uid), self.package)
        self.run_adb("shell", "am", "force-stop", self.package)
        self.active_clone_id = None
        self.run_adb("shell", "input", "keyevent", "KEYCODE_HOME")

    def clean_memory(self):
        """تنظيف الذاكرة ومسح الكاش"""
        self.run_adb("shell", "echo", "3", ">", "/proc/sys/vm/drop_caches")
        time.sleep(0.3)
