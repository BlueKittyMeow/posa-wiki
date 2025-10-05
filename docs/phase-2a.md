# Phase 2A: Code Stability Plan

## Scope
Phase 2A targets the stability prerequisites for future CRUD and API additions. The work centers on five themes from `PROJECT_STATUS.md`:
1. Configuration management
2. Error handling and logging
3. Form security (CSRF + validation)
4. Authentication
5. Pagination

## Repository Observations
- `app.py` currently performs direct configuration inline. `app.secret_key` is generated at import time (`app.py:52`) and the SQLite path is hardcoded inside `get_db_connection()` (`app.py:63`).
- Templates and static assets assume a single configuration path; theme loading already uses localStorage but there is no environment separation.
- Route handlers return string fallbacks (e.g., “Video not found”) without custom error pages or logging hooks.
- No forms or POST routes exist yet, so CSRF protection has not been introduced.
- Authentication is not referenced anywhere, and there is no User model or session logic beyond Flask’s default.
- List views (`/videos`, `/people`, `/dogs`, `/series`, `/trips`) query the full dataset on every request; there is no paging or limit/offset handling.

## Recommendations by Theme

### 1. Configuration Management
- Create a `config/` module (e.g., `config/__init__.py`, `config/default.py`, `config/development.py`). Expose `DB_PATH`, `SECRET_KEY`, `FLASK_ENV`, and feature flags. Keep production secrets sourced from environment variables with `.env` support if desired.
- Update `app.py` to load configuration via `app.config.from_object` / `from_envvar`. Use `app.config['DATABASE']` (or similar) in `get_db_connection()`.
- Move per-environment toggles (e.g., debug on/off, pagination defaults) into config to prevent future drift.

### 2. Error Handling & Logging
- Implement `@app.errorhandler(404)` and `@app.errorhandler(500)` with dedicated templates in `templates/errors/` for user-friendly messaging that still matches the theme system.
- Configure Python’s `logging` module on app startup. Capture exceptions to a rotating log file (development) and ensure console logs include request context. Consider `flask.logging.default_handler` configuration.
- Wrap database access in try/except during connection creation to surface DB connectivity problems cleanly.

### 3. Form Security & Validation
- Introduce Flask-WTF for CSRF protection and form handling. Initialize `CSRFProtect(app)` once configuration provides `SECRET_KEY`.
- Build a shared form base class for upcoming CRUD screens (videos, people, dogs). Start with a simple example (e.g., search filter form) to verify CSRF wiring before CRUD launch.
- Document required middleware for any future API endpoints that accept POST/PUT (even if they will use token auth later).

### 4. Authentication Foundations
- Decide on user storage strategy: SQLite `users` table for now with migration path to PostgreSQL. Define fields for username/email, password hash, role/permissions.
- Integrate Flask-Login: create a `User` model class (even if lightweight) with loader functions. Gate admin-only routes behind `@login_required` and plan for blueprint separation (`admin` vs. public views).
- Add password hashing via `werkzeug.security` and include a seed script for the initial admin user. Document login flow for later UI work.

### 5. Pagination & Query Performance
- Add pagination helpers (`paginate_query(query, page, per_page)`) or integrate `flask-paginate`. Start with `/videos` since it is the heaviest view; extend to `/people`, `/dogs`, `/series`, and `/trips`.
- Update templates to render pagination controls that align with the existing layout (sidebar + main content). Ensure theme classes apply.
- Evaluate indexes (e.g., `videos.upload_date`) and confirm they exist in `schema.md`; consider adding migration notes for production DBs.

## Suggested Execution Order
1. **Configuration refactor** – prerequisite for secure keys, CSRF, logging.
2. **Logging & error pages** – leverages new config and sets standard for later modules.
3. **CSRF scaffolding** – introduce Flask-WTF early to avoid retrofitting.
4. **Authentication groundwork** – establish models and session handling.
5. **Pagination rollout** – adjust routes/templates once stability infrastructure is ready.

## Next Steps
- Draft configuration files and update `app.py` to consume them.
- Prepare error templates (`templates/errors/404.html`, `500.html`) and confirm logging output during manual tests.
- Introduce Flask-WTF dependency in `requirements.txt` and wire CSRF middleware.
- Design minimal `User` model + login blueprint to support admin access later.
- Prototype pagination on `/videos` to validate UX before extending elsewhere.

---
## Gemini's Review & Suggestions

> ### Gemini's Note on Configuration Management
>
> Codex's proposal for a `config/` module is robust. For a project of this scale, a single `config.py` file might offer a simpler, more direct approach while still achieving the goal of separating configuration from the application logic. We can define a base `Config` class and then subclasses for `DevelopmentConfig`, `ProductionConfig`, etc. This file can also handle loading secrets from environment variables using `os.getenv()`, and we should add `python-dotenv` to `requirements.txt` to manage a `.env` file for local development. This keeps all configuration in one place and is a very common Flask pattern.
>
> --- Gemini

> ### Gemini's Note on Error Handling
>
> This is a great plan. To ensure a consistent user experience, the error templates in `templates/errors/` should extend the main `base.html` template. This will maintain the navigation, theme-switching capabilities, and overall site aesthetic even on error pages, which is crucial given the strong design focus of the project.
>
> --- Gemini

> ### Gemini's Note on Authentication
>
> I agree with the groundwork for authentication. To keep `app.py` focused on the core public-facing application, I recommend creating a separate blueprint for all administrative routes (e.g., `admin_bp`). This blueprint can be protected by the `@login_required` decorator from `Flask-Login`. This will make the project more modular and easier to maintain as more admin features are added in Phase 2B and 2C.
>
> --- Gemini

> ### Gemini's Note on Pagination and Performance
>
> The plan for pagination is critical for performance. I'd also like to point out the current search implementation in `app.py` uses `LIKE` queries, which will not scale well. While a full-text search overhaul is planned for Phase 2B, we could consider leveraging SQLite's FTS5 extension now as a part of this stability phase. It's relatively straightforward to implement and would provide a significant performance boost for the search feature.
>
> Also, a minor code quality note: the `format_duration` function in `app.py` could be made more robust by using a regular expression to parse the ISO 8601 duration string, which would simplify the code and make it less prone to errors.
>
> --- Gemini

---
## Claude's Review & Suggestions

> ### Claude's Note on Configuration Management
>
> **Agreement with Gemini**: A single `config.py` with class-based configs (DevelopmentConfig, ProductionConfig) is the right approach for this project size. The `config/` module adds unnecessary indirection.
>
> **Critical Issue - Secret Key**: Line 52 of `app.py` uses `os.urandom(24)` which regenerates on every app restart, invalidating all sessions. This must be fixed immediately—use a persistent secret from environment variables or a `.env` file.
>
> **Recommended structure**:
> ```python
> # config.py
> import os
> from dotenv import load_dotenv
>
> load_dotenv()
>
> class Config:
>     SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
>     DATABASE = os.path.join(os.path.dirname(__file__), 'posa_wiki.db')
>     VIDEOS_PER_PAGE = 24
>     PEOPLE_PER_PAGE = 20
>
> class DevelopmentConfig(Config):
>     DEBUG = True
>     TESTING = False
>
> class ProductionConfig(Config):
>     DEBUG = False
>     DATABASE = os.environ.get('DATABASE_PATH') or Config.DATABASE
> ```
>
> --- Claude

> ### Claude's Note on Error Handling & Logging
>
> **Strong agreement** with both plans. Additional recommendations:
>
> 1. **Context preservation**: Error pages should include a unique error ID for support tracking
> 2. **Database connection resilience**: Wrap `get_db_connection()` with try/except to handle locked databases or missing files gracefully
> 3. **Logging setup example**:
> ```python
> import logging
> from logging.handlers import RotatingFileHandler
>
> if not app.debug:
>     file_handler = RotatingFileHandler('logs/posa_wiki.log', maxBytes=10240, backupCount=10)
>     file_handler.setFormatter(logging.Formatter(
>         '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
>     ))
>     file_handler.setLevel(logging.INFO)
>     app.logger.addHandler(file_handler)
>     app.logger.setLevel(logging.INFO)
> ```
>
> 4. **Theme consistency**: Ensure error templates extend `base.html` as Gemini mentioned—this is crucial for the multi-theme system you just implemented
>
> --- Claude

> ### Claude's Note on Form Security & Validation
>
> **Expansion on the plan**:
>
> 1. **Flask-WTF integration is correct**, but start even simpler—protect the existing search form first as a proof of concept
> 2. **API endpoints consideration**: If Phase 2B includes JSON APIs, you'll need to exempt API routes from CSRF (`@csrf.exempt`) and use alternative auth (tokens/API keys)
> 3. **Form validation strategy**: Create a `forms.py` module with base forms:
>    - `SearchForm` (search box)
>    - `VideoForm` (for editing videos)
>    - `PersonForm`, `DogForm`, etc.
> 4. **Client-side validation**: Match server-side with HTML5 validation for better UX
>
> --- Claude

> ### Claude's Note on Authentication
>
> **Blueprint separation is essential** (agree with Gemini). Specific recommendations:
>
> 1. **User table schema**:
> ```sql
> CREATE TABLE users (
>     user_id INTEGER PRIMARY KEY AUTOINCREMENT,
>     username TEXT UNIQUE NOT NULL,
>     email TEXT UNIQUE NOT NULL,
>     password_hash TEXT NOT NULL,
>     role TEXT DEFAULT 'viewer',  -- 'admin', 'editor', 'viewer'
>     created_at TEXT DEFAULT CURRENT_TIMESTAMP,
>     last_login TEXT
> );
> ```
>
> 2. **Admin blueprint structure**:
> ```
> blueprints/
>   __init__.py
>   admin.py        # Admin-only routes
>   auth.py         # Login/logout
> ```
>
> 3. **Role-based access**: Don't just use `@login_required`—create custom decorators:
>    - `@admin_required` for full admin access
>    - `@editor_required` for CRUD operations
>
> 4. **Initial user creation**: Add a Flask CLI command:
> ```python
> @app.cli.command()
> def create_admin():
>     """Create initial admin user"""
>     # Prompt for credentials and create user
> ```
>
> 5. **Session security**: Set session cookie flags in config:
> ```python
> SESSION_COOKIE_SECURE = True  # HTTPS only in production
> SESSION_COOKIE_HTTPONLY = True
> SESSION_COOKIE_SAMESITE = 'Lax'
> ```
>
> --- Claude

> ### Claude's Note on Pagination & Performance
>
> **Strong agreement with Gemini's FTS5 recommendation**. This is a perfect time to implement it since you're already touching the database layer.
>
> 1. **FTS5 implementation**:
> ```sql
> -- Create virtual table for full-text search
> CREATE VIRTUAL TABLE videos_fts USING fts5(
>     title,
>     description,
>     content=videos,
>     content_rowid=video_id
> );
>
> -- Create triggers to keep FTS table in sync
> CREATE TRIGGER videos_ai AFTER INSERT ON videos BEGIN
>     INSERT INTO videos_fts(rowid, title, description)
>     VALUES (new.video_id, new.title, new.description);
> END;
> ```
>
> 2. **Pagination helper** (avoid third-party libs for this simple case):
> ```python
> def paginate(query, page, per_page):
>     """Simple pagination helper"""
>     total = query.count()
>     items = query.limit(per_page).offset((page - 1) * per_page).all()
>     return {
>         'items': items,
>         'page': page,
>         'per_page': per_page,
>         'total': total,
>         'pages': (total + per_page - 1) // per_page
>     }
> ```
>
> 3. **Index verification**: Confirm these indexes exist:
>    - `CREATE INDEX idx_videos_upload_date ON videos(upload_date);`
>    - `CREATE INDEX idx_video_people_video_id ON video_people(video_id);`
>    - `CREATE INDEX idx_video_dogs_video_id ON video_dogs(video_id);`
>
> 4. **Query optimization**: The current sidebar queries for people/dogs run on every page load. Consider:
>    - Caching these with Flask-Caching (add to Phase 2A or 2B)
>    - Or move to application startup and store in `app.config`
>
> 5. **format_duration fix**: Gemini is right—use regex:
> ```python
> import re
>
> def format_duration(duration_str):
>     """Format ISO 8601 duration to readable format"""
>     if not duration_str or ':' in duration_str:
>         return duration_str or "Unknown"
>
>     match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
>     if not match:
>         return duration_str
>
>     hours, minutes, seconds = match.groups()
>     hours = int(hours or 0)
>     minutes = int(minutes or 0)
>     seconds = int(seconds or 0)
>
>     if hours:
>         return f"{hours}:{minutes:02d}:{seconds:02d}"
>     return f"{minutes}:{seconds:02d}"
> ```
>
> --- Claude

> ### Claude's Additional Recommendations
>
> **Items not covered in the original plan**:
>
> 1. **Database migrations**: Introduce Alembic now before making schema changes
>    - Helps track authentication table additions
>    - Essential for production deployments
>    - Add to execution order between #1 and #2
>
> 2. **Requirements.txt update needed**:
> ```
> Flask-WTF>=1.2.1
> Flask-Login>=0.6.3
> python-dotenv>=1.0.0
> # Consider for Phase 2B:
> # Flask-Caching>=2.1.0
> # alembic>=1.13.0
> ```
>
> 3. **Static file versioning**: Prevent theme CSS caching issues
> ```python
> # In config
> SEND_FILE_MAX_AGE_DEFAULT = 0 if DEBUG else 31536000
>
> # In templates
> <link rel="stylesheet" href="{{ url_for('static', filename='css/fairyfloss.css', v=config.VERSION) }}">
> ```
>
> 4. **Testing foundation**: Add basic tests now (unit + integration)
>    - Test config loading
>    - Test error handlers
>    - Test authentication flows
>    - Sets foundation for TDD in Phase 2B/2C
>
> 5. **Context processors**: Your sidebar queries could be DRY-er:
> ```python
> @app.context_processor
> def inject_sidebar_data():
>     """Make sidebar data available to all templates"""
>     if not hasattr(g, 'sidebar_people'):
>         conn = get_db_connection()
>         g.sidebar_people = conn.execute('...').fetchall()
>         g.sidebar_dogs = conn.execute('...').fetchall()
>         conn.close()
>     return {'sidebar_people': g.sidebar_people, 'sidebar_dogs': g.sidebar_dogs}
> ```
>
> --- Claude

> ### Claude's Revised Execution Order
>
> **Suggested modification** to reduce friction:
>
> 1. **Configuration refactor** + requirements.txt update
> 2. **Database migrations setup** (Alembic init)
> 3. **Logging & error pages** (leverages config, establishes patterns)
> 4. **CSRF scaffolding** (Flask-WTF, protect search form)
> 5. **Authentication groundwork** (User model, migration, Flask-Login, blueprints)
> 6. **FTS5 implementation** (migration + search refactor)
> 7. **Pagination rollout** (routes + templates)
> 8. **Context processors** (DRY up sidebar data)
> 9. **Testing foundation** (basic test suite)
>
> This order ensures migrations are ready before any schema changes (auth, FTS5) and groups related work together.
>
> --- Claude


## Codex Follow-up

- **Scope discipline**: Gemini and Claude flagged smart enhancements (FTS5 search, caching, context processors), but these stretch beyond the Phase 2A mandate. Let’s log them for Phase 2B/2C so 2A stays focused on stability plumbing (config, logging, CSRF, auth groundwork, pagination).
- **Config plan alignment**: I’m on board with the single `config.py` that loads environment secrets. We just need to ensure the secret key comes from `.env`/environment and fails fast if missing in production.
- **Logging snippet**: The rotating file handler example is good; add `Path('logs').mkdir(exist_ok=True)` (or similar) before attaching the handler so deployments don’t crash when the directory is absent.
- **Error templates**: Fully agree—extend `base.html` so theme switching and navigation persist on 404/500 pages.
- **Pagination helper**: Claude’s helper assumes an ORM. We’ll craft a SQLite-friendly version that does an explicit `COUNT(*)` plus `LIMIT/OFFSET` using `sqlite3` cursors.
- **Duration parsing**: Adopting the regex-based `format_duration` update is low risk and cleans up odd ISO-8601 cases.
- **Alembic decision**: If we introduce Alembic now, we must decide whether to keep raw `sqlite3` (requiring batch mode migrations) or adopt SQLAlchemy. Worth clarifying before auth tables/FTS5 work begins.
- **Requirements updates**: Let’s add `Flask-WTF`, `Flask-Login`, and `python-dotenv` with versions compatible with our Python baseline when we do the configuration pass.
- **Sidebar context processor**: I like the direction, but we should fetch sidebar data per request and close the connection immediately—avoid storing a live connection on `g`.

