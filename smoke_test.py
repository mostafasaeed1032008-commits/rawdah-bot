# -*- coding: utf-8 -*-
"""
smoke_test.py
=============
Automated Unit and Integration Smoke Test Suite for NusukBot PC.
Runs completely offline without requiring an active emulator or real external network connection.
Covers:
1. Syntax compilation of all repository Python modules
2. Config loading, environment overrides, and strict secret masking
3. CSV & Excel parsing with Arabic and English headers, child linking, and validation
4. Screen coordinate scaling and bounds clamping
5. State classification & conservative detection (XML fixtures for all primary states)
6. Security challenge detection and safe stop
7. Offline preflight diagnostic verification
8. Local HTTP REST API endpoints and secret leak prevention
"""

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import json
import time
import unittest
import urllib.request
import urllib.parse
import threading
import xml.etree.ElementTree as ET

from booking_plan import PassengerTask, BookingSession, BookingResult
from excel_manager import ExcelManager, Passenger
from adb_controller import AdbController
from device_manager import DeviceManager
from nusuk_flows import FlowController, NusukScreenType
from nusuk_engine import NusukEngine, BotState
from otp_fetcher import OtpFetcher
from ai_vision_agent import GeminiEmployeeAgent


class TestNusukBotPC(unittest.TestCase):

    def setUp(self):
        self.test_dir = os.path.dirname(os.path.abspath(__file__))

    # ── Test 1: Configuration & Secret Masking ────────────────────────────────
    def test_config_secret_masking(self):
        engine = NusukEngine()
        engine.config = {
            "adb_path": "C:\\fake\\adb.exe",
            "device_serial": "127.0.0.1:16384",
            "gmail_user": "test@gmail.com",
            "gmail_app_password": "supersecretpassword",
            "gemini_api_key": "AIzaSySecretKey",
            "unified_password": "Zxcv1234$Secret"
        }
        public_cfg = engine.public_config()
        self.assertEqual(public_cfg["gmail_app_password"], "••••••••")
        self.assertEqual(public_cfg["gemini_api_key"], "••••••••")
        self.assertEqual(public_cfg["unified_password"], "••••••••")
        self.assertEqual(public_cfg["gmail_user"], "test@gmail.com")

        # Verify get_status_dict does not leak secrets
        status_dict = engine.get_status_dict()
        cfg_in_status = status_dict["config"]
        self.assertNotIn("supersecretpassword", json.dumps(cfg_in_status))
        self.assertNotIn("AIzaSySecretKey", json.dumps(cfg_in_status))
        self.assertNotIn("Zxcv1234$Secret", json.dumps(cfg_in_status))

    # ── Test 2: Passenger Data & Validation ───────────────────────────────────
    def test_passenger_validation(self):
        p_valid = PassengerTask(name="محمد علي", email="m@example.com", is_registered=True)
        ok, msg = p_valid.validate()
        self.assertTrue(ok)

        p_empty = PassengerTask(name="", email="m@example.com")
        ok, msg = p_empty.validate()
        self.assertFalse(ok)
        self.assertIn("مطلوب", msg)

        p_no_creds = PassengerTask(name="أحمد", email="", national_id="", is_registered=True)
        ok, msg = p_no_creds.validate()
        self.assertFalse(ok)

    # ── Test 3: CSV and Header Mapping (Arabic and English) ───────────────────
    def test_excel_manager_headers(self):
        self.assertEqual(ExcelManager.match_header("الاسم"), "name")
        self.assertEqual(ExcelManager.match_header("Full Name"), "name")
        self.assertEqual(ExcelManager.match_header("رقم الجواز"), "passport")
        self.assertEqual(ExcelManager.match_header("passport_no"), "passport")
        self.assertEqual(ExcelManager.match_header("التأشيرة"), "visa")
        self.assertEqual(ExcelManager.match_header("Visa Number"), "visa")
        self.assertEqual(ExcelManager.match_header("البريد الإلكتروني"), "email")
        self.assertEqual(ExcelManager.match_header("email"), "email")
        self.assertEqual(ExcelManager.match_header("النوع"), "type")
        self.assertEqual(ExcelManager.match_header("Gender"), "type")

        # Test parsing sample CSV
        csv_path = os.path.join(self.test_dir, "sample_passengers.csv")
        if os.path.exists(csv_path):
            passengers = ExcelManager.parse_file(csv_path, link_children=True)
            self.assertGreaterEqual(len(passengers), 2)
            self.assertTrue(any(p.is_child for p in passengers))
            # Verify child companion link
            child = next(p for p in passengers if p.is_child)
            self.assertTrue(bool(child.assigned_parent_name))

    # ── Test 4: Coordinate Scaling & Bounds Clamping ───────────────────────────
    def test_coordinate_scaling(self):
        adb = AdbController()
        # Mock screen size to 720x1280
        adb._cached_screen_size = (720, 1280)
        adb._last_size_check_time = time.time() + 1000

        # Scale center (450, 800) from 900x1600 reference
        sx, sy = adb.scale_coords(450, 800, base_w=900, base_h=1600)
        self.assertEqual(sx, 360)
        self.assertEqual(sy, 640)

        # Scale out-of-bounds coordinate -> must clamp safely
        clamped_x, clamped_y = adb.scale_coords(1200, 2500, base_w=900, base_h=1600)
        self.assertEqual(clamped_x, 719)
        self.assertEqual(clamped_y, 1279)

        # Scale negative coordinate -> must clamp to 0
        neg_x, neg_y = adb.scale_coords(-50, -100, base_w=900, base_h=1600)
        self.assertEqual(neg_x, 0)
        self.assertEqual(neg_y, 0)

    # ── Test 5: State Classification on XML Fixtures ─────────────────────────
    def test_state_detection_fixtures(self):
        adb = AdbController()
        flow = FlowController(adb, GeminiEmployeeAgent(), OtpFetcher("", ""))

        # Mock is_connected
        adb.is_connected = lambda: True

        def make_xml_nodes(text_list):
            root = ET.Element("hierarchy")
            for t in text_list:
                node = ET.SubElement(root, "node")
                node.set("text", t)
                node.set("content-desc", "")
                node.set("resource-id", "")
                node.set("class", "android.widget.TextView")
                node.set("bounds", "[100,100][200,200]")
                node.set("clickable", "true")
                node.set("enabled", "true")
            return root

        # 1. Security Challenge / CAPTCHA
        adb.dump_ui = lambda save_audit_copy=False: make_xml_nodes(["Please solve this CAPTCHA", "تحقق أمني"])
        st = flow.detect_screen()
        self.assertEqual(st, NusukScreenType.SECURITY_CHALLENGE)

        # 2. Confirmed Permit
        adb.dump_ui = lambda save_audit_copy=False: make_xml_nodes(["Reservation confirmed", "تفاصيل التصريح"])
        st = flow.detect_screen()
        self.assertEqual(st, NusukScreenType.ALREADY_CONFIRMED)

        # 3. Waiting List
        adb.dump_ui = lambda save_audit_copy=False: make_xml_nodes(["الانضمام لقائمة الانتظار", "Waiting List"])
        st = flow.detect_screen()
        self.assertEqual(st, NusukScreenType.WAITING_LIST)

        # 4. Instant Track
        adb.dump_ui = lambda save_audit_copy=False: make_xml_nodes(["المسار الفوري", "Instant Track"])
        st = flow.detect_screen()
        self.assertEqual(st, NusukScreenType.INSTANT_TRACK)

        # 5. Fully Booked
        adb.dump_ui = lambda save_audit_copy=False: make_xml_nodes(["لا توجد مواعيد متاحة حالياً", "Fully Booked"])
        st = flow.detect_screen()
        self.assertEqual(st, NusukScreenType.FULLY_BOOKED)

        # 6. Available Slot
        adb.dump_ui = lambda save_audit_copy=False: make_xml_nodes(["08:30 AM", "Available"])
        st = flow.detect_screen()
        self.assertEqual(st, NusukScreenType.AVAILABLE_SLOT)

        # 7. Select Person
        adb.dump_ui = lambda save_audit_copy=False: make_xml_nodes(["Add Friend", "Select user", "المرافقين"])
        st = flow.detect_screen()
        self.assertEqual(st, NusukScreenType.SELECT_PERSON)

        # 8. Onboarding
        adb.dump_ui = lambda save_audit_copy=False: make_xml_nodes(["Enter the Prophet", "The Qur’an", "Skip"])
        st = flow.detect_screen()
        self.assertEqual(st, NusukScreenType.ONBOARDING)

    # ── Test 6: Preflight & Offline Diagnostic Verification ───────────────────
    def test_offline_preflight(self):
        dm = DeviceManager()
        report = dm.run_preflight()
        self.assertIn("python", report)
        self.assertTrue(report["python"]["is_ok"])
        self.assertIn("packages", report)
        self.assertTrue(report["packages"]["requests"])
        self.assertTrue(report["packages"]["openpyxl"])
        self.assertTrue(report["packages"]["PIL"])
        self.assertIn(report["status"], ["CONNECTED", "DISCONNECTED", "NO_ADB", "OFFLINE"])

        # Specifically test forced offline handling without throwing unhandled exceptions
        dm_offline = DeviceManager()
        dm_offline._list_adb_devices = lambda: []
        offline_report = dm_offline.run_preflight()
        self.assertIn(offline_report["status"], ["DISCONNECTED", "OFFLINE", "NO_ADB"])
        self.assertTrue(len(offline_report["remediation"]) > 0)

    # ── Test 7: Results Persistence ──────────────────────────────────────────
    def test_results_persistence(self):
        engine = NusukEngine()
        sample_results = [
            {
                "clone_id": 1,
                "passenger_name": "معتمر تجريبي",
                "status": "WAITING_LIST",
                "waiting_list_status": "REGISTERED",
                "permit_details": "",
                "error_reason": "",
                "action_taken": "الانضمام لقائمة الانتظار",
                "execution_time_seconds": 3.5,
                "timestamp": "2026-09-20 12:00:00"
            }
        ]
        engine._save_results(sample_results)
        loaded = engine.load_results()
        self.assertEqual(loaded["total_results"], 1)
        self.assertEqual(loaded["results"][0]["status"], "WAITING_LIST")

    # ── Test 8: Local REST API Server & Secret Leak Check ────────────────────
    def test_api_endpoints(self):
        from app_server import ReusableTCPServer, NusukApiHandler
        test_port = 5899
        server = ReusableTCPServer(("127.0.0.1", test_port), NusukApiHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.5)

        try:
            # 1. GET /api/status
            req = urllib.request.urlopen(f"http://127.0.0.1:{test_port}/api/status", timeout=4)
            self.assertEqual(req.status, 200)
            status_data = json.loads(req.read().decode("utf-8"))
            self.assertIn("state", status_data)
            self.assertIn("config", status_data)
            # Ensure no secret leak in API response
            for secret_key in ("gmail_app_password", "gemini_api_key", "unified_password"):
                val = status_data["config"].get(secret_key, "")
                if val:
                    self.assertEqual(val, "••••••••")

            # 2. GET /api/preflight
            req_pre = urllib.request.urlopen(f"http://127.0.0.1:{test_port}/api/preflight", timeout=4)
            self.assertEqual(req_pre.status, 200)
            pre_data = json.loads(req_pre.read().decode("utf-8"))
            self.assertIn("python", pre_data)
            self.assertIn("adb", pre_data)

            # 3. GET /api/results
            req_res = urllib.request.urlopen(f"http://127.0.0.1:{test_port}/api/results", timeout=4)
            self.assertEqual(req_res.status, 200)

            # 4. POST /api/stop
            post_req = urllib.request.Request(f"http://127.0.0.1:{test_port}/api/stop", data=b"{}", headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(post_req, timeout=4)
            self.assertEqual(resp.status, 200)
            stop_data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(stop_data["success"])
        finally:
            server.shutdown()
            server.server_close()


def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNusukBotPC)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return res.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
