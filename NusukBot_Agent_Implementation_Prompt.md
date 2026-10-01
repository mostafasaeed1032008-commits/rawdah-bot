# NusukBot_PC — Agent Implementation Prompt

You are working on the existing local Windows repository `NusukBot_PC`. Your job is to turn it into a reliable, portable, testable Android UI automation and regression-testing utility for an Android app running in the user’s own MuMu emulator.

The user wants the repetitive, ordinary UI steps to be automated after configuring the data once. The tool must follow the official app flow and must never invent availability or bypass a security or capacity control.

## Safety and scope boundaries

This is authorized local testing on the user’s own Windows machine and emulator. Implement normal UI automation only:

- Open the app.
- Read the UI hierarchy and current screen.
- Enter ordinary user-provided data.
- Navigate through screens displayed by the app.
- Select an appointment only when the app explicitly shows it as available.
- Use an official waiting-list option only when the app explicitly presents it.
- Detect the official Instant Track option only when the app explicitly presents it and the app itself confirms eligibility.
- Save truthful results and screenshots.

Do **not**:

- Bypass CAPTCHA, identity checks, device checks, location checks, rate limits, authentication, or anti-abuse controls.
- Spoof GPS or device identity.
- Create capacity that the official app does not provide.
- Exploit an API or private endpoint.
- Use aggressive polling or repeated submissions.
- Automate a security challenge.
- Claim success after clicking a button without visible confirmation.
- Print or expose passwords, Gmail app passwords, API keys, tokens, OTP values, or full credentials.

If a CAPTCHA, security challenge, identity verification, location verification, unknown screen, or manual approval step appears, pause safely, save diagnostics, and report that manual action is required.

## Repository and current context

Important files include:

- `app_server.py` — local dashboard server and API
- `nusuk_engine.py` — main engine and state management
- `nusuk_flows.py` — screen detection and normal app flows
- `adb_controller.py` — ADB actions, screenshots, UI hierarchy, taps, typing
- `device_manager.py` — ADB and emulator discovery
- `sequential_runner.py` — sequential account execution
- `excel_manager.py` — CSV/XLSX import and export
- `booking_plan.py` — typed booking/session data
- `otp_fetcher.py` — optional email verification-code retrieval
- `ai_vision_agent.py` — optional visual fallback
- `web_gui/index.html` — dashboard
- `test_connection.py` — diagnostics
- `test_connection.bat`, `run_bot.bat`, `run_job.bat`, `run_gui.bat` — Windows launchers
- `smoke_test.py` — offline test suite if present

A previous implementation already addressed some basics: portable BAT paths, local API smoke testing, secret masking in status, removal of demo counters, configurable Excel path, and graceful startup when ADB is unavailable. Verify the current files before changing them; keep working fixes and improve them rather than blindly replacing them.

## Priority order

Work in this order and test after each phase. Do not jump directly to the multi-account runner.

### Phase 1 — Baseline and truthfulness

1. Inspect every Python file and the dashboard.
2. Run syntax compilation and existing tests.
3. Identify all fake values, static slot cards, hardcoded dates, hardcoded user paths, silent exceptions, and unhandled thread failures.
4. Remove or replace fake availability, fake counters, fake connection badges, fake success states, and hardcoded prayer/date data.
5. Ensure all UI and API status values come from actual engine/device state.

### Phase 2 — Configuration and security

1. Keep a non-secret `config.example.json` with documented fields.
2. Keep local secrets out of source control and out of browser responses.
3. Support environment variables for at least:
   - `NUSUK_ADB_PATH`
   - `NUSUK_DEVICE_SERIAL`
   - `NUSUK_PACKAGE`
   - `NUSUK_EXCEL_PATH`
   - `NUSUK_GMAIL_USER`
   - `NUSUK_GMAIL_APP_PASSWORD`
   - `NUSUK_GEMINI_API_KEY`
4. Add or update `.gitignore` for local secrets, screenshots, UI dumps, logs, results, and Python caches.
5. Preserve existing secrets when a settings form submits blank secret fields; blank UI fields must not erase a configured secret accidentally.
6. Mask secrets in logs, `/api/status`, `/api/preflight`, error messages, and dashboard HTML.
7. Never log OTP contents.

### Phase 3 — Portable startup and preflight

1. Every BAT file must use `%~dp0` and must not reference a previous username or desktop path.
2. Detect `py`, `python`, and common installed Python locations. If Python is missing, print a clear installation message and exit cleanly.
3. Detect required Python packages without crashing the dashboard.
4. Detect ADB using:
   - configured path if valid;
   - `shutil.which("adb")`;
   - Android SDK platform-tools;
   - common MuMu installation paths;
   - other emulator paths only as optional fallbacks.
5. Add a structured preflight function and `/api/preflight` endpoint returning:
   - Python version and executable;
   - missing packages;
   - ADB path and version;
   - connected devices and their states;
   - emulator detection;
   - Android model/version when connected;
   - screen resolution when connected;
   - installed target package when connected;
   - actionable remediation text.
6. The dashboard must start when the emulator is disconnected and must show a truthful disconnected state.

### Phase 4 — Device and ADB reliability

1. Add `get_screen_size()` using ADB display information.
2. Add safe coordinate scaling from the existing 900x1600 reference resolution.
3. Clamp tap coordinates to the actual screen bounds.
4. Prefer UI hierarchy interaction in this order:
   - resource ID;
   - exact text/content description;
   - safe partial text match;
   - bounds center;
   - scaled coordinate fallback only when necessary.
5. Add bounded timeouts and retries to every device operation.
6. Save timestamped screenshots and UI dumps before and after important transitions, but never include them in API responses unless explicitly requested.
7. If the device disconnects, pause the run and expose a resumable `DEVICE_DISCONNECTED` state.

### Phase 5 — Explicit state machine

Use explicit states, with timeouts and legal transitions, at minimum:

- `DISCONNECTED`
- `ONBOARDING`
- `LANDING`
- `LOGIN_FORM`
- `REGISTER_FORM`
- `OTP`
- `HOME`
- `RAWDah_SERVICE`
- `WHO_FOR`
- `SELECT_PERSON`
- `CALENDAR`
- `AVAILABLE_SLOT`
- `FULLY_BOOKED`
- `WAITING_LIST`
- `INSTANT_TRACK`
- `CONFIRMATION`
- `ALREADY_CONFIRMED`
- `SECURITY_CHALLENGE`
- `UNKNOWN`
- `PAUSED`
- `FAILED`

For each state, define:

- detection signals;
- allowed actions;
- success condition;
- timeout;
- retry behavior;
- safe-stop behavior;
- diagnostic artifacts to save.

The detector must be conservative. If evidence is ambiguous, return `UNKNOWN` rather than guessing.

### Phase 6 — Official availability workflow

Implement only the normal app flow:

1. When the app explicitly displays an available date/time, select according to configured preferences.
2. Confirm that the slot is enabled/selectable and not merely visible text.
3. If no requested slot is available, follow the configured fallback policy without aggressive retries.
4. If the app explicitly displays that all slots are full, enter `FULLY_BOOKED`.
5. If the app explicitly offers an official waiting-list action:
   - select it once;
   - verify registration succeeded;
   - persist the waiting-list state locally;
   - do not register the same person repeatedly.
6. If the app explicitly offers official Instant Track:
   - do not spoof location;
   - allow the app to perform its own eligibility check;
   - if eligibility fails or location verification appears, pause and report manual action;
   - verify any resulting permit using an explicit confirmation state.
7. When no official option is available, wait using a configurable safe interval and exponential backoff after failures.
8. Stop after a configurable number of consecutive failures and preserve the resume state.

The system cannot create capacity. It may only react to availability, official waiting-list behavior, or official Instant Track behavior shown by the app.

### Phase 7 — Data, resume, and result integrity

1. Support Arabic and English CSV/XLSX headers for name, email, passport, visa, gender/type, mobile, and status.
2. Validate required fields before starting.
3. Reject or clearly report malformed rows instead of silently creating fake records.
4. Persist local state in a safe results file containing:
   - person identifier;
   - current state;
   - waiting-list state;
   - selected date/time if any;
   - confirmation details if any;
   - timestamps;
   - error reason;
   - last diagnostic artifact paths.
5. Resume deterministically after interruption without repeating confirmed or already-registered actions.
6. Never run two operations for the same person concurrently.
7. Export truthful results to XLSX/CSV without assuming a Desktop path.

### Phase 8 — Dashboard and API

Add or repair these endpoints as appropriate:

- `/api/status`
- `/api/preflight`
- `/api/logs`
- `/api/screenshot`
- `/api/results`
- `/api/start`
- `/api/stop`
- `/api/resume`
- `/api/diagnostics`
- `/api/import_excel`
- `/api/export_excel`

The dashboard must:

- show actual device, app, resolution, and engine states;
- show `FULLY_BOOKED`, `WAITING_LIST`, `INSTANT_TRACK`, `PAUSED`, and `SECURITY_CHALLENGE` distinctly;
- provide Start, Stop, Resume, Diagnostics, Screenshot, Import, and Export actions;
- show a clear manual-intervention warning when required;
- avoid static demo slots and fake availability;
- escape dynamic text before inserting it into HTML;
- never expose credentials or OTPs.

### Phase 9 — AI fallback

AI vision is optional and must never be the only source of truth for a sensitive action.

1. Keep deterministic UI hierarchy detection as the primary method.
2. If AI is used for an unknown screen, it may suggest a state/action, but the engine must validate the action against safe allowed actions.
3. AI must detect and signal security challenges.
4. AI prompts must use the actual screen dimensions.
5. AI output must be schema-validated before use.
6. Never let AI bypass a security challenge or invent a successful booking.

### Phase 10 — Tests and verification

Run all of the following and save the results in `TEST_REPORT.md`:

1. `python -m compileall`.
2. Unit tests for config loading and secret masking.
3. CSV/XLSX parsing tests with Arabic and English headers.
4. Coordinate scaling and bounds-clamping tests.
5. State-classification tests using fixture UI XML files.
6. Security-challenge detection tests.
7. Offline preflight tests with no ADB/device.
8. Local API smoke tests for status, preflight, logs, results, invalid input, and safe stop.
9. Dashboard test confirming no fake counters or static mock availability.
10. If an emulator is available, test one person only:
    - app launch;
    - screen detection;
    - normal navigation;
    - fully-booked detection;
    - waiting-list detection only if the app displays it;
    - Instant Track detection only if the app displays it;
    - security-challenge pause behavior;
    - explicit confirmation validation.
11. Do not run a large batch or multiple emulator instances until the one-person test is verified.

## Acceptance criteria

The work is complete only when:

- The project starts from its own folder on Windows without old-user paths.
- Missing Python, dependencies, ADB, MuMu, or the app package produce actionable diagnostics.
- The dashboard can start offline and reports the real offline state.
- No fake availability, fake counters, or fake success remains.
- Secrets are not stored in source code or exposed by APIs/logs.
- The engine uses explicit states and safe transitions.
- A confirmed result requires visible app evidence.
- Fully booked, waiting-list, Instant Track, disconnected, unknown, and security-challenge states are distinguishable.
- The process can stop and resume without duplicating confirmed or waiting-list actions.
- Local smoke tests pass.
- `TEST_REPORT.md` clearly separates verified behavior from behavior that requires a connected emulator or manual user action.

## Required final response from the agent

At the end, do not say only “done.” Provide:

1. Files changed or created.
2. Commands executed.
3. Tests passed and failed.
4. Whether a real emulator was connected.
5. Whether a real app confirmation was observed.
6. Any remaining manual steps.
7. Exact commands to start diagnostics, dashboard, and the one-person test.
8. Known limitations and safety stops.

Do not claim that actual appointment booking works unless it was observed and verified on a connected emulator with an explicit confirmation state.
