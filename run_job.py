# -*- coding: utf-8 -*-
"""
run_job.py
==========
Main Code-Driven Execution Script for NusukBot PC.
Performs preflight checks, loads passengers from configuration or CSV,
and runs the sequential booking session safely.
"""

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import json
from booking_plan import BookingSession, PassengerTask
from sequential_runner import SequentialRunner
from excel_manager import ExcelManager
from device_manager import DeviceManager


my_booking_session = BookingSession(
    session_name="خطة حجز الروضة الشريفة",
    target_date="",                            # اتركه فارغاً لأول موعد متاح أو بصيغة YYYY-MM-DD
    target_period="All",                       # "All", "Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"
    preferred_times=["08:00", "09:30", "14:00", "20:00"],
    clone_range=range(1, 2),                   # ابدأ بنسخة واحدة أو حساب واحد للاختبار الآمن
    close_clone_after_finish=True,
    clean_memory_between_clones=True,
    passengers=[],
    on_error="retry_and_continue",
    max_retries=2
)


def main():
    print("\n" + "=" * 65)
    print("  🕋 منظومة NusukBot PC - محرك تنفيذ خطة الحجز")
    print("=" * 65)

    cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
    config = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass

    # 1. Preflight check
    dm = DeviceManager(adb_path=config.get("adb_path"), preferred_serial=config.get("device_serial", "127.0.0.1:16384"))
    preflight = dm.run_preflight(config.get("nusuk_package", "com.moh.nusukapp"))

    if preflight["status"] != "CONNECTED":
        print("\n⚠️ تنبيه الفحص المسبق (Preflight Check):")
        print(f"  حالة الاتصال: {preflight['status']}")
        for rem in preflight["remediation"]:
            print(f"  - {rem}")
        print("\nيرجى تشغيل محاكي MuMu Player والتأكد من فتح ADB ثم إعادة المحاولة.\n")
        return

    # 2. Load passengers
    if not my_booking_session.passengers:
        excel_path = config.get("default_excel_path")
        if not excel_path or not os.path.exists(excel_path):
            sample_path = os.path.join(os.path.dirname(__file__), "sample_passengers.csv")
            if os.path.exists(sample_path):
                excel_path = sample_path

        if excel_path and os.path.exists(excel_path):
            print(f"📊 جاري تحميل بيانات المعتمرين من: {os.path.basename(excel_path)}")
            raw_passengers = ExcelManager.parse_file(excel_path)
            for idx, p in enumerate(raw_passengers):
                nat_id = p.passport_no or p.visa_no
                task = PassengerTask(
                    name=p.name,
                    gender=p.person_type or "رجال",
                    national_id=nat_id,
                    mobile=p.mobile,
                    email=p.email,
                    password=config.get("unified_password", "Zxcv1234$"),
                    is_registered=True,
                    clone_id=idx + 1
                )
                my_booking_session.passengers.append(task)
            print(f"✅ تم تحميل {len(my_booking_session.passengers)} معتمر.")

    if not my_booking_session.passengers:
        print("⚠️ لا يوجد معتمرون محملون لتنفيذ الخطة.")
        return

    # 3. Sequential Execution
    runner = SequentialRunner(my_booking_session, config_dict=config)
    results = runner.run()
    print("🏁 اكتملت الجلسة.")


if __name__ == "__main__":
    main()
