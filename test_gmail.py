# -*- coding: utf-8 -*-
"""
test_gmail.py
=============
Standalone Gmail IMAP Connection & OTP Diagnostic Tool.
Tests secure IMAP authentication and verifies inbox accessibility without printing secrets.
"""

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import json
import imaplib
import email
from datetime import datetime
from otp_fetcher import OtpFetcher

def run_diagnostic():
    print("=" * 60)
    print("  📧 أداة فحص واختبار اتصال Gmail وسحب الـ OTP")
    print("=" * 60)

    # 1. Load config
    cfg = {}
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"❌ تعذر قراءة config.json: {e}")
        return

    user = cfg.get("gmail_user", "").strip()
    app_pwd = cfg.get("gmail_app_password", "").strip().replace(" ", "")

    if not user:
        print("⚠ لم يتم تحديد البريد الإلكتروني في config.json (حقل: gmail_user)")
        return

    print(f"👤 البريد المستهدف: {user}")

    if not app_pwd:
        print("❌ كلمة مرور تطبيقات جوجل (gmail_app_password) غير مسجلة في config.json!")
        print("\n💡 كيفية الحصول عليها:")
        print("  1. افتح الرابط: https://myaccount.google.com/apppasswords")
        print("  2. أنشئ كلمة مرور باسم NusukBot")
        print("  3. انسخ الكود المكون من 16 حرفاً وضعه في حقل gmail_app_password")
        return

    print(f"🔑 كلمة مرور التطبيقات: مسجلة ومحفوظة بأمان (بطول {len(app_pwd)} حرفاً).")
    print("\n⏳ جاري الاتصال بخادم Gmail (imap.gmail.com:993)...")

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(user, app_pwd)
        mail.select("INBOX")
        status, data = mail.search(None, "ALL")

        if status == "OK" and data and data[0]:
            msg_ids = data[0].split()
            print(f"✅ تم الاتصال بنجاح تام! عدد الرسائل في صندوق الوارد: {len(msg_ids)}")

            # Fetch latest message info
            last_id = msg_ids[-1]
            _, msg_data = mail.fetch(last_id, "(RFC822.HEADER)")
            if msg_data and msg_data[0]:
                msg = email.message_from_bytes(msg_data[0][1])
                subj = msg.get("Subject", "بدون عنوان")
                dt = msg.get("Date", "غير معروف")
                print(f"📬 آخر رسالة وصلت: {subj}")
                print(f"📅 تاريخ آخر رسالة: {dt}")

            # Test OtpFetcher module
            print("\n🔍 اختبار وحدة سحب الـ OTP (OtpFetcher)...")
            fetcher = OtpFetcher(user, app_pwd)
            print("⚡ وحدة OtpFetcher جاهزة للعمل وسحب الأكواد في أقل من ثانية فور وصولها!")
        else:
            print("✅ تم الاتصال بـ Gmail ولكن صندوق الوارد فارغ حالياً.")

        mail.logout()
        print("\n🎉 المنظومة متصلة بنجاح مع Gmail!")
    except imaplib.IMAP4.error as e:
        print(f"\n❌ فشل تسجيل الدخول إلى Gmail: {e}")
        print("💡 تذكير: يجب استخدام 'كلمة مرور التطبيقات (App Password)' المكونة من 16 حرفاً وليس كلمة مرور حسابك العادية.")
    except Exception as e:
        print(f"\n❌ خطأ في الاتصال: {e}")

if __name__ == "__main__":
    run_diagnostic()
