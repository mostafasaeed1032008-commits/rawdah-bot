# -*- coding: utf-8 -*-
"""
app_server.py
=============
NusukBot PC Web Dashboard & Local Controller Server.
Provides local REST API, live screen mirroring, preflight diagnostics,
results inspection, and multi-clone sequential execution.
"""

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import http.server
import socketserver
import json
import os
import urllib.parse
import webbrowser
import time
import threading
from typing import Optional, Dict, Any
from nusuk_engine import NusukEngine
from excel_manager import ExcelManager
from booking_plan import BookingSession, PassengerTask
from sequential_runner import SequentialRunner

engine = NusukEngine()
current_runner: Optional[SequentialRunner] = None
runner_thread: Optional[threading.Thread] = None


class NusukApiHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        web_dir = os.path.join(os.path.dirname(__file__), "web_gui")
        super().__init__(*args, directory=web_dir, **kwargs)

    def log_message(self, format, *args):
        # Suppress verbose HTTP server logs in stdout
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/status":
            self._send_json(engine.get_status_dict())

        elif parsed.path == "/api/preflight":
            preflight = engine.dm.run_preflight(engine.config.get("nusuk_package", "com.moh.nusukapp"))
            self._send_json(preflight)

        elif parsed.path == "/api/results":
            self._send_json(engine.load_results())

        elif parsed.path == "/api/diagnostics":
            diag = {
                "engine_state": engine.state.value,
                "is_running": engine.is_running,
                "is_connected": engine.adb.is_connected(),
                "device_info": engine.device_info.to_dict() if engine.device_info else None,
                "screen_size": engine.adb.get_screen_size(),
                "focused_activity": engine.adb.get_focused_activity(),
                "last_error": engine.last_error,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self._send_json(diag)

        elif parsed.path == "/api/clones":
            try:
                from clone_manager import CloneManager
                cm = CloneManager(engine.adb.adb, engine.adb.serial)
                clones = []
                for cid in sorted(cm._user_map.keys()):
                    label = "التطبيق الأساسي (Main App)" if cid == 0 else f"Clone #{cid}"
                    clones.append({
                        "id": cid,
                        "label": label,
                        "user_id": cm.get_user_id_for_clone(cid),
                        "is_active": (cm.active_clone_id == cid)
                    })
                self._send_json({"success": True, "clones": clones})
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "clones": []})

        elif parsed.path == "/api/screenshot":
            sc_path = engine.adb.screencap("live_preview.png")
            if os.path.exists(sc_path):
                try:
                    with open(sc_path, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                except Exception:
                    self.send_response(500)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        elif parsed.path == "/api/logs":
            self._send_json({"logs": engine.logs})

        else:
            super().do_GET()

    def do_POST(self):
        global current_runner, runner_thread
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(length) if length > 0 else b"{}"

        try:
            body = json.loads(post_data.decode("utf-8"))
        except Exception:
            body = {}

        if parsed.path == "/api/start":
            ok, msg = engine.start_booking()
            self._send_json({"success": ok, "message": msg})

        elif parsed.path == "/api/stop":
            engine.stop_booking()
            if current_runner:
                current_runner.is_running = False
            self._send_json({"success": True, "message": "تم إيقاف البوت"})

        elif parsed.path == "/api/resume":
            if engine.is_running:
                self._send_json({"success": False, "message": "الجلسة تعمل بالفعل"})
                return
            ok, msg = engine.start_booking()
            self._send_json({"success": ok, "message": "تم استئناف الجلسة"})

        elif parsed.path == "/api/run_code_plan":
            if engine.is_running or (current_runner and current_runner.is_running):
                self._send_json({"success": False, "message": "توجد عملية قيد التشغيل حالياً."})
                return

            clone_start = int(body.get("clone_start", 1))
            clone_end = int(body.get("clone_end", 1))
            target_date = body.get("target_date", "")
            target_period = body.get("target_period", "All")

            session = BookingSession(
                session_name=body.get("session_name", "خطة الحجز بالكود"),
                target_date=target_date,
                target_period=target_period,
                clone_range=range(clone_start, clone_end + 1),
                close_clone_after_finish=True,
                clean_memory_between_clones=True,
                passengers=[]
            )

            for p in body.get("passengers", []):
                session.passengers.append(PassengerTask(
                    name=p.get("name", "معتمر"),
                    gender=p.get("gender", "رجال"),
                    national_id=p.get("national_id", ""),
                    email=p.get("email", ""),
                    password=p.get("password", "Zxcv1234$"),
                    is_registered=p.get("is_registered", True),
                    auto_logout=p.get("auto_logout", False)
                ))

            try:
                current_runner = SequentialRunner(session, config_dict=engine.config, log_callback=engine.log)
            except Exception as exc:
                self._send_json({"success": False, "message": f"تعذر تجهيز الجهاز: {exc}"})
                return

            runner_thread = threading.Thread(target=current_runner.run, daemon=True)
            runner_thread.start()
            self._send_json({"success": True, "message": f"تم بدء التنفيذ التسلسلي للنسخ من {clone_start} إلى {clone_end}."})

        elif parsed.path == "/api/save_config":
            engine.save_config(body)
            self._send_json({"success": True, "message": "تم حفظ الإعدادات"})

        elif parsed.path == "/api/tap":
            try:
                w, h = engine.adb.get_screen_size()
                x = max(0, min(w - 1, int(body.get("x", w // 2))))
                y = max(0, min(h - 1, int(body.get("y", h // 2))))
                engine.adb.tap(x, y)
                self._send_json({"success": True, "x": x, "y": y})
            except Exception as e:
                self._send_json({"success": False, "message": f"إحداثيات غير صالحة: {e}"})

        elif parsed.path == "/api/back":
            engine.adb.press_back()
            self._send_json({"success": True})

        elif parsed.path == "/api/launch_app":
            engine.adb.launch_app()
            self._send_json({"success": True})

        elif parsed.path == "/api/ai_analyze":
            sc_path = engine.adb.screencap("ai_req.png")
            instruction = body.get("instruction", "تحليل الشاشة الحالية واقتراح الخطوة التالية")
            res = engine.ai_agent.think_and_act(sc_path, instruction, execute_action=False)
            self._send_json(res)

        elif parsed.path == "/api/import_excel":
            file_path = body.get("file_path", "")
            if not file_path or not os.path.exists(file_path):
                sample = os.path.join(os.path.dirname(__file__), "sample_passengers.csv")
                if os.path.exists(sample):
                    file_path = sample
            passengers = ExcelManager.parse_file(file_path, engine.config.get("link_children", True))
            engine.passengers = passengers
            self._send_json({"success": True, "count": len(passengers), "file": os.path.basename(file_path)})

        elif parsed.path == "/api/generate_dot_trick":
            base_email = body.get("email") or engine.config.get("gmail_user", "")
            count = int(body.get("count", 5))
            passengers = ExcelManager.generate_dot_trick_passengers(base_email, count)
            engine.passengers = passengers
            self._send_json({
                "success": True,
                "count": len(passengers),
                "passengers": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "email": p.email,
                        "person_type": p.person_type,
                        "booking_status": p.booking_status
                    } for p in passengers
                ]
            })

        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def run_server(port: int = 5000, auto_open: bool = True):
    socketserver.TCPServer.allow_reuse_address = True
    for p in [port, 5001, 5002, 5050, 8080]:
        try:
            httpd = ReusableTCPServer(("", p), NusukApiHandler)
            print("=" * 60)
            print(f"  NusukBot Dashboard is running at: http://localhost:{p}")
            print("=" * 60)

            if auto_open:
                def open_browser():
                    time.sleep(1.0)
                    webbrowser.open(f"http://localhost:{p}")
                threading.Thread(target=open_browser, daemon=True).start()

            httpd.serve_forever()
            break
        except OSError:
            continue


if __name__ == "__main__":
    p = 5000
    if len(sys.argv) > 1:
        try:
            p = int(sys.argv[1])
        except ValueError:
            pass
    run_server(p)
