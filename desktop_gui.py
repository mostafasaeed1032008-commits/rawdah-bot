# -*- coding: utf-8 -*-
"""
desktop_gui.py
==============
NusukBot PC - Native Windows Desktop GUI
Tkinter dark theme interface with live preview, Excel/CSV manager, and safe automation triggers.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import os
from PIL import Image, ImageTk

from nusuk_engine import NusukEngine, BotState
from excel_manager import ExcelManager


class NusukDesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🕋 NusukBot PC - لوحة التحكم المكتبية")
        self.root.geometry("1150x780")
        self.root.minsize(1000, 700)
        self.root.configure(bg="#0f172a")

        self.engine = NusukEngine()
        self.current_img_tk = None
        self.is_updating_screen = True

        self._setup_styles()
        self._build_ui()
        self._load_initial_data()

        # Start background polling
        self.engine.log_callbacks.append(self.append_log)
        threading.Thread(target=self._auto_refresh_loop, daemon=True).start()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Treeview",
                        background="#1e293b",
                        foreground="#f8fafc",
                        fieldbackground="#1e293b",
                        rowheight=26,
                        font=("Segoe UI", 9))
        style.configure("Treeview.Heading",
                        background="#334155",
                        foreground="#f8fafc",
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#059669")])

    def _build_ui(self):
        # 1. Header Bar
        header = tk.Frame(self.root, bg="#1e293b", height=65, padx=20, pady=10)
        header.pack(fill=tk.X, side=tk.TOP)

        title_lbl = tk.Label(header, text="🕋 NusukBot PC", font=("Segoe UI", 16, "bold"), fg="#10b981", bg="#1e293b")
        title_lbl.pack(side=tk.LEFT)

        subtitle_lbl = tk.Label(header, text=" |  منظومة فحص وأتمتة واجهة نسك", font=("Segoe UI", 10), fg="#94a3b8", bg="#1e293b")
        subtitle_lbl.pack(side=tk.LEFT, padx=5)

        self.btn_stop = tk.Button(header, text="⛔ إيقاف", font=("Segoe UI", 10, "bold"), bg="#dc2626", fg="white", activebackground="#b91c1c", padx=15, pady=4, relief=tk.FLAT, cursor="hand2", command=self.stop_bot)
        self.btn_stop.pack(side=tk.RIGHT, padx=5)
        self.btn_stop.pack_forget()

        self.btn_start = tk.Button(header, text="⚡ بدء التشغيل", font=("Segoe UI", 11, "bold"), bg="#059669", fg="white", activebackground="#047857", padx=20, pady=5, relief=tk.FLAT, cursor="hand2", command=self.start_bot)
        self.btn_start.pack(side=tk.RIGHT, padx=5)

        self.lbl_status = tk.Label(header, text="○ غير متصل", font=("Segoe UI", 10, "bold"), fg="#ef4444", bg="#1e293b")
        self.lbl_status.pack(side=tk.RIGHT, padx=15)

        # 2. Main Body Container
        body = tk.Frame(self.root, bg="#0f172a", padx=15, pady=15)
        body.pack(fill=tk.BOTH, expand=True)

        left_col = tk.Frame(body, bg="#0f172a")
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # Stats Cards
        stats_frame = tk.Frame(left_col, bg="#0f172a")
        stats_frame.pack(fill=tk.X, pady=(0, 10))

        self.card_total = self._create_card(stats_frame, "المعتمرين المحملين", "0", "#38bdf8")
        self.card_done = self._create_card(stats_frame, "المكتملين بنجاح", "0", "#34d399")
        self.card_status = self._create_card(stats_frame, "حالة النظام", "جاهز", "#fbbf24")

        # Table Frame
        table_frame = tk.LabelFrame(left_col, text=" قائمة المعتمرين والتصاريح ", font=("Segoe UI", 11, "bold"), fg="#f8fafc", bg="#1e293b", padx=10, pady=10)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        tb_toolbar = tk.Frame(table_frame, bg="#1e293b")
        tb_toolbar.pack(fill=tk.X, pady=(0, 8))

        btn_import = tk.Button(tb_toolbar, text="📥 استيراد Excel / CSV", font=("Segoe UI", 9, "bold"), bg="#334155", fg="white", padx=10, pady=3, relief=tk.FLAT, cursor="hand2", command=self.import_excel)
        btn_import.pack(side=tk.LEFT, padx=3)

        btn_export = tk.Button(tb_toolbar, text="📤 تصدير النتائج", font=("Segoe UI", 9, "bold"), bg="#065f46", fg="#6ee7b7", padx=10, pady=3, relief=tk.FLAT, cursor="hand2", command=self.export_excel)
        btn_export.pack(side=tk.LEFT, padx=3)

        btn_reset = tk.Button(tb_toolbar, text="🔄 إعادة تعيين الحالة", font=("Segoe UI", 9, "bold"), bg="#1e3a8a", fg="#93c5fd", padx=10, pady=3, relief=tk.FLAT, cursor="hand2", command=self.reset_all_status)
        btn_reset.pack(side=tk.LEFT, padx=3)

        btn_clear = tk.Button(tb_toolbar, text="🗑 مسح", font=("Segoe UI", 9), bg="#475569", fg="white", padx=10, pady=3, relief=tk.FLAT, cursor="hand2", command=self.clear_passengers)
        btn_clear.pack(side=tk.RIGHT, padx=3)

        cols = ("id", "name", "email", "passport", "visa", "type", "status", "note")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=8)
        self.tree.heading("id", text="م")
        self.tree.heading("name", text="الاسم")
        self.tree.heading("email", text="البريد الإلكتروني")
        self.tree.heading("passport", text="الجواز")
        self.tree.heading("visa", text="التأشيرة")
        self.tree.heading("type", text="النوع")
        self.tree.heading("status", text="حالة الحجز")
        self.tree.heading("note", text="ملاحظات")

        self.tree.column("id", width=35, anchor=tk.CENTER)
        self.tree.column("name", width=120, anchor=tk.W)
        self.tree.column("email", width=180, anchor=tk.W)
        self.tree.column("passport", width=80, anchor=tk.CENTER)
        self.tree.column("visa", width=80, anchor=tk.CENTER)
        self.tree.column("type", width=60, anchor=tk.CENTER)
        self.tree.column("status", width=100, anchor=tk.CENTER)
        self.tree.column("note", width=150, anchor=tk.W)

        tree_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Log Box
        log_frame = tk.LabelFrame(left_col, text=" سجل الأحداث المباشر ", font=("Segoe UI", 10, "bold"), fg="#f8fafc", bg="#1e293b", padx=10, pady=8)
        log_frame.pack(fill=tk.X)

        self.log_txt = tk.Text(log_frame, bg="#020617", fg="#10b981", font=("Consolas", 9), height=7, wrap=tk.WORD)
        self.log_txt.pack(fill=tk.BOTH, expand=True)

        # Right Column (Screen & Settings)
        right_col = tk.Frame(body, bg="#0f172a", width=340)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(10, 0))

        screen_frame = tk.LabelFrame(right_col, text=" بث الشاشة المباشر ", font=("Segoe UI", 10, "bold"), fg="#f8fafc", bg="#1e293b", padx=10, pady=10)
        screen_frame.pack(fill=tk.X, pady=(0, 10))

        self.screen_canvas = tk.Label(screen_frame, bg="#000000", height=16, text="[شاشة المحاكي غير متصلة]", fg="#64748b")
        self.screen_canvas.pack(fill=tk.BOTH, expand=True)

        controls = tk.Frame(screen_frame, bg="#1e293b")
        controls.pack(fill=tk.X, pady=(6, 0))

        tk.Button(controls, text="◀ رجوع", bg="#334155", fg="white", relief=tk.FLAT, command=lambda: self.engine.adb.press_back()).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        tk.Button(controls, text="🚀 نسك", bg="#334155", fg="white", relief=tk.FLAT, command=lambda: self.engine.adb.launch_app()).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        tk.Button(controls, text="🤖 AI", bg="#4338ca", fg="white", relief=tk.FLAT, command=self.ask_ai).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # Settings
        cfg_frame = tk.LabelFrame(right_col, text=" الإعدادات السريعة ", font=("Segoe UI", 10, "bold"), fg="#f8fafc", bg="#1e293b", padx=10, pady=10)
        cfg_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(cfg_frame, text="وضع التشغيل:", bg="#1e293b", fg="#38bdf8", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)
        self.mode_var = tk.StringVar(value="api")
        mode_box = tk.Frame(cfg_frame, bg="#1e293b")
        mode_box.pack(fill=tk.X, pady=(0, 6))
        tk.Radiobutton(mode_box, text="⚡ REST API مباشر (سريع)", variable=self.mode_var, value="api", bg="#1e293b", fg="white", selectcolor="#0f172a", activebackground="#1e293b").pack(anchor=tk.W)
        tk.Radiobutton(mode_box, text="📱 محاكي أندرويد (MuMu ADB)", variable=self.mode_var, value="adb", bg="#1e293b", fg="white", selectcolor="#0f172a", activebackground="#1e293b").pack(anchor=tk.W)

        tk.Label(cfg_frame, text="الفترة المستهدفة:", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 8)).pack(anchor=tk.W)
        self.ent_period = tk.Entry(cfg_frame, bg="#334155", fg="white", relief=tk.FLAT)
        self.ent_period.pack(fill=tk.X, pady=(0, 4))

        tk.Label(cfg_frame, text="تاريخ الحجز المستهدف:", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 8)).pack(anchor=tk.W)
        self.ent_date = tk.Entry(cfg_frame, bg="#334155", fg="white", relief=tk.FLAT)
        self.ent_date.pack(fill=tk.X, pady=(0, 4))

        tk.Label(cfg_frame, text="Gmail (سحب OTP):", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 8)).pack(anchor=tk.W)
        self.ent_gmail = tk.Entry(cfg_frame, bg="#334155", fg="white", relief=tk.FLAT)
        self.ent_gmail.pack(fill=tk.X, pady=(0, 4))

        tk.Label(cfg_frame, text="Gmail App Password:", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 8)).pack(anchor=tk.W)
        self.ent_gmail_pass = tk.Entry(cfg_frame, bg="#334155", fg="white", relief=tk.FLAT, show="•")
        self.ent_gmail_pass.pack(fill=tk.X, pady=(0, 4))

        tk.Label(cfg_frame, text="Gemini API Key:", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 8)).pack(anchor=tk.W)
        self.ent_gemini = tk.Entry(cfg_frame, bg="#334155", fg="white", relief=tk.FLAT, show="•")
        self.ent_gemini.pack(fill=tk.X, pady=(0, 8))

        tk.Button(cfg_frame, text="💾 حفظ الإعدادات", bg="#059669", fg="white", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, command=self.save_settings).pack(fill=tk.X)

    def _create_card(self, parent, title, val, color):
        card = tk.Frame(parent, bg="#1e293b", padx=12, pady=8)
        card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        tk.Label(card, text=title, font=("Segoe UI", 8), fg="#94a3b8", bg="#1e293b").pack(anchor=tk.W)
        lbl = tk.Label(card, text=val, font=("Segoe UI", 16, "bold"), fg=color, bg="#1e293b")
        lbl.pack(anchor=tk.W)
        return lbl

    def _load_initial_data(self):
        cfg = self.engine.config
        self.mode_var.set(cfg.get("engine_mode", "api"))
        self._set_entry(self.ent_period, cfg.get("target_period", "All"))
        self._set_entry(self.ent_date, cfg.get("target_date", ""))
        self._set_entry(self.ent_gmail, cfg.get("gmail_user", ""))
        if cfg.get("gmail_app_password"):
            self._set_entry(self.ent_gmail_pass, "••••••••")
        if cfg.get("gemini_api_key"):
            self._set_entry(self.ent_gemini, "••••••••")

        self.render_table()

    def _set_entry(self, entry: tk.Entry, value: str):
        entry.delete(0, tk.END)
        entry.insert(0, value or "")

    def append_log(self, text: str):
        def _insert():
            self.log_txt.insert(tk.END, text + "\n")
            self.log_txt.see(tk.END)
        self.root.after(0, _insert)

    def render_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for p in self.engine.passengers:
            self.tree.insert("", tk.END, values=(
                p.id, p.name or "-", p.email or "-", p.passport_no or "-", p.visa_no or "-", p.person_type, p.booking_status, p.note or "-"
            ))

        self.card_total.config(text=str(len(self.engine.passengers)))
        done_cnt = sum(1 for p in self.engine.passengers if "تم" in p.booking_status or "مؤكد" in p.booking_status)
        self.card_done.config(text=str(done_cnt))

    def import_excel(self):
        path = filedialog.askopenfilename(filetypes=[("Excel & CSV Files", "*.xlsx *.xls *.csv")])
        if path:
            passengers = ExcelManager.parse_file(path, self.engine.config.get("link_children", True))
            self.engine.passengers = passengers
            self.render_table()
            messagebox.showinfo("نجاح", f"تم استيراد {len(passengers)} حساب/معتمر بنجاح!")

    def export_excel(self):
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel Files", "*.xlsx")])
        if path:
            ExcelManager.export_permits(self.engine.passengers, path)
            messagebox.showinfo("نجاح", f"تم تصدير النتائج بنجاح إلى:\n{path}")

    def clear_passengers(self):
        self.engine.passengers = []
        self.render_table()

    def save_settings(self):
        cfg = {
            "engine_mode": self.mode_var.get(),
            "target_period": self.ent_period.get().strip(),
            "target_date": self.ent_date.get().strip(),
            "gmail_user": self.ent_gmail.get().strip(),
            "gmail_app_password": self.ent_gmail_pass.get().strip(),
            "gemini_api_key": self.ent_gemini.get().strip()
        }
        self.engine.save_config(cfg)
        messagebox.showinfo("تم الحفظ", "تم حفظ جميع الإعدادات بنجاح!")

    def reset_all_status(self):
        self.engine.reset_passengers_status()
        self.render_table()
        messagebox.showinfo("تمت الإعادة", "تم إعادة تعيين حالة جميع المعتمرين إلى '⏳ قيد الانتظار' بنجاح!")

    def start_bot(self):
        self.save_settings()
        pending = [p for p in self.engine.passengers if not ("تم" in p.booking_status or "مؤكد" in p.booking_status)]
        if not pending and self.engine.passengers:
            ans = messagebox.askyesno(
                "تأكيد البدء",
                "جميع الحسابات في الجدول محددة كـ 'تم' بالفعل.\nهل تريد إعادة تعيين حالتهم إلى 'قيد الانتظار' والبدء في الحجز الآن؟"
            )
            if ans:
                self.engine.reset_passengers_status()
                self.render_table()
            else:
                return

        self.btn_start.pack_forget()
        self.btn_stop.pack(side=tk.RIGHT, padx=5)
        self.engine.start_booking()

    def stop_bot(self):
        self.engine.stop_booking()
        self.btn_stop.pack_forget()
        self.btn_start.pack(side=tk.RIGHT, padx=5)

    def ask_ai(self):
        sc_path = self.engine.adb.screencap("ai_diag.png")
        if not self.engine.ai_agent.is_available():
            messagebox.showwarning("تنبيه", "يرجى إدخال مفتاح Gemini API أولاً في خانة الإعدادات.")
            return
        res = self.engine.ai_agent.analyze_screen(sc_path)
        messagebox.showinfo("تحليل الذكاء الاصطناعي", f"نوع الشاشة: {res.get('screen_type')}\nالوصف: {res.get('description_ar')}\nالإجراء المقترح: {res.get('next_action')}")

    def _auto_refresh_loop(self):
        while True:
            try:
                connected = self.engine.adb.ensure_connected()
                if connected:
                    self.lbl_status.config(text="● متصل بالمحاكي", fg="#10b981")
                else:
                    self.lbl_status.config(text="○ غير متصل", fg="#ef4444")

                def _sync_ui():
                    if not self.engine.is_running:
                        if self.btn_stop.winfo_ismapped():
                            self.btn_stop.pack_forget()
                            self.btn_start.pack(side=tk.RIGHT, padx=5)
                    done_cnt = sum(1 for p in self.engine.passengers if "تم" in p.booking_status or "مؤكد" in p.booking_status)
                    self.card_done.config(text=str(done_cnt))
                    self.card_total.config(text=str(len(self.engine.passengers)))
                    self.card_status.config(text=self.engine.state.value)

                self.root.after(0, _sync_ui)

                # Screen preview
                sc_path = self.engine.adb.screencap("live_thumb.png")
                if os.path.exists(sc_path):
                    img = Image.open(sc_path)
                    img.thumbnail((240, 340))
                    img_tk = ImageTk.PhotoImage(img)
                    self.current_img_tk = img_tk
                    self.screen_canvas.config(image=img_tk, text="")
                else:
                    self.screen_canvas.config(text="[بث الشاشة غير متوفر]")
            except Exception:
                pass
            time.sleep(2.5)


if __name__ == "__main__":
    root = tk.Tk()
    app = NusukDesktopApp(root)
    root.mainloop()
