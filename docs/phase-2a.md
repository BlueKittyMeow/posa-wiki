# Phase 2A: Code Stability Implementation Plan

This document outlines the concrete steps for Phase 2A, focusing on enhancing the stability, security, and performance of the application before new features are added.

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


**Status:** ✅ Completed (Codex)

**Goal:** Provide a consistent user experience for errors and establish a baseline for server-side logging.

1. ✅ **Create Error Templates:** Added `templates/errors/404.html` and `500.html`, both extending `base.html` with themed messaging (Codex).
2. ✅ **Implement Error Handlers:** Registered `handle_not_found` and `handle_server_error` in `app.py` to render the new templates (Codex).
3. ✅ **Configure Logging:** Added `configure_logging` to wire console logging everywhere and rotating file logs when not in debug/test (Codex).

---

### Step 3: Improve Search Performance with FTS5 - Gemini (tentative)

**Goal:** Replace the inefficient `LIKE` queries in the search functionality with SQLite's optimized full-text search.

1.  **Create FTS Index:** Write a one-time script (e.g., `build_fts_index.py`) that creates a new FTS5 virtual table in the database and populates it with data from the `videos` table.
2.  **Update Search Route:** Modify the `/search` route in `app.py` to query against the new FTS5 table, providing a significant performance boost.

---

### Step 4: Paginate List Views - Gemini (stretch)

**Goal:** Improve the performance and usability of pages that list large numbers of items.

1.  **Add Dependency:** Add `flask-paginate` to `requirements.txt`.
2.  **Prototype on Videos Page:** Update the `/videos` route to implement pagination logic. Pass the generated pagination object to the `video_list.html` template.
3.  **Render Controls:** Modify `video_list.html` to display the pagination controls.
4.  **Roll Out:** Once working correctly, apply the same pagination logic and template controls to the `/people`, `/dogs`, `/series`, and `/trips` views.

---

### Step 5: Establish Authentication Foundations - Claude

**Goal:** Create the necessary components for a secure admin login system.

1.  **Add Dependency:** Add `Flask-Login` to `requirements.txt`.
2.  **Update Schema:** Manually add a `users` table to the `posa_wiki.db` database. Update `schema.md` to reflect this change.
3.  **Create Admin User:** Write a simple script (e.g., `create_admin.py`) to add the first admin user, using `werkzeug.security.generate_password_hash` to secure the password.
4.  **Create User Model:** Create a `user.py` file with a `User` class that is compatible with `Flask-Login`.
5.  **Create Auth Blueprint:** Create an `auth.py` file as a Flask Blueprint to manage `/login` and `/logout` routes and their corresponding templates.
6.  **Register Blueprint:** Register the new auth blueprint in the main `app.py` file.

---

### Step 6: Implement Form Security (CSRF) - Codex

**Goal:** Protect the application against Cross-Site Request Forgery attacks, starting with the new login form.

1.  **Add Dependency:** Add `Flask-WTF` to `requirements.txt`.
2.  **Initialize CSRF Protection:** In `app.py`, initialize `CSRFProtect(app)` after loading the application configuration.
3.  **Secure Login Form:** Integrate the CSRF token into the login form located in the `auth` blueprint's template. This will serve as the first and primary test case for CSRF protection.
