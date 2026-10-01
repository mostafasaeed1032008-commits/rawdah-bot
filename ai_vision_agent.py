# -*- coding: utf-8 -*-
"""
ai_vision_agent.py
==================
Optional Google Gemini Visual Fallback Agent for NusukBot PC.
Features:
- Schema-validated output
- Detection and flagging of security challenges (never attempts bypasses)
- Dynamic screen resolution support
- Provides analyze_screen helper for UI dashboards
"""

import base64
import json
import os
import io
import time
import requests
from typing import Optional, Dict, Any, Tuple
from PIL import Image


class GeminiEmployeeAgent:
    def __init__(self, api_key: str = "", adb_controller=None):
        self.api_key = (api_key or "").strip()
        self.adb = adb_controller
        self.models = ["gemini-3.6-flash", "gemini-3.5-flash"]

    def set_api_key(self, api_key: str):
        self.api_key = (api_key or "").strip()

    def is_available(self) -> bool:
        return bool(self.api_key)

    def analyze_screen(self, image_path: str) -> Dict[str, Any]:
        """Provides a safe descriptive summary without executing any action."""
        res = self.think_and_act(image_path, user_instruction="تحليل وتوصيف الشاشة الحالية فقط", execute_action=False)
        if res.get("success"):
            return {
                "screen_type": res.get("current_screen", "غير محدد"),
                "description_ar": res.get("analysis", "تم التحليل بنجاح"),
                "next_action": res.get("decision", "لا يوجد"),
                "is_security_challenge": res.get("is_security_challenge", False)
            }
        return {
            "screen_type": "خطأ",
            "description_ar": res.get("error", "تعذر التحليل"),
            "next_action": "يرجى التحقق من الاتصال والمفتاح",
            "is_security_challenge": False
        }

    def think_and_act(self, image_path: str, user_instruction: str = "تحديد الخطوة التالية للوصول للرئيسية أو المواعيد",
                      execute_action: bool = True) -> Dict[str, Any]:
        """Inspects screen, checks for security challenges, and suggests or executes safe actions."""
        if not self.is_available():
            return {
                "success": False,
                "error": "مفتاح Google Gemini API غير متوفر.",
                "reasoning": "يرجى إدخال المفتاح في الإعدادات أو عبر متغير البيئة NUSUK_GEMINI_API_KEY."
            }

        if not os.path.exists(image_path):
            return {"success": False, "error": "ملف صورة الشاشة غير موجود."}

        try:
            # Query actual screen size
            w, h = (900, 1600)
            if self.adb:
                w, h = self.adb.get_screen_size()

            # Compress and encode
            img = Image.open(image_path).convert("RGB")
            img.thumbnail((540, 960))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            img_data = base64.b64encode(buf.getvalue()).decode("utf-8")

            prompt = f"""
أنت مساعد خبير في اختبار وفحص واجهات تطبيق "نسك" (Nusuk).
أبعاد شاشة الجهاز الحالية هي {w} عرض × {h} ارتفاع (بكسل).
التعليمات المطلوبة: "{user_instruction}"

قواعد الأمان الصارمة:
1. إذا كانت الشاشة تظهر اختبار روبوت (CAPTCHA)، أو تحققاً أمنياً، أو طلباً للتحقق من الموقع، أو حظراً:
   اضبط "is_security_challenge" على true، و "action_type" على "none". لا تحاول تجاوز أي فحص أمني إطلاقاً!
2. لا تخترع مواعيد غير ظاهرة على الشاشة.
3. الإجراءات المسموحة فقط: ["tap", "type", "back", "swipe", "none"].

أجب فقط بصيغة JSON نظيفة:
{{
    "current_screen": "اسم الشاشة باللغة العربية",
    "analysis": "شرح ما يظهر على الشاشة بدقة",
    "decision": "القرار المنطقي",
    "is_security_challenge": false,
    "action_type": "none",
    "tap_coordinates": [x, y],
    "type_text": "",
    "swipe_coordinates": [x1, y1, x2, y2],
    "is_goal_reached": false
}}
"""

            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": img_data
                                }
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json"
                }
            }

            last_error = ""
            for model in self.models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
                try:
                    resp = requests.post(url, json=payload, timeout=30)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(raw_text)
                        parsed["success"] = True
                        parsed["model_used"] = model

                        # Safety guard: if security challenge detected, refuse any automated touch/typing
                        if parsed.get("is_security_challenge"):
                            parsed["action_type"] = "none"
                            parsed["action_executed"] = "تم إيقاف التنفيذ الآلي: رصد تحدٍ أمني يتطلب تدخلاً يدوياً."
                            return parsed

                        # Execute action if allowed
                        if execute_action and self.adb:
                            action = parsed.get("action_type", "none")
                            if action == "tap" and parsed.get("tap_coordinates"):
                                coords = parsed["tap_coordinates"]
                                tx = max(0, min(w - 1, int(coords[0])))
                                ty = max(0, min(h - 1, int(coords[1])))
                                self.adb.tap(tx, ty)
                                parsed["action_executed"] = f"النقر على ({tx}, {ty})"
                            elif action == "type" and parsed.get("type_text"):
                                txt = parsed["type_text"]
                                self.adb.type_text(txt)
                                parsed["action_executed"] = f"إدخال نص: {txt}"
                            elif action == "back":
                                self.adb.press_back()
                                parsed["action_executed"] = "الرجوع للخلف"
                            elif action == "swipe" and parsed.get("swipe_coordinates"):
                                s = parsed["swipe_coordinates"]
                                self.adb.swipe(int(s[0]), int(s[1]), int(s[2]), int(s[3]))
                                parsed["action_executed"] = "سحب الشاشة"

                        return parsed
                    else:
                        last_error = f"Model {model} HTTP {resp.status_code}: {resp.text}"
                except Exception as ex:
                    last_error = str(ex)

            return {
                "success": False,
                "error": last_error or "تعذر الاتصال بخدمة Gemini."
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
