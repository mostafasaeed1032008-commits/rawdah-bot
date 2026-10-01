# -*- coding: utf-8 -*-
"""
nusuk_api_client.py
===================
Direct REST API Client for Nusuk (Modelled after RawdahPass and NusukWeb architecture).
Interacts directly with official Nusuk API endpoints on `https://nusukapp.nusuk.sa/nusuk/`.
Bypasses the need for Android emulators (MuMu), heavy graphical rendering, and UI latency.
"""

import logging
import time
from typing import Dict, Any, Optional, List, Union
from curl_cffi import requests

import nusuk_crypto

logger = logging.getLogger("NusukApiClient")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class NusukServiceId:
    UMRAH = 11
    RAWDAH_MEN = 20
    RAWDAH_WOMEN = 21


class NusukApiClient:
    BASE_URL = "https://nusukapp.nusuk.sa/nusuk"

    def __init__(self, impersonate: str = "chrome124", language: str = "ar", timeout: int = 15, mock_mode: bool = False):
        self.impersonate = impersonate
        self.language = language
        self.timeout = timeout
        self.mock_mode = mock_mode
        self.session = requests.Session(impersonate=impersonate)

        # User authentication state
        self.user_id: Optional[int] = None
        self.phone_no: Optional[str] = None
        self.auth_token: Optional[str] = None
        self.user_profile: Optional[Dict[str, Any]] = None
        self.request_uuid: Optional[str] = None
        self._nationalities_cache: Optional[List[Dict[str, Any]]] = None

    def _get_headers(self, target_url: Optional[str] = None) -> Dict[str, str]:
        """Builds standard headers matching services.nusuk.sa portal."""
        now_ms = str(int(time.time() * 1000))
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://services.nusuk.sa",
            "Referer": "https://services.nusuk.sa/nusuk-svc/",
            "channel": "portal",
            "Accept-Language": self.language,
            "timestamp": now_ms
        }
        if self.auth_token and target_url:
            signed_bearer = nusuk_crypto.generate_bearer_token(self.auth_token, target_url)
            headers["Authorization"] = f"Bearer {signed_bearer}"
            headers["vId"] = "1"
        return headers

    def get_nationalities(self) -> List[Dict[str, Any]]:
        """Retrieves list of countries and nationality IDs from official lookup."""
        if self._nationalities_cache:
            return self._nationalities_cache

        url = f"{self.BASE_URL}/public/lookup/nationalities"
        try:
            r = self.session.get(url, headers=self._get_headers(), timeout=self.timeout)
            if r.status_code == 200:
                data = r.json()
                nats = data.get("response", {}).get("Nationalities", [])
                self._nationalities_cache = nats
                return nats
        except Exception as e:
            logger.error(f"Error fetching nationalities lookup: {e}")
        return []

    def find_nationality_id(self, country_name_or_code: str) -> Optional[int]:
        """Finds nationality ID by country name in Arabic, English, or ID."""
        nats = self.get_nationalities()
        target = str(country_name_or_code).strip().lower()
        if target.isdigit():
            return int(target)

        aliases = {
            "egypt": "مصر",
            "saudi": "السعودية",
            "ksa": "السعودية",
            "jordan": "الأردن",
            "kuwait": "الكويت",
            "uae": "الإمارات",
            "pakistan": "باكستان",
            "india": "الهند",
            "indonesia": "إندونيسيا",
            "turkey": "تركيا",
            "algeria": "الجزائر",
            "morocco": "المغرب",
            "tunisia": "تونس",
            "iraq": "العراق",
            "yemen": "اليمن"
        }
        for k, v in aliases.items():
            if k in target:
                target = v
                break

        # 1. Exact match first
        for item in nats:
            ar_name = item.get("NationalityNameAr", "").strip()
            std_name = item.get("NationalityName", "").strip()
            if target == ar_name or target == std_name:
                return item.get("NationalityId")

        # 2. Substring match fallback
        for item in nats:
            ar_name = item.get("NationalityNameAr", "").strip()
            std_name = item.get("NationalityName", "").strip()
            if target in ar_name or target in std_name or ar_name in target:
                return item.get("NationalityId")
        return None

    def login_visitor(
        self,
        nationality_id: Union[int, str],
        passport_no: str,
        password: str,
        recaptcha_token: str = "dummy"
    ) -> Dict[str, Any]:
        """
        Executes visitor login against Nusuk portal.
        POST /public/portal/loginservices/login
        """
        url_path = "public/portal/loginservices/login"
        full_url = f"{self.BASE_URL}/{url_path}"

        if isinstance(nationality_id, str) and not nationality_id.isdigit():
            resolved = self.find_nationality_id(nationality_id)
            if resolved:
                nationality_id = resolved
            else:
                nationality_id = 20  # Default to Egypt (20) if unresolved

        if self.mock_mode:
            uid = abs(hash(passport_no)) % 1000000 + 100000
            self.user_id = uid
            self.phone_no = "966500000000"
            self.request_uuid = f"mock-uuid-{uid}"
            logger.info(f"🧪 [وضع المحاكاة] تسجيل دخول تجريبي ناجح: UserID={uid}")
            return {
                "success": True,
                "needs_otp": True,
                "user_id": uid,
                "phone_no": self.phone_no,
                "request_uuid": self.request_uuid,
                "raw": {"UserID": uid, "PhoneNo": self.phone_no}
            }

        payload = {
            "Request": {
                "UserType": 3,
                "Natioanlity": int(nationality_id),
                "Pssport": passport_no.strip(),
                "Password": password,
                "reCaptchaToken": recaptcha_token
            }
        }

        logger.info(f"Submitting visitor login for passport {passport_no}, nationality {nationality_id}...")
        try:
            r = self.session.post(full_url, headers=self._get_headers(), json=payload, timeout=self.timeout)
            res_json = r.json()
            resp = res_json.get("response", {})
            code = resp.get("responseCode")
            desc = resp.get("responseDesc", "")
            self.request_uuid = resp.get("requestUUID")

            logger.info(f"Login response status: {r.status_code}, code: {code}, desc: {desc}")

            if code == 0 and resp.get("data"):
                # Decrypt embedded user data
                decrypted = nusuk_crypto.get_object_from_string(resp["data"])
                if decrypted:
                    self.user_id = decrypted.get("UserID")
                    self.phone_no = decrypted.get("PhoneNo")
                    logger.info(f"Login credential verified! UserID={self.user_id}, Phone={self.phone_no}. OTP Challenge required.")
                    return {
                        "success": True,
                        "needs_otp": True,
                        "user_id": self.user_id,
                        "phone_no": self.phone_no,
                        "request_uuid": self.request_uuid,
                        "raw": decrypted
                    }

            return {
                "success": False,
                "needs_otp": False,
                "code": code,
                "message": desc,
                "request_uuid": self.request_uuid
            }
        except Exception as e:
            logger.error(f"Login request exception: {e}")
            return {"success": False, "message": str(e)}

    def verify_otp(
        self,
        otp_code: str,
        user_id: Optional[int] = None,
        phone_no: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submits verification OTP for login session.
        POST /public/portal/loginservices/VerifyLogin
        """
        url_path = "public/portal/loginservices/VerifyLogin"
        full_url = f"{self.BASE_URL}/{url_path}"

        uid = user_id or self.user_id
        phone = phone_no or self.phone_no

        if self.mock_mode:
            self.auth_token = f"mock_bearer_token_{uid}"
            self.user_profile = {"VisitorNameLa": "Pilgrim", "VisitorNameAr": "معتمر", "Token": self.auth_token}
            logger.info(f"🧪 [وضع المحاكاة] توثيق OTP تجريبي ناجح: Token={self.auth_token}")
            return {
                "success": True,
                "token": self.auth_token,
                "profile": self.user_profile
            }

        if not uid:
            return {"success": False, "message": "Missing UserID for OTP verification"}

        payload = {
            "Request": {
                "OTP": str(otp_code).strip(),
                "UserID": uid,
                "PhoneNo": phone or ""
            }
        }

        logger.info(f"Submitting OTP {otp_code} for UserID={uid}...")
        try:
            r = self.session.post(full_url, headers=self._get_headers(), json=payload, timeout=self.timeout)
            res_json = r.json()
            resp = res_json.get("response", {})
            code = resp.get("responseCode")
            desc = resp.get("responseDesc", "")

            logger.info(f"VerifyLogin response: code: {code}, desc: {desc}")

            if code == 0 and resp.get("data"):
                decrypted = nusuk_crypto.get_object_from_string(resp["data"])
                if decrypted:
                    self.user_profile = decrypted
                    self.auth_token = decrypted.get("Token") or decrypted.get("token")
                    logger.info(f"Authentication successful! Token acquired for user: {decrypted.get('VisitorNameLa', '')}")
                    return {
                        "success": True,
                        "token": self.auth_token,
                        "profile": self.user_profile
                    }

            return {
                "success": False,
                "code": code,
                "message": desc
            }
        except Exception as e:
            logger.error(f"Verify OTP request exception: {e}")
            return {"success": False, "message": str(e)}

    def recover_account_visitor(
        self,
        passport_no: str,
        nationality_id: Union[int, str],
        dob: str,
        new_email: str,
        new_password: str,
        recaptcha_token: str = "dummy"
    ) -> Dict[str, Any]:
        """
        Step 1 of Visitor Account Recovery (تعديل البريد واسترجاع الحساب للزائر):
        POST /public/change
        Verifies Passport, Nationality, and Date of Birth against official records,
        then triggers a 4-digit verification OTP to `new_email`.
        
        :param passport_no: Passport Number (e.g., 'A41820141')
        :param nationality_id: Country ID (Egypt = 20)
        :param dob: Date of birth formatted as YYYYMMDD (e.g., '19850514')
        :param new_email: The new email to link (e.g., dot-trick Gmail)
        :param new_password: The new password to assign
        :param recaptcha_token: Enterprise reCAPTCHA token if required
        """
        url_path = "public/change"
        full_url = f"{self.BASE_URL}/{url_path}"

        if isinstance(nationality_id, str) and not nationality_id.isdigit():
            resolved = self.find_nationality_id(nationality_id)
            nationality_id = resolved if resolved else 20

        # Ensure DOB is clean digits YYYYMMDD
        clean_dob = re.sub(r"[^0-9]", "", str(dob))

        payload = {
            "Request": {
                "UserType": 3,
                "Device_Id": "A54646848a",
                "Passport_No": passport_no.strip().upper(),
                "Nationality_Id": int(nationality_id),
                "DOB": clean_dob,
                "DOBType": 2,
                "Password": new_password,
                "NewEmail": new_email.strip(),
                "reCaptchaToken": recaptcha_token
            }
        }

        logger.info(f"Initiating Account Recovery for passport {passport_no}, email {new_email}...")
        try:
            r = self.session.post(full_url, headers=self._get_headers(), json=payload, timeout=self.timeout)
            res_json = r.json()
            resp = res_json.get("response", {})
            code = resp.get("responseCode")
            desc = resp.get("responseDesc", "")

            logger.info(f"Recovery step 1 status: {r.status_code}, code: {code}, desc: {desc}")

            if code == 0:
                return {
                    "success": True,
                    "needs_otp": True,
                    "message": desc,
                    "email": new_email,
                    "request_uuid": resp.get("requestUUID")
                }
            return {
                "success": False,
                "code": code,
                "message": desc,
                "request_uuid": resp.get("requestUUID")
            }
        except Exception as e:
            logger.error(f"recover_account_visitor exception: {e}")
            return {"success": False, "message": str(e)}

    def verify_recover_account_visitor(
        self,
        passport_no: str,
        nationality_id: Union[int, str],
        dob: str,
        new_email: str,
        new_password: str,
        otp_code: str
    ) -> Dict[str, Any]:
        """
        Step 2 of Visitor Account Recovery:
        POST /public/verify
        Submits 4-digit OTP. Once verified, the account is permanently rebound to
        `new_email` with `new_password` ready for immediate login!
        """
        url_path = "public/verify"
        full_url = f"{self.BASE_URL}/{url_path}"

        if isinstance(nationality_id, str) and not nationality_id.isdigit():
            resolved = self.find_nationality_id(nationality_id)
            nationality_id = resolved if resolved else 20

        clean_dob = re.sub(r"[^0-9]", "", str(dob))

        payload = {
            "Request": {
                "UserType": 3,
                "Device_Id": "A54646848a",
                "Passport_No": passport_no.strip().upper(),
                "Nationality_Id": int(nationality_id),
                "DOB": clean_dob,
                "DOBType": 2,
                "Password": new_password,
                "NewEmail": new_email.strip(),
                "OTP": str(otp_code).strip()
            }
        }

        logger.info(f"Verifying Recovery OTP {otp_code} for {passport_no}...")
        try:
            r = self.session.post(full_url, headers=self._get_headers(), json=payload, timeout=self.timeout)
            res_json = r.json()
            resp = res_json.get("response", {})
            code = resp.get("responseCode")
            desc = resp.get("responseDesc", "")

            logger.info(f"Recovery OTP response: code: {code}, desc: {desc}")

            if code == 0:
                return {
                    "success": True,
                    "message": "Account recovered and successfully rebound!",
                    "passport": passport_no,
                    "email": new_email
                }
            return {
                "success": False,
                "code": code,
                "message": desc
            }
        except Exception as e:
            logger.error(f"verify_recover_account_visitor exception: {e}")
            return {"success": False, "message": str(e)}

    def get_available_slots(
        self,
        month: int,
        year: int,
        service_id: int = NusukServiceId.RAWDAH_MEN,
        is_hijri: bool = False,
        count: int = 1
    ) -> Dict[str, Any]:
        """
        Queries available timeslots for a given month/year and service.
        POST /timeslots/available
        """
        if self.mock_mode:
            slot_id = 9800 + (month * 10) + (service_id % 10)
            logger.info(f"🧪 [وضع المحاكاة] استرجاع مواعيد شاغرة تجريبية: TimeslotID={slot_id}")
            return {
                "success": True,
                "available_dates": [
                    {
                        "Date": f"15/{month:02d}/{year}",
                        "Timeslots": [
                            {"TimeslotID": slot_id, "TimeAr": "08:00 ص - 08:30 ص", "TimeLa": "08:00 AM - 08:30 AM"}
                        ],
                        "PercentageColor": "4caf50"
                    }
                ],
                "code": 0
            }

        url_path = "timeslots/available"
        full_url = f"{self.BASE_URL}/{url_path}"

        date_str = f"{month:02d}/{year}"
        date_type = 1 if is_hijri else 2

        payload = {
            "Request": {
                "Count": count,
                "Date": date_str,
                "DateType": date_type,
                "ServiceID": service_id
            }
        }

        logger.info(f"Polling slots: Service={service_id}, Date={date_str}...")
        try:
            headers = self._get_headers(target_url=url_path)
            r = self.session.post(full_url, headers=headers, json=payload, timeout=self.timeout)
            res_json = r.json()
            resp = res_json.get("response", {})
            code = resp.get("responseCode")
            desc = resp.get("responseDesc", "")

            if code == 0:
                available_dates = resp.get("AvailableDates", [])
                logger.info(f"Retrieved {len(available_dates)} available date records")
                return {
                    "success": True,
                    "available_dates": available_dates,
                    "code": code
                }

            return {
                "success": False,
                "code": code,
                "message": desc
            }
        except Exception as e:
            logger.error(f"get_available_slots exception: {e}")
            return {"success": False, "message": str(e)}

    def issue_permit_visitor(
        self,
        service_id: int,
        timeslot_id: int,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Issues Rawdah or Umrah permit for an international visitor.
        POST /reservations/issuePermitEatVisitor
        """
        uid = user_id or self.user_id
        if not uid:
            return {"success": False, "message": "Missing UserID for issuing permit"}

        if self.mock_mode:
            permit_id = f"RAWDAH-{abs(hash(str(timeslot_id) + str(uid))) % 10000000}"
            logger.info(f"🧪 [وضع المحاكاة] تم تأكيد إصدار التصريح التجريبي: {permit_id}")
            return {
                "success": True,
                "permit_data": {
                    "PermitNumber": permit_id,
                    "Status": "CONFIRMED",
                    "ServiceID": service_id,
                    "TimeslotID": timeslot_id,
                    "QR": f"https://services.nusuk.sa/qr/{permit_id}"
                },
                "response": {"responseCode": 0}
            }

        url_path = "reservations/issuePermitEatVisitor"
        full_url = f"{self.BASE_URL}/{url_path}"

        payload = {
            "Request": {
                "Count": 1,
                "ServiceID": service_id,
                "TimeslotID": [timeslot_id],
                "MuatamerList": [
                    {"UserID": uid}
                ]
            }
        }

        logger.info(f"Booking permit: Service={service_id}, TimeslotID={timeslot_id}, UserID={uid}...")
        try:
            headers = self._get_headers(target_url=url_path)
            r = self.session.post(full_url, headers=headers, json=payload, timeout=self.timeout)
            res_json = r.json()
            resp = res_json.get("response", {})
            code = resp.get("responseCode")
            desc = resp.get("responseDesc", "")

            if code == 0:
                permit_data = resp.get("data")
                logger.info(f"Permit issued successfully! Details: {permit_data}")
                return {
                    "success": True,
                    "permit_data": permit_data,
                    "response": resp
                }

            return {
                "success": False,
                "code": code,
                "message": desc
            }
        except Exception as e:
            logger.error(f"issue_permit exception: {e}")
            return {"success": False, "message": str(e)}

    def get_all_active_permits(self) -> Dict[str, Any]:
        """
        Retrieves all currently active permits for the logged-in account.
        POST /reservations/getAllActivePermitsEat
        """
        url_path = "reservations/getAllActivePermitsEat"
        full_url = f"{self.BASE_URL}/{url_path}"

        try:
            headers = self._get_headers(target_url=url_path)
            r = self.session.post(full_url, headers=headers, json={"Request": {}}, timeout=self.timeout)
            res_json = r.json()
            resp = res_json.get("response", {})
            code = resp.get("responseCode")

            if code == 0:
                permits = resp.get("Permits", []) or resp.get("Reservations", [])
                return {"success": True, "permits": permits}
            return {"success": False, "code": code, "message": resp.get("responseDesc", "")}
        except Exception as e:
            return {"success": False, "message": str(e)}
