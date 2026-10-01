# -*- coding: utf-8 -*-
"""
nusuk_engine.py
===============
NusukBot PC Automation & Regression Testing Engine.
Orchestrates fast ADB actions, device discovery, UI state tracking, results logging,
and Gemini AI vision fallback.
"""

import json
import os
import threading
import time
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Callable, Tuple

from device_manager import (
    DeviceManager, DeviceInfo,
    AdbNotFoundError, NoDeviceError, DeviceOfflineError
)
from appium_controller import (
    AppiumController,
    AppiumNotRunningError, AppiumSessionError, APPIUM_AVAILABLE
)
from adb_controller import AdbController
from otp_fetcher import OtpFetcher
from ai_vision_agent import GeminiEmployeeAgent
from excel_manager import Passenger, ExcelManager
from nusuk_flows import FlowController, NusukScreenType
from booking_plan import BookingSession, PassengerTask, BookingResult
from nusuk_api_client import NusukApiClient, NusukServiceId


class BotState(Enum):
    STOPPED = "متوقف"
    DISCONNECTED = "غير متصل بالمحاكي"
    CONNECTING = "جاري الاتصال بالمحاكي"
    READY = "جاهز للعمل"
    RUNNING = "جاري الحجز والتنفيذ"
    WAITING_OTP = "في انتظار كود التحقق OTP"
    SNIPING_SLOTS = "فحص المواعيد المتاحة 🎯"
    CONFIRMING = "جاري تأكيد التصريح"
    FULLY_BOOKED = "المواعيد ممتلئة"
    WAITING_LIST = "تم التسجيل في قائمة الانتظار"
    SECURITY_CHALLENGE = "توقف أمني: مطلوب تدخل يدوي ⚠️"
    PAUSED = "مؤقت"
    COMPLETED = "تم الانتهاء"
    ERROR = "حدث خطأ"


class NusukEngine:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self.results_path = os.path.join(os.path.dirname(__file__) or ".", "results.json")

        # 1. Device discovery layer
        self.dm = DeviceManager(
            adb_path=self.config.get("adb_path"),
            preferred_serial=self.config.get("device_serial", "127.0.0.1:16384")
        )
        self.device_info: Optional[DeviceInfo] = None

        # 2. Appium layer
        self.appium_ctrl = AppiumController(
            adb_path=self.config.get("adb_path"),
            preferred_serial=self.config.get("device_serial", "127.0.0.1:16384"),
            package=self.config.get("nusuk_package", "com.moh.nusukapp")
        )

        # 3. ADB controller
        self.adb = AdbController(
            adb_path=self.config.get("adb_path", ""),
            serial=self.config.get("device_serial", "127.0.0.1:16384"),
            package_name=self.config.get("nusuk_package", "com.moh.nusukapp"),
            appium_ctrl=self.appium_ctrl
        )

        # 4. OTP and AI modules
        self.otp_fetcher = OtpFetcher(
            self.config.get("gmail_user", ""),
            self.config.get("gmail_app_password", "")
        )
        self.ai_agent = GeminiEmployeeAgent(
            self.config.get("gemini_api_key", ""),
            self.adb
        )

        # 5. Flow Controller
        self.flow_ctrl = FlowController(self.adb, self.ai_agent, self.otp_fetcher, log_fn=self.log)

        self.passengers: List[Passenger] = []
        self.current_index = 0
        self.state = BotState.DISCONNECTED
        self.is_running = False
        self._run_lock = threading.Lock()
        self.logs: List[str] = []
        self.log_callbacks: List[Callable[[str], None]] = []
        self.driver_mode = "adb"
        self.last_error = ""

        # Engine Mode: 'api' (Direct REST API, RawdahPass style) or 'adb' (Emulator)
        self.engine_mode = self.config.get("engine_mode", "api")
        self.api_client = NusukApiClient(impersonate="chrome124", language="ar")

        # Auto discover device on startup
        self._init_device_connection()
        if self.engine_mode == "api":
            self.state = BotState.READY
            self.log("⚡ تم تفعيل محرك الـ REST API المباشر (أسلوب RawdahPass). جاهز للعمل فوراً.")

        # Load local passengers if configured or available
        self._load_initial_passengers()

    def _init_device_connection(self):
        """Discovers device without crashing if offline."""
        try:
            self.device_info = self.dm.get_device()
            self.adb.serial = self.device_info.serial
            self.adb.adb = self.device_info.adb_path
            self.state = BotState.READY
            self.last_error = ""
            self.log(f"📱 تم الاتصال بالجهاز: {self.device_info.serial} "
                     f"({self.device_info.model} - Android {self.device_info.android_version})")

            if self.config.get("use_appium", False) and APPIUM_AVAILABLE:
                try:
                    if self.appium_ctrl.connect(auto_start_server=True):
                        self.driver_mode = "appium"
                        self.log("🚀 تم تفعيل طبقة Appium بنجاح.")
                except Exception:
                    self.driver_mode = "adb"
            else:
                self.driver_mode = "adb"
        except (NoDeviceError, DeviceOfflineError) as e:
            self.state = BotState.DISCONNECTED
            self.last_error = str(e)
        except AdbNotFoundError as e:
            self.state = BotState.DISCONNECTED
            self.last_error = str(e)
        except Exception as e:
            self.state = BotState.DISCONNECTED
            self.last_error = str(e)

    def _load_initial_passengers(self):
        excel_path = self.config.get("default_excel_path")
        if excel_path and os.path.exists(excel_path):
            try:
                self.passengers = ExcelManager.parse_file(excel_path, self.config.get("link_children", True))
                self.log(f"📊 تم استيراد {len(self.passengers)} معتمر من {os.path.basename(excel_path)}")
            except Exception as e:
                self.log(f"⚠ تعذر قراءة ملف البيانات: {e}")
        elif os.path.exists("sample_passengers.csv"):
            try:
                self.passengers = ExcelManager.parse_file("sample_passengers.csv", self.config.get("link_children", True))
            except Exception:
                pass

    def _load_config(self) -> Dict[str, Any]:
        config: Dict[str, Any] = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (OSError, ValueError):
                config = {}

        # Environment variable overrides
        env_map = {
            "adb_path": "NUSUK_ADB_PATH",
            "device_serial": "NUSUK_DEVICE_SERIAL",
            "nusuk_package": "NUSUK_PACKAGE",
            "gmail_user": "NUSUK_GMAIL_USER",
            "gmail_app_password": "NUSUK_GMAIL_APP_PASSWORD",
            "gemini_api_key": "NUSUK_GEMINI_API_KEY",
            "default_excel_path": "NUSUK_EXCEL_PATH",
            "unified_password": "NUSUK_UNIFIED_PASSWORD",
        }
        for key, env_name in env_map.items():
            val = os.environ.get(env_name)
            if val:
                config[key] = val
        return config

    def public_config(self) -> Dict[str, Any]:
        """Returns safe configuration strictly masking all secrets."""
        secret_keys = {"gmail_app_password", "gemini_api_key", "unified_password"}
        safe_copy = {}
        for k, v in self.config.items():
            if k in secret_keys:
                safe_copy[k] = "••••••••" if v else ""
            else:
                safe_copy[k] = v
        return safe_copy

    def save_config(self, new_config: Dict[str, Any]):
        allowed = {
            "engine_mode", "adb_path", "device_serial", "nusuk_package", "target_date",
            "target_period", "time_from", "time_to", "max_fallback_days",
            "auto_sniper_interval_ms", "link_children", "server_port",
            "default_excel_path", "gmail_user", "gmail_app_password",
            "gemini_api_key", "unified_password",
        }
        secret_keys = {"gmail_app_password", "gemini_api_key", "unified_password"}

        for k, v in new_config.items():
            if k in allowed:
                # Do not overwrite existing secrets if submitted with blank or masked placeholder
                if k in secret_keys and (not str(v).strip() or "••••" in str(v)):
                    continue
                self.config[k] = v

        if "engine_mode" in self.config:
            self.engine_mode = self.config["engine_mode"]

        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"⚠ تعذر حفظ الإعدادات على القرص: {e}")

        # Update live components
        if "adb_path" in self.config:
            self.adb.adb = self.config["adb_path"]
        if "device_serial" in self.config:
            self.adb.serial = self.config["device_serial"]
        self.otp_fetcher.user = self.config.get("gmail_user", "")
        self.otp_fetcher.password = self.config.get("gmail_app_password", "").replace(" ", "")
        self.ai_agent.set_api_key(self.config.get("gemini_api_key", ""))

    def log(self, message: str):
        t = datetime.now().strftime("%H:%M:%S")
        entry = f"[{t}] {message}"
        self.logs.append(entry)
        if len(self.logs) > 300:
            self.logs.pop(0)
        print(entry)
        for cb in self.log_callbacks:
            try:
                cb(entry)
            except Exception:
                pass

    def reset_passengers_status(self):
        """Resets all passengers' booking status to Pending."""
        for p in self.passengers:
            p.booking_status = "⏳ قيد الانتظار"
            p.note = ""
        self.log("🔄 تم إعادة تعيين حالة جميع المعتمرين إلى قيد الانتظار.")

    def start_booking(self, auto_reset: bool = True) -> Tuple[bool, str]:
        with self._run_lock:
            if self.is_running:
                return False, "جلسة الأتمتة قيد التشغيل بالفعل"
            if auto_reset:
                pending = [p for p in self.passengers if not ("تم" in p.booking_status or "مؤكد" in p.booking_status)]
                if not pending and self.passengers:
                    self.reset_passengers_status()
            self.is_running = True

        t = threading.Thread(target=self._booking_worker, daemon=True)
        t.start()
        return True, "تم بدء التشغيل"

    def stop_booking(self):
        self.is_running = False
        self.state = BotState.STOPPED
        self.log("⛔ تم إيقاف البوت بأمان.")

    def _booking_worker(self):
        if self.engine_mode == "api":
            self._booking_worker_api()
        else:
            self._booking_worker_adb()

    def _booking_worker_api(self):
        self.log("⚡ بدء جلسة الحجز المباشر عبر محرك REST API (أسلوب RawdahPass)...")
        self.state = BotState.RUNNING

        pending = [p for p in self.passengers if not ("تم" in p.booking_status or "مؤكد" in p.booking_status)]
        if not pending:
            self.log("ℹ لا توجد حسابات معلقة للحجز.")
            self.state = BotState.COMPLETED
            self.is_running = False
            return

        target_date = self.config.get("target_date", "")
        now = datetime.now()
        target_month = now.month
        target_year = now.year
        if target_date:
            try:
                parts = target_date.replace("-", "/").split("/")
                if len(parts) >= 2:
                    if len(parts[0]) == 4:
                        target_year = int(parts[0])
                        target_month = int(parts[1])
                    else:
                        target_month = int(parts[0])
                        target_year = int(parts[1])
            except Exception:
                pass

        results = []
        for idx, p in enumerate(pending):
            if not self.is_running:
                self.log("⛔ تم التوقف بناءً على طلب المستخدم.")
                break

            self.current_index = idx
            self.log(f"▶ معالجة المعتمر [{idx+1}/{len(pending)}]: {p.name} (جواز: {p.passport_no})")

            # 1. Determine service ID: Women = 21, Men = 20
            is_women = "نساء" in (p.person_type or "") or "أنثى" in (p.person_type or "")
            service_id = NusukServiceId.RAWDAH_WOMEN if is_women else NusukServiceId.RAWDAH_MEN
            gender_str = "نساء" if is_women else "رجال"
            self.log(f"👤 الفئة المستهدفة: {gender_str} (Service ID: {service_id})")

            # 2. Login
            dry_run = self.config.get("dry_run", False) or self.config.get("simulation_mode", False)
            password = self.config.get("unified_password", "Zxcv1234$")
            client = NusukApiClient(impersonate="chrome124", mock_mode=dry_run)

            login_res = client.login_visitor(
                nationality_id=20,  # Egypt
                passport_no=p.passport_no,
                password=password
            )

            if login_res.get("needs_otp"):
                self.state = BotState.WAITING_OTP
                self.log(f"🔑 مطلوب كود التحقق OTP لحساب {p.name}. جاري الفحص عبر Gmail...")

                if dry_run:
                    otp_code = "1234"
                    self.log(f"🧪 [وضع المحاكاة] تم إدخال كود OTP تجريبي تلقائياً: {otp_code}")
                else:
                    otp_code = self.otp_fetcher.fetch_latest_otp(timeout=25)

                if not otp_code:
                    self.log(f"❌ انتهت مهلة انتظار كود التحقق OTP لحساب {p.name}.")
                    p.booking_status = "❌ تعذر استلام OTP"
                    p.note = "Timeout waiting for OTP email"
                    results.append({"name": p.name, "status": "FAILED", "reason": "OTP Timeout"})
                    self._save_results(results)
                    continue

                self.log(f"⚡ تم سحب كود التحقق بنجاح: {otp_code}. جاري تأكيد تسجيل الدخول...")
                verify_res = client.verify_otp(otp_code=otp_code)
                if not verify_res.get("success"):
                    self.log(f"❌ فشل تأكيد كود OTP: {verify_res.get('message')}")
                    p.booking_status = "❌ فشل تأكيد OTP"
                    p.note = verify_res.get('message', '')
                    results.append({"name": p.name, "status": "FAILED", "reason": p.note})
                    self._save_results(results)
                    continue

                self.log(f"✅ تم تسجيل الدخول والحصول على رمز التوثيق بنجاح للمعتمر: {p.name}")
            elif not login_res.get("success"):
                err_code = login_res.get("code")
                # إذا فشل التحقق من البيانات وكان لدينا تاريخ الميلاد: تنفيذ استرجاع الحساب تلقائياً
                if err_code == 1010106003 and getattr(p, "dob", "") and p.dob.strip():
                    self.log(f"🔄 الحساب غير مفعل أو مرتبط بحساب سابق. بدء استرجاع الحساب للمعتمر {p.name} (جواز: {p.passport_no})...")
                    rec_res = client.recover_account_visitor(
                        passport_no=p.passport_no,
                        nationality_id=20,
                        dob=p.dob,
                        new_email=p.email,
                        new_password=password
                    )
                    if rec_res.get("needs_otp"):
                        self.log(f"🔑 تم إرسال كود استرجاع الحساب إلى {p.email}. جاري السحب من Gmail...")
                        rec_otp = self.otp_fetcher.fetch_latest_otp(timeout=30) if not dry_run else "1234"
                        if rec_otp:
                            rec_verify = client.verify_recover_account_visitor(
                                passport_no=p.passport_no,
                                nationality_id=20,
                                dob=p.dob,
                                new_email=p.email,
                                new_password=password,
                                otp_code=rec_otp
                            )
                            if rec_verify.get("success"):
                                self.log(f"✅ تم استرجاع وربط الحساب بنجاح! جاري تسجيل الدخول الآن...")
                                login_res = client.login_visitor(nationality_id=20, passport_no=p.passport_no, password=password)
                                if login_res.get("needs_otp"):
                                    l_otp = self.otp_fetcher.fetch_latest_otp(timeout=25) if not dry_run else "1234"
                                    if l_otp and client.verify_otp(otp_code=l_otp).get("success"):
                                        self.log(f"✅ تم تسجيل الدخول بعد الاسترجاع بنجاح للمعتمر: {p.name}")
                                    else:
                                        p.booking_status = "❌ فشل OTP الدخول"
                                        continue
                            else:
                                self.log(f"❌ فشل تأكيد كود الاسترجاع: {rec_verify.get('message')}")
                                p.booking_status = "❌ فشل استرجاع الحساب"
                                continue
                        else:
                            self.log(f"❌ انتهت مهلة كود OTP للاسترجاع.")
                            p.booking_status = "❌ تعذر استلام OTP"
                            continue
                    else:
                        err_msg = rec_res.get("message") or f"Code {rec_res.get('code')}"
                        self.log(f"⚠ تعذر بدء استرجاع الحساب: {err_msg}")
                        p.booking_status = f"❌ {err_msg}"
                        p.note = err_msg
                        results.append({"name": p.name, "status": "FAILED", "reason": err_msg})
                        self._save_results(results)
                        continue
                else:
                    err_msg = login_res.get("message") or f"Code {login_res.get('code')}"
                    self.log(f"⚠ تعذر تسجيل الدخول للمعتمر {p.name}: {err_msg}")
                    p.booking_status = f"❌ {err_msg}"
                    p.note = err_msg
                    results.append({"name": p.name, "status": "FAILED", "reason": err_msg})
                    self._save_results(results)
                    continue

            # 3. Query available slots
            self.state = BotState.SNIPING_SLOTS
            self.log(f"🎯 فحص المواعيد المتاحة لشهر {target_month}/{target_year}...")
            slots_res = client.get_available_slots(month=target_month, year=target_year, service_id=service_id)

            if not slots_res.get("success"):
                self.log(f"⚠ تعذر استعلام المواعيد: {slots_res.get('message')}")
                p.booking_status = "⏳ تعذر استعلام المواعيد"
                p.note = slots_res.get("message", "")
                results.append({"name": p.name, "status": "FAILED", "reason": p.note})
                self._save_results(results)
                continue

            avail_dates = slots_res.get("available_dates", [])
            chosen_slot_id = None
            chosen_date_str = ""

            for ad in avail_dates:
                date_val = ad.get("Date", "")
                slots = ad.get("Timeslots", [])
                if slots:
                    chosen_slot_id = slots[0].get("TimeslotID")
                    chosen_date_str = date_val
                    break

            if not chosen_slot_id:
                self.log(f"⏳ لا توجد مواعيد شاغرة حالياً لشهر {target_month}/{target_year} ({gender_str}).")
                p.booking_status = "⏳ المواعيد ممتلئة"
                p.note = "No slots available in target month"
                results.append({"name": p.name, "status": "FULLY_BOOKED", "reason": p.note})
                self._save_results(results)
                continue

            # 4. Issue permit
            self.state = BotState.CONFIRMING
            self.log(f"⚡ حجز الموعد الفوري للمعتمر {p.name}: التاريخ {chosen_date_str}, كود الموعد {chosen_slot_id}...")
            permit_res = client.issue_permit_visitor(service_id=service_id, timeslot_id=chosen_slot_id)

            if permit_res.get("success"):
                p.booking_status = "✅ تم الحجز بنجاح"
                p.booking_date = chosen_date_str
                p.booking_slot = str(chosen_slot_id)
                permit_info = permit_res.get("permit_data") or permit_res.get("response", {})
                p.note = f"Permit: {permit_info}"
                self.log(f"🎉 تم إصدار تصريح الروضة بنجاح للمعتمر {p.name}!")
                results.append({"name": p.name, "status": "SUCCESS", "date": chosen_date_str, "slot": chosen_slot_id, "permit": permit_info})
            else:
                p.booking_status = "❌ فشل إصدار التصريح"
                p.note = permit_res.get("message", "")
                self.log(f"❌ تعذر إصدار التصريح: {p.note}")
                results.append({"name": p.name, "status": "FAILED", "reason": p.note})

            self._save_results(results)

        self.is_running = False
        self.state = BotState.COMPLETED
        try:
            ExcelManager.export_permits(self.passengers, "Nusuk_Permits_Export.xlsx")
            self.log("📊 تم تصدير جميع التصاريح والبيانات إلى: Nusuk_Permits_Export.xlsx")
        except Exception as e:
            self.log(f"⚠ تعذر تصدير الإكسيل تلقائياً: {e}")
        self.log("🏁 اكتملت جلسة المعالجة.")

    def _booking_worker_adb(self):
        self.log("🚀 بدء جلسة الفحص والأتمتة عبر محاكي ADB...")
        self.state = BotState.CONNECTING

        if not self.adb.ensure_connected():
            self._init_device_connection()
            if not self.adb.is_connected():
                self.log("❌ تعذر الاتصال بالمحاكي عبر ADB. يرجى تشغيل المحاكي.")
                self.state = BotState.DISCONNECTED
                self.is_running = False
                return

        self.state = BotState.RUNNING
        pending = [p for p in self.passengers if not ("تم" in p.booking_status or "مؤكد" in p.booking_status)]

        if not pending:
            self.log("ℹ لا توجد حسابات معلقة للحجز.")
            self.state = BotState.COMPLETED
            self.is_running = False
            return

        session = BookingSession(
            session_name="جلسة الحجز",
            target_date=self.config.get("target_date", ""),
            target_period=self.config.get("target_period", "All"),
            passengers=[]
        )

        results = []
        for idx, p in enumerate(pending):
            if not self.is_running:
                self.log("⛔ تم التوقف بناءً على طلب المستخدم.")
                break

            self.current_index = idx
            self.log(f"▶ معالجة الحساب [{idx+1}/{len(pending)}]: {p.name}")

            task = PassengerTask(
                name=p.name,
                gender=p.person_type or "رجال",
                national_id=p.passport_no or p.visa_no,
                email=p.email,
                password=self.config.get("unified_password", "Zxcv1234$"),
                is_registered=True
            )

            res = self.flow_ctrl.process_passenger_flow(task, session)
            results.append(res.to_dict())

            if res.status == "SUCCESS":
                p.booking_status = "✅ تم الحجز بنجاح"
                p.note = res.permit_details
                self.state = BotState.RUNNING
            elif res.status == "ALREADY_BOOKED":
                p.booking_status = "✅ تصريح مؤكد مسبقاً"
                p.note = res.permit_details
            elif res.status == "WAITING_LIST":
                p.booking_status = "📋 في قائمة الانتظار"
                p.note = res.action_taken
                self.state = BotState.WAITING_LIST
            elif res.status == "SECURITY_CHALLENGE":
                p.booking_status = "⚠️ تحقق أمني مطلوب"
                p.note = res.error_reason
                self.state = BotState.SECURITY_CHALLENGE
                self.log("🛑 توقف أمني فوري: تم رصد تحقق أمني يتطلب تدخلاً بشرياً.")
                self.is_running = False
                break
            elif res.status == "FULLY_BOOKED":
                p.booking_status = "⏳ المواعيد ممتلئة"
                p.note = res.error_reason
                self.state = BotState.FULLY_BOOKED
            else:
                p.booking_status = "❌ فشل"
                p.note = res.error_reason

            self._save_results(results)

        self.is_running = False
        if self.state not in [BotState.SECURITY_CHALLENGE, BotState.STOPPED]:
            self.state = BotState.COMPLETED
        self.log("🏁 اكتملت الجلسة.")

    def _save_results(self, results: List[Dict[str, Any]]):
        try:
            with open(self.results_path, "w", encoding="utf-8") as f:
                json.dump({
                    "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_results": len(results),
                    "results": results
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_results(self) -> Dict[str, Any]:
        if os.path.exists(self.results_path):
            try:
                with open(self.results_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"last_updated": "", "total_results": 0, "results": []}

    def get_status_dict(self) -> Dict[str, Any]:
        """Returns live dashboard status with strict masking of sensitive fields."""
        is_conn = self.adb.is_connected()
        focused = self.adb.get_focused_activity() if is_conn else ""
        screen_size = self.adb.get_screen_size() if is_conn else (0, 0)

        return {
            "state": self.state.value,
            "is_running": self.is_running,
            "current_index": self.current_index,
            "total_passengers": len(self.passengers),
            "passengers": [asdict(p) for p in self.passengers],
            "config": self.public_config(),  # Strict secret masking
            "is_connected": is_conn,
            "last_activity": focused,
            "driver_mode": self.driver_mode,
            "engine_mode": self.engine_mode,
            "last_screen": self.flow_ctrl.last_detected_screen.value,
            "screen_resolution": f"{screen_size[0]}x{screen_size[1]}" if screen_size != (0, 0) else "غير متاح",
            "device": {
                "serial": self.device_info.serial if self.device_info else "",
                "model": self.device_info.model if self.device_info else "",
                "android_version": self.device_info.android_version if self.device_info else "",
                "is_emulator": self.device_info.is_emulator if self.device_info else False
            } if self.device_info else None,
            "last_error": self.last_error
        }
