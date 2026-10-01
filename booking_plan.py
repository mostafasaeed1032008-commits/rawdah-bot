# -*- coding: utf-8 -*-
"""
booking_plan.py
===============
Declarative Booking Instructions, Task Definitions, and Result Records.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union, Dict, Any, Tuple
from datetime import datetime


@dataclass
class PassengerTask:
    """
    بيانات وتعليمات المعتمر المطلوب الحجز له
    """
    name: str                                  # اسم المعتمر
    gender: str = "رجال"                        # رجال أو نساء (male / female)
    national_id: str = ""                      # رقم الهوية / الإقامة / جواز السفر
    nationality: str = "مصر"                   # الجنسية
    dob: str = ""                              # تاريخ الميلاد (YYYY-MM-DD)
    mobile: str = ""                           # رقم الجوال
    email: str = ""                            # البريد الإلكتروني
    password: str = "Zxcv1234$"                # كلمة المرور
    is_registered: bool = True                 # هل يمتلك حساباً مسجلاً بالفعل؟ (False -> إنشاء حساب جديد)
    has_active_permit: bool = False            # هل لديه تصريح سابق؟
    clone_id: Optional[int] = None             # رقم الـ Clone المخصص له (إذا ترك فارغاً يتم التوزيع تلقائياً)
    auto_logout: bool = False                  # هل يتم تسجيل الخروج بعد انتهاء العملية؟
    custom_notes: str = ""                     # أي ملاحظات أو تعليمات خاصة

    def validate(self) -> Tuple[bool, str]:
        """التحقق من صحة واكتمال الحقول الأساسية قبل البدء"""
        if not self.name or not self.name.strip():
            return False, "اسم المعتمر / المستخدم مطلوب"
        if self.is_registered and not (self.email or self.national_id):
            return False, f"المعتمر {self.name}: يلزم توفر البريد الإلكتروني أو رقم الهوية للحساب المسجل"
        if not self.is_registered and not (self.email and self.password):
            return False, f"المعتمر {self.name}: يلزم توفر البريد وكلمة المرور لإنشاء حساب جديد"
        return True, ""


@dataclass
class BookingSession:
    """
    خطة وجلسة الحجز الكاملة المحددة عبر الكود
    """
    session_name: str = "حجز الروضة الشريفة"
    target_date: str = ""                      # التاريخ المطلوب بصيغة YYYY-MM-DD أو فارغ لأول موعد متاح
    target_period: str = "All"                 # الفترات: الفجر، الظهر، العصر، المغرب، العشاء، All
    preferred_times: List[str] = field(default_factory=lambda: ["08:00", "09:30", "14:00", "20:00"])
    max_fallback_days: int = 3                 # عدد الأيام البديلة المسموح بالبحث فيها إن لم يتوفر التاريخ الأساسي

    # إعدادات الـ Clones
    clone_range: Union[range, List[int], str] = field(default_factory=lambda: range(1, 46)) # نطاق النسخ المطلوب (1 إلى 45)
    close_clone_after_finish: bool = True      # إغلاق كل نسخة فور اكتمالها قبل فتح النسخة التالية
    clean_memory_between_clones: bool = True   # تنظيف الذاكرة ومسح الكاش بين النسخ

    # المعتمرين
    passengers: List[PassengerTask] = field(default_factory=list)

    # سلوك الأخطاء
    on_error: str = "retry_and_continue"       # 'retry_and_continue', 'skip_clone', 'stop'
    max_retries: int = 2                       # عدد محاولات إعادة المحاولة عند حدوث خطأ
    link_children: bool = True                 # هل يتم ربط التابعين والأطفال تلقائياً؟

    def get_clone_list(self) -> List[int]:
        """تحويل نطاق النسخ إلى قائمة أرقام محددة"""
        if isinstance(self.clone_range, range):
            return list(self.clone_range)
        elif isinstance(self.clone_range, list):
            return self.clone_range
        elif isinstance(self.clone_range, str):
            if "-" in self.clone_range:
                start, end = self.clone_range.split("-")
                return list(range(int(start.strip()), int(end.strip()) + 1))
            elif self.clone_range.lower() == "all":
                return list(range(1, 46))
            else:
                return [int(self.clone_range.strip())]
        return list(range(1, 46))


@dataclass
class BookingResult:
    """
    تقرير نتيجة الحجز لكل معتمر / Clone
    """
    clone_id: int
    passenger_name: str
    status: str                                # 'SUCCESS', 'FAILED', 'ALREADY_BOOKED', 'FULLY_BOOKED', 'WAITING_LIST', 'INSTANT_TRACK', 'SECURITY_CHALLENGE', 'ERROR', 'PAUSED'
    permit_details: str = ""                   # تفاصيل التصريح وتاريخه ووقته
    error_reason: str = ""                     # سبب الفشل إن وجد
    action_taken: str = ""                     # ما تم فعله (إنشاء حساب، تسجيل دخول، حجز، قائمة انتظار)
    waiting_list_status: str = ""              # حالة قائمة الانتظار
    instant_track_status: str = ""             # حالة المسار الفوري
    diagnostic_artifacts: List[str] = field(default_factory=list) # مسارات الصور والـ XML المحفوظة
    execution_time_seconds: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clone_id": self.clone_id,
            "passenger_name": self.passenger_name,
            "status": self.status,
            "permit_details": self.permit_details,
            "error_reason": self.error_reason,
            "action_taken": self.action_taken,
            "waiting_list_status": self.waiting_list_status,
            "instant_track_status": self.instant_track_status,
            "diagnostic_artifacts": self.diagnostic_artifacts,
            "execution_time_seconds": self.execution_time_seconds,
            "timestamp": self.timestamp,
        }
