# -*- coding: utf-8 -*-
"""
otp_fetcher.py
==============
Retrieves Nusuk verification OTP codes from Gmail via secure IMAP.
Ensures zero credential leakage into stdout/logs and handles timeouts safely.
"""

import imaplib
import email
import email.utils
import re
import time
from datetime import datetime
from typing import Optional


class OtpFetcher:
    def __init__(self, user: str = "", app_password: str = ""):
        self.user = (user or "").strip()
        self.password = (app_password or "").strip().replace(" ", "")
        self.keywords = ["nusuk", "نسك", "otp", "verification", "رمز", "كود", "تحقق", "verify"]
        self.otp_pattern = re.compile(r"\b(\d{4,6})\b")

    def is_configured(self) -> bool:
        return bool(self.user and self.password)

    def fetch_latest_otp(self, timeout_seconds: int = 45, max_age_seconds: int = 120, poll_interval: float = 2.5) -> Optional[str]:
        if not self.is_configured():
            return None

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                otp = self._try_read_inbox(max_age_seconds)
                if otp:
                    return otp
            except imaplib.IMAP4.error as e:
                err_str = str(e)
                if "AUTHENTICATIONFAILED" in err_str or "Invalid credentials" in err_str:
                    print("[OtpFetcher] ❌ فشل تسجيل الدخول إلى Gmail: كلمة المرور العادية مرفوضة من Google. مطلوب (Google App Password) مكونة من 16 حرفاً.")
                    break
                else:
                    print(f"[OtpFetcher] خطأ IMAP: {err_str[:60]}")
            except Exception as e:
                # Log general error type without exposing credentials
                print(f"[OtpFetcher] التحقق من البريد: {type(e).__name__}")
            time.sleep(poll_interval)
        return None

    # Alias for backward compatibility
    def fetch_otp(self, timeout_seconds: int = 30) -> Optional[str]:
        return self.fetch_latest_otp(timeout_seconds=timeout_seconds)

    def _try_read_inbox(self, max_age_seconds: int) -> Optional[str]:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        try:
            mail.login(self.user, self.password)
            mail.select("INBOX")

            _, data = mail.search(None, "ALL")
            if not data or not data[0]:
                return None

            msg_ids = data[0].split()
            recent_ids = msg_ids[-8:] if len(msg_ids) >= 8 else msg_ids

            for msg_id in reversed(recent_ids):
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue

                msg = email.message_from_bytes(msg_data[0][1])

                # Check message age
                date_str = msg.get("Date", "")
                try:
                    msg_time = email.utils.parsedate_to_datetime(date_str)
                    age = (datetime.now(msg_time.tzinfo) - msg_time).total_seconds()
                    if age > max_age_seconds:
                        continue
                except Exception:
                    pass

                subject = str(msg.get("Subject", ""))
                body = self._extract_body(msg)
                combined = (subject + " " + body).lower()

                if any(kw in combined for kw in self.keywords):
                    matches = self.otp_pattern.findall(body)
                    if matches:
                        return matches[0]

            return None
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    def _extract_body(self, msg) -> str:
        if msg.is_multipart():
            parts = []
            for part in msg.walk():
                if part.get_content_type() in ("text/plain", "text/html"):
                    payload = part.get_payload(decode=True)
                    if payload:
                        parts.append(payload.decode("utf-8", errors="ignore"))
            return " ".join(parts)
        else:
            payload = msg.get_payload(decode=True)
            return payload.decode("utf-8", errors="ignore") if payload else ""
