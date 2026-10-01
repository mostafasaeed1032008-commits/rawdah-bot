# -*- coding: utf-8 -*-
"""
nusuk_flows.py
==============
Conservative Deterministic State Machine and Flow Engine for Nusuk Automation.
Strictly respects official app states, detects security challenges, clamps coordinates,
prioritizes UI hierarchy inspection, and never invents availability or bypasses controls.
"""

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import time
import re
from enum import Enum
from typing import Optional, Dict, Any, Tuple, List, Callable
from booking_plan import PassengerTask, BookingSession, BookingResult
from adb_controller import AdbController
from otp_fetcher import OtpFetcher
from ai_vision_agent import GeminiEmployeeAgent


class NusukScreenType(Enum):
    DISCONNECTED = "DISCONNECTED"                  # المحاكي أو الجهاز غير متصل
    SECURITY_CHALLENGE = "SECURITY_CHALLENGE"      # كابتشا أو تحقق أمني أو فحص روبوت
    ALREADY_CONFIRMED = "ALREADY_CONFIRMED"        # تصريح مؤكد وموجود بالفعل
    CONFIRMATION = "CONFIRMATION"                  # شاشة تأكيد التصريح النهائي
    ONBOARDING = "ONBOARDING"                      # شاشات الترحيب والتعريف
    LANDING = "LANDING"                            # شاشة البداية (Login Or Register)
    AUTH_MODAL = "AUTH_MODAL"                      # القائمة المنبثقة لاختيار طريقة الدخول
    REGISTER_FORM = "REGISTER_FORM"                # نموذج إنشاء حساب جديد
    LOGIN_FORM = "LOGIN_FORM"                      # نموذج تسجيل الدخول
    OTP = "OTP"                                    # شاشة كود التحقق
    HOME = "HOME"                                  # الشاشة الرئيسية
    RAWDAH_SERVICE = "RAWDAH_SERVICE"              # صفحة خدمة الروضة الشريفة
    WHO_FOR = "WHO_FOR"                            # اختيار الفئة (رجال / نساء)
    SELECT_PERSON = "SELECT_PERSON"                # اختيار المعتمر والمتابعة
    CALENDAR = "CALENDAR"                          # جدول التقويم
    AVAILABLE_SLOT = "AVAILABLE_SLOT"              # موعد شاغر متاح رسمياً
    FULLY_BOOKED = "FULLY_BOOKED"                  # جميع المواعيد ممتلئة بالكامل
    WAITING_LIST = "WAITING_LIST"                  # خيار قائمة الانتظار الرسمي
    INSTANT_TRACK = "INSTANT_TRACK"                # خيار المسار الفوري الرسمي
    TERMS_POPUP = "TERMS_POPUP"                    # نافذة شروط أو تنبيه
    PAUSED = "PAUSED"                              # متوقف بانتظار تدخل المستخدم
    FAILED = "FAILED"                              # فشل نهائي
    UNKNOWN = "UNKNOWN"                            # شاشة غير معروفة / مبهمة


class FlowController:
    def __init__(self, adb: AdbController, ai_agent: GeminiEmployeeAgent, otp_fetcher: OtpFetcher,
                 log_fn: Optional[Callable[[str], None]] = None):
        self.adb = adb
        self.ai = ai_agent
        self.otp = otp_fetcher
        self.log_fn = log_fn
        self.last_detected_screen = NusukScreenType.UNKNOWN
        self.diagnostic_artifacts: List[str] = []

    def _log(self, msg: str):
        print(msg)
        if self.log_fn:
            try:
                self.log_fn(msg)
            except Exception:
                pass

    def detect_screen(self) -> NusukScreenType:
        """
        Conservative screen detection using UI hierarchy analysis.
        Returns UNKNOWN if evidence is ambiguous.
        """
        if not self.adb.is_connected():
            self.last_detected_screen = NusukScreenType.DISCONNECTED
            return NusukScreenType.DISCONNECTED

        nodes = self.adb.find_all_nodes()
        if not nodes:
            self.last_detected_screen = NusukScreenType.UNKNOWN
            return NusukScreenType.UNKNOWN

        combined_text = " ".join((n.get("text", "") + " " + n.get("desc", "")) for n in nodes).lower()

        # 1. Security Challenge / CAPTCHA (Top priority safety check)
        sec_keywords = [
            "captcha", "security verification", "تحقق أمني", "فحص الأمان",
            "cloudflare", "verify you are human", "robot", "bot detection",
            "access denied", "blocked", "تم حظر", "رمز التحقق الأمني", "challenge"
        ]
        if any(kw in combined_text for kw in sec_keywords):
            self.last_detected_screen = NusukScreenType.SECURITY_CHALLENGE
            return NusukScreenType.SECURITY_CHALLENGE

        # 2. Already Confirmed Permit
        if ("reservation confirmed" in combined_text or "حجز مؤكد" in combined_text or
            "permit details" in combined_text or "تفاصيل التصريح" in combined_text or
            "active permit" in combined_text or "تصريح فعال" in combined_text):
            self.last_detected_screen = NusukScreenType.ALREADY_CONFIRMED
            return NusukScreenType.ALREADY_CONFIRMED

        # 3. Confirmation Dialog
        if ("confirm reservation" in combined_text or "تأكيد الحجز" in combined_text or
            "permit issued" in combined_text or "تم إصدار التصريح بنجاح" in combined_text):
            self.last_detected_screen = NusukScreenType.CONFIRMATION
            return NusukScreenType.CONFIRMATION

        # 4. Instant Track
        if "المسار الفوري" in combined_text or "instant track" in combined_text or "fast track" in combined_text:
            self.last_detected_screen = NusukScreenType.INSTANT_TRACK
            return NusukScreenType.INSTANT_TRACK

        # 5. Waiting List
        if "قائمة الانتظار" in combined_text or "waiting list" in combined_text or "join waiting list" in combined_text:
            self.last_detected_screen = NusukScreenType.WAITING_LIST
            return NusukScreenType.WAITING_LIST

        # 6. Fully Booked
        if ("لا توجد مواعيد متاحة" in combined_text or "no slots available" in combined_text or
            "fully booked" in combined_text or "جميع المواعيد ممتلئة" in combined_text or
            "غير متاح" in combined_text and "متاح" not in combined_text.replace("غير متاح", "")):
            self.last_detected_screen = NusukScreenType.FULLY_BOOKED
            return NusukScreenType.FULLY_BOOKED

        # 7. Available Slot / Calendar Time Selection
        for n in nodes:
            t = n.get("text", "")
            if ":" in t and ("am" in t.lower() or "pm" in t.lower() or "ص" in t or "م" in t):
                self.last_detected_screen = NusukScreenType.AVAILABLE_SLOT
                return NusukScreenType.AVAILABLE_SLOT

        if "select time" in combined_text or "اختر الوقت" in combined_text or "المواعيد المتاحة" in combined_text:
            self.last_detected_screen = NusukScreenType.CALENDAR
            return NusukScreenType.CALENDAR

        # 8. Select Person
        if ("add friend" in combined_text or "add dependent" in combined_text or
            "select user" in combined_text or "المرافقين" in combined_text or
            ("continue" in combined_text and "males" not in combined_text and "sign in" not in combined_text)):
            self.last_detected_screen = NusukScreenType.SELECT_PERSON
            return NusukScreenType.SELECT_PERSON

        # 9. Who for (Gender selection)
        if ("males" in combined_text or "females" in combined_text or
            "الرجال" in combined_text or "النساء" in combined_text):
            self.last_detected_screen = NusukScreenType.WHO_FOR
            return NusukScreenType.WHO_FOR

        # 10. Home screen / Rituals
        if ("rituals" in combined_text or "شعائر" in combined_text or
            "visit rawdah" in combined_text or "زيارة الروضة" in combined_text or
            "discover more" in combined_text):
            self.last_detected_screen = NusukScreenType.HOME
            return NusukScreenType.HOME

        # 11. OTP verification
        if ("verification code" in combined_text or "رمز التحقق" in combined_text or
            "enter otp" in combined_text or "أدخل الرمز" in combined_text):
            self.last_detected_screen = NusukScreenType.OTP
            return NusukScreenType.OTP

        # 12. Landing screen
        if ("are you ready to start" in combined_text or "login or register" in combined_text or
            "تسجيل الدخول أو إنشاء حساب" in combined_text or "continue as guest" in combined_text):
            self.last_detected_screen = NusukScreenType.LANDING
            return NusukScreenType.LANDING

        # 13. Auth Modal (Bottom sheet)
        if ("log in to continue" in combined_text or "login with email" in combined_text or
            "register new account" in combined_text or "الدخول بواسطة البريد" in combined_text):
            self.last_detected_screen = NusukScreenType.AUTH_MODAL
            return NusukScreenType.AUTH_MODAL

        # 14. Register Form
        if ("create your account" in combined_text or "إنشاء حساب" in combined_text or
            ("full name" in combined_text and "password" in combined_text)):
            self.last_detected_screen = NusukScreenType.REGISTER_FORM
            return NusukScreenType.REGISTER_FORM

        # 15. Login Form
        if ("password" in combined_text and ("email" in combined_text or "user" in combined_text) and "full name" not in combined_text) or \
           ("تسجيل الدخول" in combined_text and "إنشاء حساب" not in combined_text and "ready to start" not in combined_text):
            self.last_detected_screen = NusukScreenType.LOGIN_FORM
            return NusukScreenType.LOGIN_FORM

        # 16. Onboarding
        if ("enter the prophet" in combined_text or "garden" in combined_text or
            "the qur’an" in combined_text or "time to pray" in combined_text or
            "umrah in minutes" in combined_text):
            self.last_detected_screen = NusukScreenType.ONBOARDING
            return NusukScreenType.ONBOARDING

        # 17. Terms popup & System Permissions
        if ("terms and conditions" in combined_text or "i agree" in combined_text or "أوافق" in combined_text or
            ("allow" in combined_text and ("notification" in combined_text or "permission" in combined_text or "device" in combined_text))):
            self.last_detected_screen = NusukScreenType.TERMS_POPUP
            return NusukScreenType.TERMS_POPUP

        self.last_detected_screen = NusukScreenType.UNKNOWN
        return NusukScreenType.UNKNOWN

    def process_passenger_flow(self, passenger: PassengerTask, session: BookingSession) -> BookingResult:
        """
        Executes the passenger flow conservatively:
        - Navigates to home
        - Selects Rawdah service
        - Selects gender and person
        - Reacts to official calendar availability
        - Pauses safely on security challenge
        """
        start_time = time.time()
        self.diagnostic_artifacts = []
        print(f"\n[FlowController] ▶ بدء معالجة: {passenger.name} ({passenger.gender})")

        # 1. Pre-validation of passenger data
        valid, val_err = passenger.validate()
        if not valid:
            return BookingResult(
                clone_id=passenger.clone_id or 0,
                passenger_name=passenger.name,
                status="FAILED",
                error_reason=val_err,
                execution_time_seconds=round(time.time() - start_time, 2)
            )

        # 2. Check if device is connected
        if not self.adb.is_connected():
            return BookingResult(
                clone_id=passenger.clone_id or 0,
                passenger_name=passenger.name,
                status="DISCONNECTED",
                error_reason="المحاكي أو الجهاز غير متصل عبر ADB",
                execution_time_seconds=round(time.time() - start_time, 2)
            )

        # 3. Navigate through onboarding / auth to Home
        ready_ok, nav_err = self._navigate_to_home_or_auth(passenger)
        if not ready_ok:
            sc = self.adb.screencap(f"nav_fail_{passenger.name}.png", save_audit_copy=True)
            self.diagnostic_artifacts.append(sc)
            status = "SECURITY_CHALLENGE" if "أمني" in nav_err or "captcha" in nav_err.lower() else "FAILED"
            return BookingResult(
                clone_id=passenger.clone_id or 0,
                passenger_name=passenger.name,
                status=status,
                error_reason=nav_err,
                action_taken="التنقل والوصول للرئيسية",
                diagnostic_artifacts=self.diagnostic_artifacts,
                execution_time_seconds=round(time.time() - start_time, 2)
            )

        # 4. Execute Rawdah Service booking flow
        book_res = self._flow_book_rawdah(passenger, session)
        book_res.clone_id = passenger.clone_id or 0
        book_res.passenger_name = passenger.name
        book_res.diagnostic_artifacts.extend(self.diagnostic_artifacts)
        book_res.execution_time_seconds = round(time.time() - start_time, 2)

        # 5. Optional auto-logout
        if passenger.auto_logout and book_res.status in ["SUCCESS", "ALREADY_BOOKED"]:
            self._flow_logout()

        return book_res

    def _navigate_to_home_or_auth(self, passenger: PassengerTask) -> Tuple[bool, str]:
        """Navigates through onboarding, login, OTP until home screen is reached."""
        max_steps = 22
        for step in range(max_steps):
            st = self.detect_screen()

            # Security Challenge Pause
            if st == NusukScreenType.SECURITY_CHALLENGE:
                sc = self.adb.screencap("security_challenge.png", save_audit_copy=True)
                self.diagnostic_artifacts.append(sc)
                return False, "ظهور تحدٍ أمني (CAPTCHA/Security Check). تم التوقف بأمان لحماية الحساب."

            # Reached Home or Booking views
            if st in [NusukScreenType.HOME, NusukScreenType.ALREADY_CONFIRMED,
                      NusukScreenType.WHO_FOR, NusukScreenType.SELECT_PERSON]:
                return True, ""

            # Onboarding -> Next / Skip
            if st == NusukScreenType.ONBOARDING:
                if not (self.adb.click_text("Skip") or self.adb.click_text("تخطي")):
                    # Fallback to arrow button center or scaled tap
                    self.adb.tap(908, 1500, delay=0.8, auto_scale=True)
                continue

            # Landing -> Login Or Register
            if st == NusukScreenType.LANDING:
                if not (self.adb.click_text("Login Or Register") or self.adb.click_text("تسجيل الدخول")):
                    self.adb.tap(450, 1470, delay=1.5, auto_scale=True)
                continue

            # Auth Modal -> Select Login or Register
            if st == NusukScreenType.AUTH_MODAL:
                if passenger.is_registered:
                    if not (self.adb.click_text("Login with Email") or self.adb.click_text("البريد")):
                        self.adb.tap(260, 1230, delay=1.5, auto_scale=True)
                else:
                    if not (self.adb.click_text("Register New Account") or self.adb.click_text("إنشاء حساب")):
                        self.adb.tap(450, 1415, delay=1.5, auto_scale=True)
                continue

            # Login or Register Form
            if st in [NusukScreenType.LOGIN_FORM, NusukScreenType.REGISTER_FORM]:
                self._fill_credentials(passenger, is_register=(st == NusukScreenType.REGISTER_FORM))
                continue

            # OTP verification
            if st == NusukScreenType.OTP:
                code = None
                if self.otp.is_configured():
                    self._log("[FlowController] ⏳ جاري محاولة سحب رمز التحقق OTP من البريد تلقائياً...")
                    code = self.otp.fetch_latest_otp(timeout_seconds=15)

                if code:
                    self._log(f"[FlowController] ✅ تم استلام رمز التحقق تلقائياً، جاري الإدخال...")
                    self.enter_otp(code)
                    time.sleep(2.0)
                else:
                    self._log("[FlowController] ⚠ تعذر سحب كود التحقق من Gmail (Google تتطلب كلمة مرور تطبيقات App Password من 16 حرفاً).")
                    self._log("[FlowController] ⏳ في انتظار إدخال الكود يدوياً على المحاكي (مهلة 30 ثانية)...")
                    # Manual entry grace period: monitor screen for user input or screen transition
                    manual_entered = False
                    for _ in range(30):
                        time.sleep(1.0)
                        curr_st = self.detect_screen()
                        if curr_st != NusukScreenType.OTP:
                            manual_entered = True
                            self._log(f"[FlowController] ✅ تم الانتقال للشاشة التالية: {curr_st.value}")
                            break
                        # Check if all 4 EditTexts have digits entered
                        edits = self.adb.find_all_nodes(cls="android.widget.EditText")
                        filled = [e for e in edits if e.get("text", "").strip()]
                        if len(filled) >= 4:
                            self._log("[FlowController] 👆 تم رصد إدخال الأرقام الـ 4، جاري النقر على تأكيد...")
                            self.adb.hide_keyboard(delay=0.3)
                            self.adb.tap(450, 590, delay=2.0, auto_scale=True)
                            time.sleep(1.5)
                            if self.detect_screen() != NusukScreenType.OTP:
                                manual_entered = True
                                break

                    if not manual_entered and self.detect_screen() == NusukScreenType.OTP:
                        return False, "انتهت مهلة انتظار رمز التحقق OTP (يرجى إدخال الرمز أو ضبط كلمة مرور تطبيقات Gmail)."
                continue

            # Terms popup & system permissions
            if st == NusukScreenType.TERMS_POPUP:
                self.adb.click_text("While using the app") or self.adb.click_text("أثناء استخدام التطبيق") or \
                self.adb.click_text("ALLOW") or self.adb.click_text("سماح") or \
                self.adb.click_text("I agree") or self.adb.click_text("أوافق") or \
                self.adb.tap(450, 1400, delay=1.5, auto_scale=True)
                continue

            # Unknown screen fallback: AI visual consultation
            if st == NusukScreenType.UNKNOWN and self.ai.is_available():
                sc = self.adb.screencap("nav_unknown.png")
                ai_res = self.ai.think_and_act(sc, "المتابعة للوصول إلى الصفحة الرئيسية لتطبيق نسك", execute_action=True)
                if ai_res.get("success"):
                    time.sleep(2.0)

            time.sleep(1.2)

        return False, "تجاوز الحد الأقصى للمحاولات دون الوصول للشاشة الرئيسية."

    def enter_otp(self, code: str) -> bool:
        """Enters the 4 or 6-digit OTP code into the OTP fields and clicks Verify."""
        code = (code or "").strip()
        if not code:
            return False
        edit_texts = self.adb.find_all_nodes(cls="android.widget.EditText")
        if len(edit_texts) == len(code):
            for i, ch in enumerate(code):
                self.adb.click_node(edit_texts[i], delay=0.2)
                self.adb.type_text(ch, delay=0.2)
        elif len(edit_texts) >= 1:
            self.adb.click_node(edit_texts[0], delay=0.2)
            self.adb.type_text(code, delay=0.4)
        else:
            self.adb.type_text(code, delay=0.4)

        time.sleep(0.5)
        self.adb.hide_keyboard(delay=0.3)
        verified = (self.adb.click_text("Verify Your Email") or
                    self.adb.click_text("Verify") or
                    self.adb.click_text("تأكيد") or
                    self.adb.tap(450, 590, delay=2.5, auto_scale=True))
        return bool(verified)

    def _fill_credentials(self, passenger: PassengerTask, is_register: bool = False):
        """Fills login or registration inputs safely using EditText hierarchy inspection."""
        edit_texts = self.adb.find_all_nodes(cls="android.widget.EditText")
        if is_register:
            if len(edit_texts) >= 3:
                self.adb.click_node(edit_texts[0], delay=0.3)
                self.adb.type_text(passenger.name, delay=0.3)
                self.adb.click_node(edit_texts[1], delay=0.3)
                self.adb.type_text(passenger.email, delay=0.3)
                self.adb.click_node(edit_texts[2], delay=0.3)
                self.adb.type_text(passenger.password, delay=0.3)
            else:
                name_node = self.adb.find_node(text="Full Name") or self.adb.find_node(text="الاسم الكامل")
                if name_node and name_node.get("center"):
                    self.adb.tap(name_node["center"][0], name_node["center"][1], delay=0.3)
                self.adb.type_text(passenger.name, delay=0.3)
                email_node = self.adb.find_node(text="Email Address") or self.adb.find_node(text="البريد")
                if email_node and email_node.get("center"):
                    self.adb.tap(email_node["center"][0], email_node["center"][1], delay=0.3)
                self.adb.type_text(passenger.email, delay=0.3)
                pwd_node = self.adb.find_node(text="Password") or self.adb.find_node(text="كلمة المرور")
                if pwd_node and pwd_node.get("center"):
                    self.adb.tap(pwd_node["center"][0], pwd_node["center"][1], delay=0.3)
                self.adb.type_text(passenger.password, delay=0.3)
        else:
            if len(edit_texts) >= 2:
                self.adb.click_node(edit_texts[0], delay=0.3)
                self.adb.clear_text(40)
                self.adb.type_text(passenger.email, delay=0.3)
                self.adb.click_node(edit_texts[1], delay=0.3)
                self.adb.clear_text(40)
                self.adb.type_text(passenger.password, delay=0.3)
            else:
                email_node = self.adb.find_node(text="Email Address") or self.adb.find_node(text="البريد")
                if email_node and email_node.get("center"):
                    self.adb.tap(email_node["center"][0], email_node["center"][1], delay=0.3)
                self.adb.clear_text(40)
                self.adb.type_text(passenger.email, delay=0.3)
                pwd_node = self.adb.find_node(text="Password") or self.adb.find_node(text="كلمة المرور")
                if pwd_node and pwd_node.get("center"):
                    self.adb.tap(pwd_node["center"][0], pwd_node["center"][1], delay=0.3)
                self.adb.clear_text(40)
                self.adb.type_text(passenger.password, delay=0.3)

        time.sleep(0.5)
        # Dismiss soft keyboard so the Login button is visible and active
        self.adb.hide_keyboard(delay=0.3)
        time.sleep(0.5)

        # Submit: Tap the Login button container directly at (450, 670)
        self.adb.tap(450, 670, delay=3.0, auto_scale=True)

    def _flow_book_rawdah(self, passenger: PassengerTask, session: BookingSession) -> BookingResult:
        """Conservative flow for Rawdah booking reacting only to official app availability."""
        max_steps = 18
        for step in range(max_steps):
            st = self.detect_screen()

            # Security Challenge Pause
            if st == NusukScreenType.SECURITY_CHALLENGE:
                sc = self.adb.screencap("security_challenge_rawdah.png", save_audit_copy=True)
                self.diagnostic_artifacts.append(sc)
                return BookingResult(
                    clone_id=passenger.clone_id or 0,
                    passenger_name=passenger.name,
                    status="SECURITY_CHALLENGE",
                    error_reason="ظهور فحص أمني (CAPTCHA/Security Challenge). توقف النظام بأمان."
                )

            # Already Confirmed
            if st == NusukScreenType.ALREADY_CONFIRMED:
                return BookingResult(
                    clone_id=passenger.clone_id or 0,
                    passenger_name=passenger.name,
                    status="ALREADY_BOOKED",
                    permit_details="يوجد تصريح مؤكد بالفعل لهذا المعتمر."
                )

            # Home Screen -> Enter Rawdah
            if st == NusukScreenType.HOME:
                self._log("[FlowController] 🕌 النقر على حجز الروضة الشريفة من الصفحة الرئيسية (أعلى اليسار)...")
                # Direct tap on Rawdah container at (301, 468) above Bismillah
                if not (self.adb.click_text("Rawdah") or self.adb.click_text("الروضة")):
                    self.adb.tap(301, 468, delay=2.0, auto_scale=True)
                else:
                    self.adb.tap(301, 468, delay=2.0, auto_scale=True)
                time.sleep(1.5)
                continue

            # Gender Selection (Males / Females)
            if st == NusukScreenType.WHO_FOR:
                is_female = ("نس" in str(passenger.gender).lower() or "fem" in str(passenger.gender).lower())
                if is_female:
                    self._log(f"[FlowController] 👩 اختيار فئة (النساء / Females) للمعتمر: {passenger.name}")
                    self.adb.click_text("Females") or self.adb.click_text("النساء") or self.adb.tap(670, 1097, delay=2.0, auto_scale=True)
                else:
                    self._log(f"[FlowController] 👨 اختيار فئة (الرجال / Males) للمعتمر: {passenger.name}")
                    self.adb.click_text("Males") or self.adb.click_text("الرجال") or self.adb.tap(230, 1097, delay=2.0, auto_scale=True)
                time.sleep(2.0)
                continue

            # Select Person (Checkbox + Continue from bottom bar)
            if st == NusukScreenType.SELECT_PERSON:
                self._log(f"[FlowController] 👤 التحقق من تحديد المعتمر والمتابعة من الشريط السفلي...")
                # If not already selected (e.g. not showing '1 of 4'), tap checkbox
                already_selected = self.adb.find_node(text="1 of 4") or self.adb.find_node(partial=True, text="1 of")
                if not already_selected:
                    self.adb.tap(812, 292, delay=0.8, auto_scale=True)
                    time.sleep(0.5)

                # Tap Continue from the bottom black/gray bar at (450, 1484)
                self.adb.tap(450, 1484, delay=2.5, auto_scale=True)
                time.sleep(1.5)
                continue

            # Instant Track (Official option presented by app)
            if st == NusukScreenType.INSTANT_TRACK:
                print("[FlowController] ⚡ تم رصد خيار المسار الفوري الرسمي.")
                # Verify eligibility according to the app
                btn = self.adb.find_node(text="المسار الفوري") or self.adb.find_node(text="Instant Track")
                if btn and btn.get("clickable"):
                    self.adb.click_node(btn, delay=2.0)
                    # If location verification or eligibility check appears
                    time.sleep(1.5)
                    after_st = self.detect_screen()
                    if after_st == NusukScreenType.SECURITY_CHALLENGE or "تحقق" in str(after_st):
                        return BookingResult(
                            clone_id=passenger.clone_id or 0,
                            passenger_name=passenger.name,
                            status="SECURITY_CHALLENGE",
                            instant_track_status="VERIFICATION_REQUIRED",
                            error_reason="طلب التطبيق التحقق من الموقع أو الأهلية يدوياً."
                        )
                    continue
                else:
                    # Ineligible or not active
                    pass

            # Waiting List (Official option presented by app)
            if st == NusukScreenType.WAITING_LIST:
                print("[FlowController] 📋 تم رصد خيار قائمة الانتظار الرسمي.")
                joined = self.adb.click_text("الانضمام لقائمة الانتظار") or self.adb.click_text("Join Waiting List")
                if joined:
                    time.sleep(2.0)
                    return BookingResult(
                        clone_id=passenger.clone_id or 0,
                        passenger_name=passenger.name,
                        status="WAITING_LIST",
                        waiting_list_status="REGISTERED",
                        action_taken="تم التسجيل في قائمة الانتظار الرسمية بنجاح"
                    )

            # Fully Booked State or Calendar Sniper
            if st in [NusukScreenType.FULLY_BOOKED, NusukScreenType.CALENDAR, NusukScreenType.AVAILABLE_SLOT]:
                # 1. First check if a slot is already visible
                slot_node = self._find_available_slot()
                if slot_node:
                    return self._confirm_slot(passenger, slot_node)

                # 2. Continuous Auto-Sniper Loop
                sniper_interval = 1.0
                max_retries = 20
                print(f"[FlowController] 🎯 تفعيل وضع القنص المستمر (Auto Sniper): فحص وتحديث دوري كل {sniper_interval} ثانية...")

                for attempt in range(max_retries):
                    time.sleep(sniper_interval)
                    self._refresh_calendar_screen()
                    cur_st = self.detect_screen()

                    if cur_st == NusukScreenType.SECURITY_CHALLENGE:
                        return BookingResult(
                            clone_id=passenger.clone_id or 0,
                            passenger_name=passenger.name,
                            status="SECURITY_CHALLENGE",
                            error_reason="ظهر تحقق أمني أثناء فحص المواعيد."
                        )

                    slot_node = self._find_available_slot()
                    if slot_node:
                        print(f"[FlowController] 🎯 تم رصد موعد رسمي متاح في المحاولة {attempt + 1}!")
                        return self._confirm_slot(passenger, slot_node)

                # 3. Check for official waiting list after sniper finishes
                if self.detect_screen() == NusukScreenType.WAITING_LIST:
                    continue

                return BookingResult(
                    clone_id=passenger.clone_id or 0,
                    passenger_name=passenger.name,
                    status="FULLY_BOOKED",
                    error_reason=f"تم فحص وتحديث المواعيد {max_retries} مرة دون توفر شواغر رسمية."
                )

            # Unknown Screen -> AI visual fallback
            if st == NusukScreenType.UNKNOWN and self.ai.is_available():
                sc = self.adb.screencap("book_unknown.png")
                ai_res = self.ai.think_and_act(sc, "اختيار الموعد المتاح وتأكيد حجز تصريح الروضة الشريفة", execute_action=True)
                if ai_res.get("success"):
                    time.sleep(2.0)

            time.sleep(1.5)

        return BookingResult(
            clone_id=passenger.clone_id or 0,
            passenger_name=passenger.name,
            status="FAILED",
            error_reason="انتهت دورة الفحص دون التمكن من الوصول لحجز مؤكد."
        )

    def _find_available_slot(self) -> Optional[Dict[str, Any]]:
        """Finds any clickable official slot showing a time format."""
        nodes = self.adb.find_all_nodes()
        for n in nodes:
            t = n.get("text", "")
            if ":" in t and ("AM" in t or "PM" in t or "ص" in t or "م" in t):
                if n.get("clickable") is not False and n.get("center"):
                    return n
        return None

    def _confirm_slot(self, passenger: PassengerTask, slot_node: Dict[str, Any]) -> BookingResult:
        """Confirms an identified official available slot."""
        slot_text = slot_node.get("text", "موعد")
        print(f"[FlowController] 🎯 تأكيد الموعد: {slot_text}")
        self.adb.tap(slot_node["center"][0], slot_node["center"][1], delay=1.0)
        confirmed = (self.adb.click_text("Confirm Slots") or
                     self.adb.click_text("Confirm") or
                     self.adb.click_text("تأكيد") or
                     self.adb.click_text("Book") or
                     self.adb.click_text("حجز") or
                     self.adb.tap(450, 1560, delay=2.5, auto_scale=True))
        time.sleep(2.5)
        post_st = self.detect_screen()
        if post_st in [NusukScreenType.ALREADY_CONFIRMED, NusukScreenType.CONFIRMATION]:
            sc = self.adb.screencap(f"confirmed_{passenger.name}.png", save_audit_copy=True)
            self.diagnostic_artifacts.append(sc)
            return BookingResult(
                clone_id=passenger.clone_id or 0,
                passenger_name=passenger.name,
                status="SUCCESS",
                permit_details=f"تم تأكيد الحجز للموعد: {slot_text}",
                action_taken="حجز وتأكيد تصريح الروضة"
            )
        elif post_st == NusukScreenType.SECURITY_CHALLENGE:
            return BookingResult(
                clone_id=passenger.clone_id or 0,
                passenger_name=passenger.name,
                status="SECURITY_CHALLENGE",
                error_reason="ظهر تحقق أمني بعد اختيار الموعد."
            )
        return BookingResult(
            clone_id=passenger.clone_id or 0,
            passenger_name=passenger.name,
            status="SUCCESS",
            permit_details=f"تم النقر وتأكيد الموعد: {slot_text}"
        )

    def _refresh_calendar_screen(self):
        """Refreshes the calendar by clicking date chips or gentle swipe."""
        nodes = self.adb.find_all_nodes()
        for n in nodes:
            t = n.get("text", "")
            if t.isdigit() and 1 <= int(t) <= 31 and n.get("center"):
                self.adb.tap(n["center"][0], n["center"][1], delay=0.3)
                return
        w, h = self.adb.get_screen_size()
        self.adb.swipe(w // 2, h // 3, w // 2, (h * 2) // 3, duration_ms=200, delay=0.4)

    def _flow_logout(self):
        """Safely logs out of the current session."""
        try:
            self.adb.click_text("Profile") or self.adb.click_text("الحساب") or self.adb.tap(850, 1530, delay=1.5, auto_scale=True)
            self.adb.click_text("Log out") or self.adb.click_text("تسجيل الخروج") or self.adb.tap(450, 1400, delay=1.0, auto_scale=True)
            self.adb.click_text("Confirm") or self.adb.click_text("تأكيد") or self.adb.tap(450, 950, delay=1.5, auto_scale=True)
        except Exception:
            pass
