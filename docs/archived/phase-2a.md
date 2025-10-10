# Phase 2A: Code Stability Implementation Plan

**Status: COMPLETE**

This document outlines the concrete steps for Phase 2A, focusing on enhancing the stability, security, and performance of the application before new features are added. All steps have been successfully implemented.

---

### Step 1: Configuration and Environment Setup

**Status:** ✅ Completed (Codex)

**Goal:** Separate configuration from code, removing hardcoded values and secrets.

1. ✅ **Add Dependency:** Added `python-dotenv` to `requirements.txt` (Codex).
2. ✅ **Create Config File:** `config.py` now defines `Config`, `DevelopmentConfig`, and `ProductionConfig` with environment-driven settings (Codex).
3. ✅ **Set Up Environment File:** Added a local `.env` stub for secrets (`FLASK_SECRET_KEY`, etc.) (Codex).
4. ✅ **Update `.gitignore`:** Verified `.env` is ignored so secrets stay out of version control (Codex).
5. ✅ **Refactor `app.py`:** Flask now loads configuration classes and uses `DATABASE_PATH` from config (Codex).

---

### Step 2: Centralized Error Handling and Logging

- Note (Codex): 500 error page not manually triggered yet; plan to validate during upcoming auth/CRUD work.
- Note (Claude): During Phase 2B, include manual checks that 404/500 render correctly across all themes and both anonymous/authenticated states.

**Status:** ✅ Completed (Codex)

**Goal:** Provide a consistent user experience for errors and establish a baseline for server-side logging.

1. ✅ **Create Error Templates:** Added `templates/errors/404.html` and `500.html`, both extending `base.html` with themed messaging (Codex).
2. ✅ **Implement Error Handlers:** Registered `handle_not_found` and `handle_server_error` in `app.py` to render the new templates (Codex).
3. ✅ **Configure Logging:** Added `configure_logging` to wire console logging everywhere and rotating file logs when not in debug/test (Codex).

---

### Step 3: Improve Search Performance with FTS5

**Status: COMPLETE (Gemini)**

**Goal:** Replace the inefficient `LIKE` queries in the search functionality with SQLite's optimized full-text search.

1.  ✅ **Create FTS Index:** Write a one-time script (`build_fts_index.py`) that creates a new FTS5 virtual table in the database and populates it with data from the `videos` table.
2.  ✅ **Update Search Route:** Modify the `/search` route in `app.py` to query against the new FTS5 table, providing a significant performance boost.


---

### Step 4: Paginate List Views

**Status: COMPLETE (Gemini)**

**Goal:** Improve the performance and usability of pages that list large numbers of items.

1.  ✅ **Add Dependency:** Add `flask-paginate` to `requirements.txt`.
2.  ✅ **Prototype on Videos Page:** Update the `/videos` route to implement pagination logic. Pass the generated pagination object to the `video_list.html` template.
3.  ✅ **Render Controls:** Modify `video_list.html` to display the pagination controls.
4.  ✅ **Roll Out:** Apply the same pagination logic and template controls to the `/people`, `/dogs`, `/series`, and `/trips` views.

---

### Step 5: Establish Authentication Foundations - Claude

**Status: COMPLETE (Claude)**

**Goal:** Create the necessary components for a secure admin login system.

1.  ✅ **Add Dependency:** Added `Flask-Login==0.6.3` to `requirements.txt`.
2.  ✅ **Update Schema:** Created `migrations/003_create_users_table.sql` with users table DDL and applied to database. Updated `schema.md` with complete documentation.
3.  ✅ **Create Admin User:** Created Flask CLI command `flask create-admin` for secure user creation with password hashing.
4.  ✅ **Create User Model:** Created `models/user.py` with `User` class implementing Flask-Login's `UserMixin`, including password verification and role checking methods.
5.  ✅ **Create Auth Blueprint:** Created `blueprints/auth.py` with `/auth/login` and `/auth/logout` routes, plus login template in `templates/auth/login.html` (theme-aware, ready for CSRF in Step 6).
6.  ✅ **Register Blueprint:** Registered auth blueprint and initialized Flask-Login in `app.py` with user_loader callback.
7.  ✅ **Role-Based Decorators:** Created `utils/decorators.py` with `@admin_required` and `@editor_required` decorators for access control.
8.  ✅ **UI Integration:** Added login/logout links to base template sidebar with current user display.

**Test Admin User Created:**
- Username: `admin`
- Password: `admin123`
- Role: `admin`

---

### Step 6: Implement Form Security (CSRF) - Codex

**Status:** ✅ Completed (Codex)

**Goal:** Protect the application against Cross-Site Request Forgery attacks, starting with the new login form.

1. ✅ **Add Dependency:** Added `Flask-WTF` to `requirements.txt` alongside python-dotenv (Codex).
2. ✅ **Initialize CSRF Protection:** Registered `CSRFProtect` in `app.py` so every POST requires a valid token (Codex).
3. ✅ **Secure Login Form:** Introduced `LoginForm` (Flask-WTF) and added CSRF token + validation to `/auth/login` (Codex).
