# -*- coding: utf-8 -*-
"""
excel_manager.py
================
Parses and exports passenger/account data from Excel (.xlsx, .xls) and CSV files.
Supports Arabic and English headers, child linking, row validation, and result export.
"""

import os
import re
import csv
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


@dataclass
class Passenger:
    id: int = 0
    name: str = ""
    passport_no: str = ""
    visa_no: str = ""
    dob: str = ""
    email: str = ""
    mobile: str = ""
    person_type: str = "رجال"
    is_child: bool = False
    assigned_parent_name: str = ""
    booking_status: str = "⏳ قيد الانتظار"
    booking_date: str = ""
    booking_slot: str = ""
    booking_period: str = ""
    note: str = ""

    def validate(self) -> Tuple[bool, str]:
        """التحقق من صحة بيانات المعتمر الأساسية"""
        if not self.name or not self.name.strip():
            return False, f"المعتمر رقم {self.id}: الاسم مفقود"
        return True, ""


class ExcelManager:
    HEADER_ALIASES = {
        "name": ["الاسم", "اسم", "name", "full name", "fullname", "passenger", "المعتمر"],
        "passport": ["الجواز", "جواز", "passport", "passport_no", "passport number", "رقم الجواز"],
        "visa": ["التأشيرة", "التاشيرة", "تأشيرة", "تاشيرة", "visa", "visa_no", "visa number", "رقم التأشيرة"],
        "dob": ["تاريخ الميلاد", "الميلاد", "dob", "birth_date", "birthdate", "date_of_birth", "تاريخ ميلاد"],
        "email": [
            "الإيميل", "الايميل", "إيميل", "ايميل", "email", "e-mail", "mail", "gmail",
            "البريد", "بريد", "البريد الالكتروني", "البريد الإلكتروني", "حساب", "الحساب",
            "user", "username", "account", "login"
        ],
        "type": ["النوع", "الجنس", "فئة", "type", "gender", "person_type"],
        "mobile": ["الجوال", "الموبايل", "الهاتف", "mobile", "phone", "phone_number", "رقم الجوال"],
        "status": ["حالة الحجز", "الحالة", "status", "booking_status", "booking status"],
        "date": ["تاريخ الحجز", "التاريخ", "date", "booking_date"],
        "slot": ["الوقت", "الفترة", "slot", "booking_slot", "time"],
        "note": ["ملاحظات", "ملاحظة", "note", "notes", "comment"]
    }

    @classmethod
    def match_header(cls, col_name: str) -> Optional[str]:
        if not col_name:
            return None
        c = str(col_name).strip().lower()
        for field_key, aliases in cls.HEADER_ALIASES.items():
            for alias in aliases:
                if alias == c or alias in c:
                    return field_key
        return None

    @staticmethod
    def parse_file(file_path: str, link_children: bool = True) -> List[Passenger]:
        if not file_path or not os.path.exists(file_path):
            return []
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".xlsx", ".xls"]:
            return ExcelManager._parse_excel(file_path, link_children)
        elif ext in [".csv", ".txt"]:
            return ExcelManager._parse_csv(file_path, link_children)
        return []

    @staticmethod
    def _parse_excel(file_path: str, link_children: bool) -> List[Passenger]:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet = wb.active
        passengers: List[Passenger] = []
        p_id = 1

        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            wb.close()
            return []

        first_row = rows[0]
        header_map: Dict[str, int] = {}
        for idx, val in enumerate(first_row):
            if val is None:
                continue
            matched = ExcelManager.match_header(str(val))
            if matched and matched not in header_map:
                header_map[matched] = idx

        # Fallback check: single column with email list
        is_email_list = ("email" in header_map or (len(header_map) == 0 and "@" in str(first_row[0] or "")))
        start_idx = 1 if len(header_map) > 0 else 0

        for row in rows[start_idx:]:
            if not row or all(v is None for v in row):
                continue

            if is_email_list and "name" not in header_map:
                email_idx = header_map.get("email", 0)
                email_val = str(row[email_idx] or "").strip()
                if not email_val or "@" not in email_val:
                    continue
                status_val = str(row[1] or "").strip() if len(row) > 1 and row[1] else "⏳ قيد الانتظار"
                if status_val == "تم":
                    status_val = "✅ تم الحجز"
                derived_name = email_val.split("@")[0].replace(".", " ").title()
                passengers.append(Passenger(
                    id=p_id,
                    name=derived_name,
                    email=email_val,
                    booking_status=status_val
                ))
                p_id += 1
            else:
                def get_val(key: str, default: str = "") -> str:
                    idx = header_map.get(key)
                    if idx is not None and idx < len(row) and row[idx] is not None:
                        return str(row[idx]).strip()
                    return default

                name = get_val("name")
                email_val = get_val("email")
                passport = get_val("passport")
                visa = get_val("visa")
                dob = get_val("dob")
                mobile = get_val("mobile")
                p_type = get_val("type", "رجال")
                status = get_val("status", "⏳ قيد الانتظار")
                note = get_val("note")

                # Auto-detect email from any cell in row if not matched by header
                if not email_val or "@" not in email_val:
                    for cell in row:
                        if cell is not None and "@" in str(cell) and "." in str(cell):
                            email_val = str(cell).strip()
                            break

                # If name is empty, try deriving from email or skip
                if not name:
                    if email_val and "@" in email_val:
                        name = email_val.split("@")[0].replace(".", " ").title()
                    else:
                        continue

                is_child = ("طفل" in p_type or "child" in p_type.lower())
                passengers.append(Passenger(
                    id=p_id,
                    name=name,
                    passport_no=passport,
                    visa_no=visa,
                    dob=dob,
                    email=email_val,
                    mobile=mobile,
                    person_type=p_type,
                    is_child=is_child,
                    booking_status=status,
                    note=note
                ))
                p_id += 1

        wb.close()
        if link_children:
            ExcelManager._link_family_companions(passengers)
        return passengers

    @staticmethod
    def _parse_csv(file_path: str, link_children: bool) -> List[Passenger]:
        passengers: List[Passenger] = []
        p_id = 1

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            rows = [r for r in reader if any(field.strip() for field in r)]

        if not rows:
            return []

        first_row = rows[0]
        header_map: Dict[str, int] = {}
        for idx, val in enumerate(first_row):
            matched = ExcelManager.match_header(val)
            if matched and matched not in header_map:
                header_map[matched] = idx

        start_idx = 1 if len(header_map) > 0 else 0
        for row in rows[start_idx:]:
            if not row or not any(field.strip() for field in row):
                continue

            def get_val(key: str, default: str = "") -> str:
                idx = header_map.get(key)
                if idx is not None and idx < len(row):
                    return row[idx].strip()
                return default

            if len(header_map) == 0:
                # Raw list (first column might be email)
                val0 = row[0].strip()
                if "@" in val0:
                    derived_name = val0.split("@")[0].replace(".", " ").title()
                    status = row[1].strip() if len(row) > 1 and row[1].strip() else "⏳ قيد الانتظار"
                    passengers.append(Passenger(id=p_id, name=derived_name, email=val0, booking_status=status))
                    p_id += 1
                continue

            name = get_val("name")
            email_val = get_val("email")
            passport = get_val("passport")
            visa = get_val("visa")
            mobile = get_val("mobile")
            p_type = get_val("type", "رجال")
            status = get_val("status", "⏳ قيد الانتظار")
            note = get_val("note")

            # Auto-detect email from any cell in row if not matched by header
            if not email_val or "@" not in email_val:
                for cell in row:
                    if cell and "@" in str(cell) and "." in str(cell):
                        email_val = str(cell).strip()
                        break

            if not name:
                if email_val and "@" in email_val:
                    name = email_val.split("@")[0].replace(".", " ").title()
                else:
                    continue

            is_child = ("طفل" in p_type or "child" in p_type.lower())
            passengers.append(Passenger(
                id=p_id,
                name=name,
                passport_no=passport,
                visa_no=visa,
                email=email_val,
                mobile=mobile,
                person_type=p_type,
                is_child=is_child,
                booking_status=status,
                note=note
            ))
            p_id += 1

        if link_children:
            ExcelManager._link_family_companions(passengers)
        return passengers

    @staticmethod
    def generate_dot_trick_passengers(base_email: str, count: int = 5, base_name: str = "معتمر") -> List[Passenger]:
        """
        Generates test passengers using Gmail dot trick aliases.
        All aliases route to the same base Gmail inbox for OTP verification.
        """
        base_email = (base_email or "").strip().lower()
        if "@" not in base_email:
            return []
        user_part, domain = base_email.split("@", 1)
        clean_user = user_part.replace(".", "")
        if len(clean_user) < 2:
            return [Passenger(id=1, name=base_name, email=base_email)]

        passengers: List[Passenger] = []
        # First passenger with base email
        passengers.append(Passenger(
            id=1,
            name=f"{base_name} 1",
            email=base_email,
            person_type="رجال",
            booking_status="⏳ قيد الانتظار"
        ))

        # Dot variants
        step = max(1, len(clean_user) // (count + 1))
        added_emails = {base_email}
        for idx in range(1, count):
            pos = min(len(clean_user) - 1, idx * step)
            variant = f"{clean_user[:pos]}.{clean_user[pos:]}@{domain}"
            if variant not in added_emails:
                added_emails.add(variant)
                passengers.append(Passenger(
                    id=len(passengers) + 1,
                    name=f"{base_name} {len(passengers) + 1}",
                    email=variant,
                    person_type="رجال",
                    booking_status="⏳ قيد الانتظار"
                ))
        return passengers

    @staticmethod
    def _link_family_companions(passengers: List[Passenger]):
        adults = [p for p in passengers if not p.is_child]
        children = [p for p in passengers if p.is_child]
        for child in children:
            child_tokens = set(re.findall(r"\w+", child.name))
            best_match, max_common = None, 0
            for adult in adults:
                adult_tokens = set(re.findall(r"\w+", adult.name))
                common = len(child_tokens.intersection(adult_tokens))
                if common > max_common:
                    max_common = common
                    best_match = adult
            if best_match and max_common >= 1:
                child.assigned_parent_name = best_match.name
                child.note = f"مرافق مع: {best_match.name}"

    @staticmethod
    def export_permits(passengers: List[Passenger], output_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "تصاريح الروضة الشريفة"
        ws.sheet_view.rightToLeft = True
        headers = ["م", "الاسم / الحساب", "البريد الإلكتروني", "رقم الجواز", "رقم التأشيرة", "رقم الجوال", "النوع", "حالة الحجز", "تاريخ الحجز", "الفترة", "الوقت", "ملاحظات"]
        ws.append(headers)

        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1B5E20", end_color="1B5E20", fill_type="solid")
        border = Border(
            left=Side(style="thin", color="CCCCCC"),
            right=Side(style="thin", color="CCCCCC"),
            top=Side(style="thin", color="CCCCCC"),
            bottom=Side(style="thin", color="CCCCCC")
        )
        for col_idx, _ in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for p in passengers:
            row_data = [p.id, p.name, p.email, p.passport_no, p.visa_no, p.mobile, p.person_type, p.booking_status, p.booking_date, p.booking_period, p.booking_slot, p.note]
            ws.append(row_data)
            curr_row = ws.max_row
            status_cell = ws.cell(row=curr_row, column=8)
            if "تم" in p.booking_status or "done" in p.booking_status.lower() or "مؤكد" in p.booking_status:
                status_cell.fill = PatternFill(start_color="C8E6C9", end_color="C8E6C9", fill_type="solid")
            elif "فشل" in p.booking_status or "error" in p.booking_status.lower():
                status_cell.fill = PatternFill(start_color="FFCDD2", end_color="FFCDD2", fill_type="solid")
            for c in range(1, len(headers) + 1):
                ws.cell(row=curr_row, column=c).border = border
                ws.cell(row=curr_row, column=c).alignment = Alignment(horizontal="center", vertical="center")

        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
        wb.save(output_path)
