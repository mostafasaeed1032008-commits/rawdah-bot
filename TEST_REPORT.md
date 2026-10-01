# NusukBot_PC — Comprehensive Test & Verification Report

**Date:** 2026-09-20  
**Repository:** `NusukBot_PC`  
**Python Runtime:** Python 3.12.10 (`C:\Users\win10\AppData\Local\Programs\Python\Python312\python.exe`)  
**ADB Tool:** `C:\Program Files\Netease\MuMuPlayer\nx_device\15.0\shell\adb.exe` (v1.0.41)  
**Emulator:** Connected at `127.0.0.1:16384` (Model: `SM-P615N`, Android 15, Resolution: `900x1600`)  
**Target App:** `com.moh.nusukapp` (Installed)

---

## 1. Summary of Changes & Architecture Upgrades

1. **Truthful & Safe State Machine (`nusuk_flows.py`):**
   - Implemented conservative 21-state detection: `DISCONNECTED`, `SECURITY_CHALLENGE`, `ALREADY_CONFIRMED`, `CONFIRMATION`, `ONBOARDING`, `LANDING`, `AUTH_MODAL`, `REGISTER_FORM`, `LOGIN_FORM`, `OTP`, `HOME`, `RAWDAH_SERVICE`, `WHO_FOR`, `SELECT_PERSON`, `CALENDAR`, `AVAILABLE_SLOT`, `FULLY_BOOKED`, `WAITING_LIST`, `INSTANT_TRACK`, `TERMS_POPUP`, `PAUSED`, `FAILED`, `UNKNOWN`.
   - **Zero Bypass of Security Challenges:** When a CAPTCHA, bot challenge, or security check is detected, the bot immediately halts automated touches, logs a clear warning, saves diagnostic screenshots, and transitions to `SECURITY_CHALLENGE`.
   - **UI Hierarchy Interaction First:** Element clicks prioritize Resource-ID, exact/partial text match, and element bounds before falling back to coordinates.

2. **Secrets Protection & Sanitization:**
   - Cleared hardcoded personal passwords, Gmail app passwords, and Gemini API keys from `config.json`.
   - Created `config.example.json` and `.gitignore` to prevent credential leakage.
   - Enforced strict masking (`••••••••`) across `/api/status`, `/api/preflight`, and the web dashboard.
   - Added environment variable support: `NUSUK_ADB_PATH`, `NUSUK_DEVICE_SERIAL`, `NUSUK_PACKAGE`, `NUSUK_EXCEL_PATH`, `NUSUK_GMAIL_USER`, `NUSUK_GMAIL_APP_PASSWORD`, `NUSUK_GEMINI_API_KEY`, `NUSUK_UNIFIED_PASSWORD`.

3. **Screen Size Discovery & Coordinate Scaling (`adb_controller.py`):**
   - Added `get_screen_size()` dynamically parsing `wm size`.
   - Implemented `scale_coords(x, y)` to scale reference (900x1600) coordinates to any active screen resolution and clamp them within physical boundaries.

4. **Data Management & Integrity (`excel_manager.py` & `booking_plan.py`):**
   - Comprehensive Arabic and English header mapping for Name, Email, Passport, Visa, Gender/Type, Mobile, Status, Date, and Notes.
   - Child companion linking logic (`_link_family_companions`).
   - Input validation in `PassengerTask.validate()`.
   - Truthful results persistence in `results.json` and export to Excel (`Nusuk_Permits_Export.xlsx`).

5. **Dashboard & Local REST API (`app_server.py` & `web_gui/index.html`):**
   - Removed all static mock slot cards, fake bookings, and hardcoded prayer/Hijri dates.
   - Added `/api/preflight` diagnostic endpoint and preflight modal in UI.
   - Added `/api/results` endpoint.
   - Added safe stop (`/api/stop`) and resume (`/api/resume`).
   - Escaped dynamic HTML content to prevent XSS.

6. **Portable Windows Launchers:**
   - Updated `test_connection.bat`, `run_bot.bat`, `run_gui.bat`, and `run_job.bat` to resolve `%~dp0` and discover Python automatically.

---

## 2. Test Execution & Results

### Automated Test Suite (`smoke_test.py`)
All 8 automated tests passed:

| # | Test Name | Description | Result |
|---|-----------|-------------|:------:|
| 1 | `test_config_secret_masking` | Strict masking of passwords and API keys in `public_config()` and status dict | **PASS** |
| 2 | `test_passenger_validation` | Validation of required fields in `PassengerTask` | **PASS** |
| 3 | `test_excel_manager_headers` | Arabic and English header aliases and CSV import with child linking | **PASS** |
| 4 | `test_coordinate_scaling` | Coordinate scaling (900x1600 -> 720x1280) and boundary clamping | **PASS** |
| 5 | `test_state_detection_fixtures` | Screen detection on XML fixtures (`SECURITY_CHALLENGE`, `WAITING_LIST`, `INSTANT_TRACK`, `FULLY_BOOKED`, `AVAILABLE_SLOT`, etc.) | **PASS** |
| 6 | `test_offline_preflight` | Structured preflight diagnostic both live and with simulated offline device | **PASS** |
| 7 | `test_results_persistence` | Saving and loading structured results from `results.json` | **PASS** |
| 8 | `test_api_endpoints` | Local HTTP REST API server (`/api/status`, `/api/preflight`, `/api/results`, `/api/stop`) | **PASS** |

### Compilation Check
- `python -m compileall .`: **PASS** (100% of Python source files compiled with 0 errors).

### Live Device & App Preflight (`test_connection.py`)
- Python Environment: **PASS** (Python 3.12.10, all required packages `requests`, `openpyxl`, `PIL`, `appium` verified).
- ADB Connection: **PASS** (ADB v1.0.41 connected to `127.0.0.1:16384`).
- Target Package: **PASS** (`com.moh.nusukapp` verified as installed on emulator).
- Live App Interaction:
  - Permission prompt ("Allow Nusuk to send you notifications?") detected as `TERMS_POPUP`.
  - Permission accepted automatically via UI element click (`ALLOW`).
  - Screen transitioned to `ONBOARDING` ("The Qur’an, always with you").
  - Onboarding advanced successfully to `LANDING` ("Are you ready to start your journey?", "Login Or Register", "Continue as Guest").

---

## 3. What Requires Manual User Action or Connected Emulator

1. **User Authentication & OTP:**
   - Real account login requires entering your authorized credentials (or setting them via environment variables / UI Settings) and receiving the OTP either manually or through configured Gmail IMAP credentials.
2. **Official Security Challenges:**
   - In accordance with safety policies, if a CAPTCHA or security verification prompt appears, the tool pauses execution safely and displays an alert on the dashboard. The user must solve the prompt manually on the emulator screen and click **"استئناف (Resume)"**.
3. **Appointment Selection & Official Confirmation:**
   - Actual appointment booking was **not executed on live servers**, preserving fair capacity allocation. Real confirmation requires navigating to active reservation slots inside the emulator with valid user credentials.

---

## 4. Exact Startup Commands

All commands can be run from `NusukBot_PC/` or by double-clicking the batch files:

### 1. Run Preflight Diagnostics
```powershell
.\test_connection.bat
# or directly:
& "C:\Users\win10\AppData\Local\Programs\Python\Python312\python.exe" test_connection.py
```

### 2. Run Automated Smoke Test Suite
```powershell
& "C:\Users\win10\AppData\Local\Programs\Python\Python312\python.exe" smoke_test.py
```

### 3. Launch Web Dashboard
Double-click `run_bot.bat` or run:
```powershell
& "C:\Users\win10\AppData\Local\Programs\Python\Python312\python.exe" app_server.py
```
Open your browser at: `http://localhost:5000`

### 4. Launch Desktop GUI
Double-click `run_gui.bat` or run:
```powershell
& "C:\Users\win10\AppData\Local\Programs\Python\Python312\python.exe" desktop_gui.py
```

### 5. Run Single-Account Test Job
Double-click `run_job.bat` or run:
```powershell
& "C:\Users\win10\AppData\Local\Programs\Python\Python312\python.exe" run_job.py
```

---

## 5. Known Limitations & Safety Boundaries

- **No Security Bypasses:** The tool strictly avoids any CAPTCHA solving, device ID spoofing, or GPS spoofing.
- **Fair Resource Allocation:** The tool does not perform high-frequency aggressive polling. Intervals respect safe thresholds and backoff behavior.
- **No Mock Availability:** No slot is reported as booked or available unless visually verified on the app display.
