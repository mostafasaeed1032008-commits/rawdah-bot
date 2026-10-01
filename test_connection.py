# -*- coding: utf-8 -*-
"""
test_connection.py
==================
Diagnostic and preflight test script for NusukBot PC.
Tests:
  1. Python version & required libraries
  2. ADB discovery & version
  3. Connected Android devices & MuMu emulator status
  4. Nusuk app package installation & focus
  5. Screen resolution & coordinate bounds
"""

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
from device_manager import DeviceManager


def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  🔍 {title}")
    print("=" * 60)


def main():
    print("\n" + "#" * 60)
    print("  🚀 اختبار وتشخيص بيئة عمل NusukBot PC")
    print("#" * 60)

    dm = DeviceManager()
    preflight = dm.run_preflight()

    # 1. Python Environment
    print_header("1. بيئة بايثون والمكتبات المطلوبة")
    py_info = preflight["python"]
    print(f"  - مسار بايثون: {py_info['executable']}")
    print(f"  - الإصدار: {py_info['version']} {'(✅ مناسب)' if py_info['is_ok'] else '(❌ قديم)'}")

    pkgs = preflight["packages"]
    for pkg_name, ok in pkgs.items():
        print(f"  - حزمة {pkg_name:15s}: {'✅ مُثبتة' if ok else '❌ غير مُثبتة (pip install ' + pkg_name + ')'}")

    # 2. ADB Status
    print_header("2. فحص أداة ADB")
    adb_info = preflight["adb"]
    print(f"  - المسار المستخدم: {adb_info['resolved_path'] or 'لم يتم العثور عليه'}")
    if adb_info["version"]:
        print(f"  - الإصدار: {adb_info['version']} (✅ جاهز)")
    else:
        print("  - الحالة: ❌ غير متوفر أو تعذر تنفيذه.")

    # 3. Emulator & Devices
    print_header("3. فحص المحاكي والأجهزة المتصلة")
    emu_info = preflight["emulator"]
    if emu_info["running_processes"]:
        print(f"  - المحاكيات النشطة في النظام: {', '.join(emu_info['running_processes'])} (✅ قيد التشغيل)")
    else:
        print("  - المحاكيات النشطة: لا توجد عمليات محاكي نشطة حالياً.")

    dev = preflight["device"]
    if dev:
        print(f"  - الجهاز المتصل: {dev['serial']} (✅ متصل)")
        print(f"    * الموديل: {dev['model']}")
        print(f"    * نظام أندرويد: Android {dev['android_version']} (SDK {dev['sdk_version']})")
        print(f"    * أبعاد الشاشة: {dev['screen_size'] or 'افتراضية 900x1600'}")
        print(f"    * نوع الجهاز: {'محاكي (Emulator)' if dev['is_emulator'] else 'هاتف حقيقي (Physical Device)'}")
    else:
        print(f"  - حالة الجهاز: ⚪ {preflight['status']} (لا يوجد جهاز متصل حالياً)")

    # 4. Target Application
    print_header("4. فحص تطبيق نسك على الجهاز")
    app_info = preflight["app"]
    if dev:
        if app_info["is_installed"]:
            print(f"  - الحزمة {app_info['package']}: ✅ مُثبتة ({app_info['apk_path']})")
            if app_info["is_focused"]:
                print("  - شاشة التطبيق: 📱 التطبيق مفتوح حالياً في الواجهة الأمامية!")
        else:
            print(f"  - الحزمة {app_info['package']}: ⚪ غير مثبتة على هذا الجهاز.")
    else:
        print("  - تم تخطي الفحص لعدم توفر جهاز متصل.")

    # 5. Summary & Remediation
    print("\n" + "=" * 60)
    if preflight["status"] == "CONNECTED":
        print("  🎉 نتيجة الفحص: المنظومة متصلة وجاهزة للعمل.")
    else:
        print("  ℹ تقرير الحالة: المنظومة تعمل بالوضع المنفصل (Offline).")
        if preflight["remediation"]:
            print("\n  خطوات موصى بها:")
            for r in preflight["remediation"]:
                print(f"   • {r}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
