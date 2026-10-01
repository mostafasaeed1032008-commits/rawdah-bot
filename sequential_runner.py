# -*- coding: utf-8 -*-
"""
sequential_runner.py
====================
Sequential Orchestrator for Multi-Clone and Multi-Account Nusuk Automation.
Ensures single-instance execution, enforces safe stops on security challenges,
persists truthful progress, and handles offline states cleanly.
"""

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import time
import os
import json
from typing import List, Optional, Callable
from booking_plan import BookingSession, PassengerTask, BookingResult
from clone_manager import CloneManager
from nusuk_flows import FlowController, NusukScreenType
from device_manager import DeviceManager, NoDeviceError, DeviceOfflineError
from adb_controller import AdbController
from otp_fetcher import OtpFetcher
from ai_vision_agent import GeminiEmployeeAgent


class SequentialRunner:
    def __init__(self,
                 session: BookingSession,
                 config_dict: Optional[dict] = None,
                 log_callback: Optional[Callable[[str], None]] = None):
        self.session = session
        self.config = config_dict or {}
        self.log_cb = log_callback
        self.results: List[BookingResult] = []
        self.is_running = False
        self.results_path = os.path.join(os.path.dirname(__file__) or ".", "results.json")

        # Device & ADB
        self.dm = DeviceManager(adb_path=self.config.get("adb_path"),
                                preferred_serial=self.config.get("device_serial", "127.0.0.1:16384"))
        try:
            self.device = self.dm.get_device()
            dev_adb = self.device.adb_path
            dev_serial = self.device.serial
        except Exception:
            self.device = None
            dev_adb = self.dm.adb_path
            dev_serial = self.config.get("device_serial", "127.0.0.1:16384")

        self.adb = AdbController(adb_path=dev_adb,
                                 serial=dev_serial,
                                 package_name=self.config.get("nusuk_package", "com.moh.nusukapp"))

        self.clone_mgr = CloneManager(adb_path=dev_adb,
                                      serial=dev_serial,
                                      package=self.config.get("nusuk_package", "com.moh.nusukapp"))

        self.otp = OtpFetcher(self.config.get("gmail_user", ""),
                              self.config.get("gmail_app_password", ""))

        self.ai = GeminiEmployeeAgent(self.config.get("gemini_api_key", ""), self.adb)
        self.flow_ctrl = FlowController(self.adb, self.ai, self.otp)

    def log(self, msg: str):
        t = time.strftime("%H:%M:%S")
        entry = f"[{t}] {msg}"
        print(entry, flush=True)
        if self.log_cb:
            try:
                self.log_cb(entry)
            except Exception:
                pass

    def run(self) -> List[BookingResult]:
        """Runs the session sequentially. Safe offline exit if device unavailable."""
        self.is_running = True
        self.results = []

        if not self.adb.is_connected():
            self.log("❌ تعذر بدء التشغيل: لا يوجد محاكي أو جهاز متصل عبر ADB.")
            self.is_running = False
            return self.results

        clone_list = self.session.get_clone_list()
        passengers = self.session.passengers

        self.log(f"🚀 بدء تنفيذ خطة الحجز: '{self.session.session_name}'")
        self.log(f"📋 عدد المعتمرين: {len(passengers)} | نطاق النسخ: {clone_list[0]} إلى {clone_list[-1]} ({len(clone_list)} نسخة)")
        self.log("🔒 النظام: تنفيذ تسلسلي صارم (Sequential) - نسخة واحدة فقط في كل لحظة")

        # 1. Stop previously active clones
        self.clone_mgr.stop_all_clones()

        total = len(clone_list)
        for idx, clone_id in enumerate(clone_list):
            if not self.is_running:
                self.log("⛔ تم إيقاف التنفيذ بناءً على طلب المستخدم.")
                break

            passenger = None
            if idx < len(passengers):
                passenger = passengers[idx]
            elif passengers:
                passenger = passengers[idx % len(passengers)]
            else:
                passenger = PassengerTask(name=f"معتمر النسخة #{clone_id}", clone_id=clone_id)

            passenger.clone_id = clone_id

            self.log(f"\n▶ [{idx+1}/{total}] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.log(f"▶ تشغيل الـ Clone #{clone_id} للمعتمر: {passenger.name}")

            # 2. Launch clone
            self.clone_mgr.launch_clone(clone_id, wait_ready_sec=4.0)

            # 3. Process passenger flow
            res: Optional[BookingResult] = None
            for attempt in range(self.session.max_retries):
                try:
                    res = self.flow_ctrl.process_passenger_flow(passenger, self.session)

                    # Immediate safe stop if security challenge appears
                    if res.status == "SECURITY_CHALLENGE":
                        self.log(f"⚠️ توقف أمني في Clone #{clone_id}: تم رصد تحدٍ أمني يتطلب تدخلاً يدوياً.")
                        self.is_running = False
                        break

                    if res.status in ["SUCCESS", "ALREADY_BOOKED", "WAITING_LIST", "FULLY_BOOKED"]:
                        break
                    elif attempt < self.session.max_retries - 1:
                        self.log(f"🔄 إعادة محاولة Clone #{clone_id} (محاولة {attempt+2}/{self.session.max_retries})...")
                        time.sleep(2.0)
                except Exception as ex:
                    self.log(f"❌ خطأ أثناء معالجة Clone #{clone_id}: {ex}")
                    res = BookingResult(
                        clone_id=clone_id,
                        passenger_name=passenger.name,
                        status="ERROR",
                        error_reason=str(ex)
                    )

            if res is None:
                res = BookingResult(
                    clone_id=clone_id,
                    passenger_name=passenger.name,
                    status="FAILED",
                    error_reason="فشل دون التمكن من استكمال الخطوات"
                )

            self.results.append(res)
            self._save_results()

            status_icon = "✅" if res.status in ["SUCCESS", "ALREADY_BOOKED"] else ("📋" if res.status == "WAITING_LIST" else "❌")
            self.log(f"{status_icon} نتيجة Clone #{clone_id}: {res.status} | {res.permit_details or res.error_reason}")

            # If stopped due to security challenge, break whole batch
            if res.status == "SECURITY_CHALLENGE":
                break

            # 4. Stop current clone before next
            if self.session.close_clone_after_finish:
                self.clone_mgr.stop_clone(clone_id, delay_sec=0.5)

            # 5. Clean memory
            if self.session.clean_memory_between_clones:
                self.clone_mgr.clean_memory()

        self.is_running = False
        self._print_summary_report()
        return self.results

    def _save_results(self):
        try:
            with open(self.results_path, "w", encoding="utf-8") as f:
                json.dump({
                    "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "total_results": len(self.results),
                    "results": [r.to_dict() for r in self.results]
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _print_summary_report(self):
        self.log("\n" + "=" * 60)
        self.log("  📊 تقرير نتائج جلسة الحجز")
        self.log("=" * 60)
        success_count = sum(1 for r in self.results if r.status in ["SUCCESS", "ALREADY_BOOKED"])
        waiting_count = sum(1 for r in self.results if r.status == "WAITING_LIST")
        sec_count = sum(1 for r in self.results if r.status == "SECURITY_CHALLENGE")
        self.log(f"  إجمالي النسخ المنفذة: {len(self.results)}")
        self.log(f"  ✅ تم الحجز بنجاح: {success_count}")
        self.log(f"  📋 قائمة الانتظار: {waiting_count}")
        if sec_count > 0:
            self.log(f"  ⚠️ توقف أمني (CAPTCHA/Challenge): {sec_count}")
        self.log(f"  ❌ فشل أو ممتلئ: {len(self.results) - success_count - waiting_count}")
        self.log("-" * 60)
        for r in self.results:
            icon = "✅" if r.status in ["SUCCESS", "ALREADY_BOOKED"] else ("📋" if r.status == "WAITING_LIST" else "❌")
            self.log(f"  {icon} Clone #{r.clone_id:02d} | {r.passenger_name} -> {r.status} ({r.permit_details or r.error_reason})")
        self.log("=" * 60 + "\n")
