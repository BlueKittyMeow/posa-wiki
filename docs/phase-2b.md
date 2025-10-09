# Phase 2B Prep Notes

## Feature Targets
- Access control enforcement for all edit/admin routes
- Admin panel blueprint with user management UI and audit visibility
- CRUD operations for videos, people, dogs, trips (CSRF-protected)
- REST API (versioned) with token-based auth and CSRF exemptions
- Service layer for business logic reusability (API + CRUD share code)
- Error-page verification across themes & auth states
- Authentication hardening (rate limiting, password policy)
- CSRF coverage for new API/CRUD forms

**Deferred to Phase 3:**
- SQLAlchemy + Alembic migration (major refactor, separate from feature work)
- Password reset flows (requires email infrastructure)
- Advanced optimization (connection pooling, query caching)

## Implementation Plan (Codex)
1. **Data Layer Foundations**
   - Introduce SQLAlchemy ORM alongside existing sqlite3 usage.
   - Configure session/engine with pooling and tie into app factory.
   - Add Alembic with initial migration reflecting current schema; future changes go through migrations.
2. **Security & Access Control**
   - Ensure global 403 handler and flash messaging for authorization failures.
   - Add rate limiting/password rules and lockout strategy to auth module.
   - Write integration tests covering `@editor_required`/`@admin_required` on placeholder routes.
3. **Admin Blueprint Skeleton**
   - Create `/admin` blueprint with layout, navigation, and dashboard placeholder.
   - Surface profile/logout links and breadcrumbs for UX consistency.
4. **User Management Module**
   - Build CRUD for users (list, create, edit, deactivate) using SQLAlchemy models.
   - Record audit log entries (who/when/what) for each change.
   - Add pagination/search for user list to handle growth.
5. **Entity CRUD (Modal UX)**
   - Implement RESTful endpoints + templates for inline modals starting with People/Dogs, then Videos/Trips.
   - Use reusable JavaScript to open/save modals; ensure server-side validation and CSRF tokens.
   - Gate routes with `@editor_required`; surface success/error alerts.
6. **Public REST API**
   - Versioned blueprint (`/api/v1`), JSON responses for videos/people/dogs/trips/search.
   - Apply token/JWT auth for mutations; CSRF exempt but rate-limited.
   - Provide API docs (OpenAPI or markdown) for consumers.
7. **Performance & Testing**
   - Review/optimize heavy queries, add indexes where necessary.
   - Run load tests on paginated views & API.
   - Manually verify 404/500 pages under each theme + auth state.
   - Extend automated tests to cover new CRUD/API flows.

— Codex

## Revised Implementation Plan (Claude)

### Architecture Decisions

**1. Skip SQLAlchemy for Phase 2B** *(Rationale: Focus on features, not refactoring)*
- Current sqlite3 + row_factory pattern works well (610 lines in app.py)
- SQLAlchemy migration would touch every data access point (massive scope)
- Alembic without SQLAlchemy is awkward (they're designed together)
- Better as dedicated Phase 3 "Technical Debt" sprint
- **Decision**: Continue with sqlite3, build service layer that abstracts data access for future ORM swap

**2. Service Layer Pattern** *(Rationale: DRY principle, API/CRUD reusability)*
- Both CRUD UI and REST API need same business logic (validation, data access)
- Services return dicts/domain objects, NOT Flask Response objects
- Routes become thin adapters (handle request/response, call services)
- Example structure:
  ```python
  # services/video_service.py
  def get_video(video_id):
      """Returns dict or raises NotFound"""
      conn = get_db_connection()
      video = conn.execute('SELECT * FROM videos WHERE video_id = ?', (video_id,)).fetchone()
      if not video: raise NotFound(f"Video {video_id} not found")
      return dict(video)

  # blueprints/crud.py (CRUD UI)
  @crud_bp.route('/video/<id>')
  @editor_required
  def edit_video(id):
      video = video_service.get_video(id)  # Service call
      return render_template('crud/video_form.html', video=video)

  # blueprints/api/v1/videos.py (API)
  @api_bp.route('/videos/<id>')
  @token_required
  def get_video_api(id):
      video = video_service.get_video(id)  # Same service call!
      return jsonify(video)
  ```

**3. Form-First Validation** *(Rationale: Flask-WTF already integrated, CSRF built-in)*
- Use WTForms for all validation (CRUD and API)
- API can use `form.validate()` without rendering HTML
- Single source of truth for field rules
- Example:
  ```python
  # forms/video_forms.py
  class VideoForm(FlaskForm):
      title = StringField('Title', validators=[DataRequired(), Length(max=200)])
      description = TextAreaField('Description')

  # API endpoint validates with same form
  form = VideoForm(data=request.json)
  if not form.validate():
      return jsonify({'errors': form.errors}), 400
  ```

**4. Progressive Enhancement UX** *(Rationale: Simplicity first, avoid premature complexity)*
- Start with server-side form pages (simple, reliable)
- Add AJAX/modal enhancements later if desired
- Modal UX requires: AJAX handlers, partial templates, JS state management, error handling
- Server-side forms require: One route, one template, browser handles everything
- **Decision**: Build server-side forms first, modal enhancement is optional polish

**5. Incremental Entity Rollout** *(Rationale: Validate pattern before scaling)*
- Build complete pattern for ONE entity (People - simplest schema)
- Validate service → CRUD → API → tests all work
- Copy pattern to remaining entities (Dogs, Videos, Trips/Series)
- Catches architecture issues early when changing is cheap

### Revised Implementation Order

#### **Step 1: Foundation & Infrastructure**
*Build reusable components that all features depend on*

- **1.1 Blueprint Restructuring**
  - Extract `/admin` routes from app.py to `blueprints/admin.py`
  - Create `blueprints/crud.py` for entity edit routes
  - Create `blueprints/api/__init__.py` and `blueprints/api/v1/` structure
  - Move app.py routes to appropriate blueprints (keep app.py < 200 lines)

- **1.2 Service Layer Scaffold**
  - Create `services/` directory with `base_service.py` (shared utilities)
  - Implement `services/video_service.py` with basic CRUD operations
  - Add error handling: custom exceptions (`NotFoundError`, `ValidationError`)
  - Write unit tests for service layer (mock DB, test logic)

- **1.3 Forms Library**
  - Create `forms/crud_forms.py` with reusable field sets
  - Implement `VideoForm`, `PersonForm`, `DogForm` with validation rules
  - Add custom validators (e.g., unique title, valid dates, file uploads)

- **1.4 Security Infrastructure**
  - Add 403 error handler to app.py (theme-aware template)
  - Create `utils/api_auth.py` for token-based authentication
  - Implement rate limiting decorator (`@rate_limit('60 per minute')`)
  - Add audit logging utility: `utils/audit_log.py` (logs to DB table)

**Why this order?** These are foundational components that every subsequent step depends on. Building them first prevents rework.

---

#### **Step 2: Admin Panel & User Management**
*Self-contained feature that validates the architecture*

- **2.1 Admin Blueprint Shell**
  - Create admin layout template extending `base.html`
  - Add navigation: Dashboard, Users, Audit Log
  - Implement breadcrumb component
  - Add admin landing page with stats (user count, recent activity)

- **2.2 User Management CRUD**
  - List users (paginated, searchable by username/email/role)
  - Create user form (reuse/extend `LoginForm` pattern)
  - Edit user (username, email, role, active status)
  - Deactivate user (soft delete, preserve for audit trail)
  - All routes protected with `@admin_required`

- **2.3 Audit Logging**
  - Create `audit_log` table migration script
  - Log user changes (created, updated, deactivated)
  - Display audit log page (filterable by user, action, date)
  - Add audit decorator: `@audit_action('user.update')`

**Why this order?** User management is isolated from video data complexity. Success here proves service layer → forms → CRUD → audit pipeline works.

---

#### **Step 3: Entity CRUD (Incremental Rollout)**
*Build once, copy pattern to all entities*

**Phase 3A: People CRUD** *(Simplest entity - validate pattern)*
- Service: `services/person_service.py` (create, read, update, delete, list)
- Routes: `blueprints/crud.py` - `/crud/person/`, `/crud/person/new`, `/crud/person/<id>/edit`, `/crud/person/<id>/delete`
- Forms: `PersonForm` with name, bio, photo URL validation
- Templates: `crud/person_list.html`, `crud/person_form.html`
- All routes: `@editor_required` + audit logging
- Tests: Integration tests for full CRUD cycle

**Phase 3B: Dogs CRUD** *(Copy & adapt People pattern)*
- Service: `services/dog_service.py`
- Routes: Same pattern as People
- Forms: `DogForm` with breed, color, age fields
- Templates: Copy People templates, adjust fields
- Tests: Copy People tests, adjust assertions

**Phase 3C: Videos CRUD** *(Complex entity - relationships)*
- Service: `services/video_service.py`
- Handle relationships: video_people, video_dogs, video_trips, video_series
- Multi-select form fields for related entities
- Thumbnail upload handling
- Complex validation (duration format, YouTube URL)

**Phase 3D: Trips & Series CRUD**
- Services: `trip_service.py`, `series_service.py`
- Nested video management (videos belong to trip/series)
- Order/sequence handling for episodes

**Why this order?** Start simple (People/Dogs have minimal relationships), validate the pattern works, then tackle complex entities (Videos have many relationships). Each entity takes ~2-4 hours once pattern is established.

---

#### **Step 4: REST API (Parallel to CRUD)**
*API endpoints reuse services built in Step 3*

- **4.1 API Infrastructure**
  - Create `blueprints/api/v1/__init__.py` with version prefix
  - Implement token generation endpoint: `POST /api/v1/auth/token`
  - Add `@token_required` decorator using JWT or simple token table
  - CSRF exemption for API blueprint (`csrf.exempt(api_bp)`)
  - Rate limiting on all API endpoints
  - Error response formatter (consistent JSON structure)

- **4.2 Entity Endpoints** *(Build alongside Step 3)*
  - When People CRUD is done → Add `/api/v1/people` endpoints
  - When Dogs CRUD is done → Add `/api/v1/dogs` endpoints
  - Pattern for each entity:
    - `GET /api/v1/people` - List (paginated, filterable)
    - `GET /api/v1/people/<id>` - Get one
    - `POST /api/v1/people` - Create (auth required)
    - `PUT /api/v1/people/<id>` - Update (auth required)
    - `DELETE /api/v1/people/<id>` - Delete (auth required)
  - Validation using same WTForms as CRUD UI
  - Service layer calls (same code path as CRUD)

- **4.3 Search API**
  - `GET /api/v1/search?q=query` - Uses existing FTS5 index
  - Returns unified results (videos, people, dogs)
  - Supports filtering by entity type

- **4.4 API Documentation**
  - Create `docs/api.md` with endpoint reference
  - Include authentication instructions
  - Provide curl examples for each endpoint
  - Add rate limit information

**Why this order?** Building API endpoints immediately after each entity's CRUD validates that service layer is truly reusable. Catches coupling issues early.

---

#### **Step 5: Authentication Hardening**
*Security improvements to auth system*

- **5.1 Rate Limiting**
  - Login endpoint: 5 attempts per 15 minutes per IP
  - Password reset: 3 requests per hour per email
  - API endpoints: 60 requests per minute per token
  - Implement with Flask-Limiter or custom decorator

- **5.2 Password Policy**
  - Minimum length: 8 characters
  - Require mix of character types (optional, configurable)
  - Password strength indicator in UI
  - Reject common passwords (check against list)

- **5.3 Session Security**
  - Session timeout after 24 hours (or configurable)
  - "Remember me" extends to 30 days
  - Force logout on password change
  - Add "Last login from: IP" display on profile

**Why this order?** Auth hardening is easier after CRUD is complete. Features first, then security polish.

---

#### **Step 6: Testing & Validation**
*Quality assurance across all new features*

- **6.1 Integration Tests**
  - CRUD workflows for each entity (create → read → update → delete)
  - API endpoint tests (auth, validation, permissions)
  - Access control tests (viewer/editor/admin roles)
  - Audit logging verification

- **6.2 Manual QA Checklist**
  - Error pages (404/500) in all three themes
  - Error pages when logged in vs. logged out
  - CRUD operations with different roles
  - Form validation (client and server side)
  - API auth flows (missing token, invalid token, expired token)

- **6.3 Performance**
  - Index verification: `EXPLAIN QUERY PLAN` on list queries
  - Load test: 100 concurrent API requests
  - Pagination performance with 1000+ records
  - Search performance with FTS5

**Why last?** Testing validates completed features. Build features first, then validate comprehensively.

---

### Proposed Directory Structure (Post-Phase 2B)

```
/
├── app.py                     # <200 lines: app factory, config, basic routes only
├── config.py                  # Existing config (no changes)
├── blueprints/
│   ├── auth.py               # Existing (login/logout)
│   ├── admin.py              # NEW: User management, audit logs, dashboard
│   ├── crud.py               # NEW: Entity CRUD routes
│   └── api/
│       ├── __init__.py       # API error handlers, CSRF exemption
│       └── v1/
│           ├── __init__.py   # Version 1 blueprint
│           ├── auth.py       # Token generation
│           ├── videos.py     # Video endpoints
│           ├── people.py     # People endpoints
│           ├── dogs.py       # Dog endpoints
│           └── search.py     # Search endpoint
├── services/
│   ├── base_service.py       # Shared DB connection, error classes
│   ├── video_service.py      # Video business logic
│   ├── person_service.py     # Person business logic
│   ├── dog_service.py        # Dog business logic
│   ├── trip_service.py       # Trip business logic
│   └── user_service.py       # User business logic
├── forms/
│   ├── auth.py               # Existing (LoginForm)
│   └── crud_forms.py         # NEW: VideoForm, PersonForm, DogForm, etc.
├── utils/
│   ├── decorators.py         # Existing (admin_required, editor_required)
│   ├── api_auth.py           # NEW: Token auth decorator
│   ├── rate_limit.py         # NEW: Rate limiting decorator
│   └── audit_log.py          # NEW: Audit logging utility
├── templates/
│   ├── admin/
│   │   ├── layout.html       # Admin base template
│   │   ├── dashboard.html    # Admin landing page
│   │   ├── users_list.html   # User management
│   │   ├── user_form.html    # Create/edit user
│   │   └── audit_log.html    # Audit log viewer
│   ├── crud/
│   │   ├── person_list.html  # People CRUD
│   │   ├── person_form.html
│   │   ├── dog_list.html     # Dogs CRUD
│   │   ├── dog_form.html
│   │   ├── video_form.html   # Video CRUD
│   │   └── trip_form.html    # Trip CRUD
│   └── errors/
│       ├── 403.html          # NEW: Forbidden error (themed)
│       ├── 404.html          # Existing
│       └── 500.html          # Existing
├── migrations/
│   ├── 001_initial_schema.sql      # Existing
│   ├── 002_add_fts_index.sql       # Existing
│   ├── 003_create_users_table.sql  # Existing
│   └── 004_create_audit_log.sql    # NEW: Audit logging table
└── tests/                    # NEW: Test suite
    ├── test_services.py      # Service layer tests
    ├── test_crud.py          # CRUD integration tests
    ├── test_api.py           # API endpoint tests
    └── test_auth.py          # Authentication tests
```

---

### Key Architectural Benefits

1. **DRY (Don't Repeat Yourself)**
   - Service layer eliminates duplicate validation/data access between CRUD and API
   - WTForms shared between HTML forms and API validation
   - Templates can be reused (list/form patterns are similar across entities)

2. **Testability**
   - Services are pure Python functions (easy to unit test)
   - Routes are thin adapters (integration test the full flow)
   - Mocking is simple (mock DB connection in services)

3. **Maintainability**
   - Changes to business logic happen in ONE place (service layer)
   - API and CRUD automatically stay in sync
   - Blueprint structure keeps codebase organized as it grows

4. **Future-Proofing**
   - Service layer abstracts data access (easy to swap sqlite3 → SQLAlchemy later)
   - API versioning allows breaking changes (v2, v3) without breaking v1 clients
   - Audit logging provides compliance trail and debugging history

5. **Progressive Complexity**
   - Start simple (server-side forms), add polish later (modals/AJAX)
   - Build one entity completely, then copy pattern (fast iteration)
   - Defer big refactors (SQLAlchemy) until features are stable

---

### Risk Mitigation

**Risk: Service layer adds boilerplate**
- Mitigation: Use base classes and utility functions for common patterns
- Estimated overhead: ~50 lines per entity service (worth it for reusability)

**Risk: API and CRUD diverge over time**
- Mitigation: Code reviews check that both use same service layer
- Automated tests catch when one path works but other doesn't

**Risk: Forms become complex with relationships**
- Mitigation: Use WTForms FieldList for many-to-many (video_people, video_dogs)
- Fallback: Separate relationship management to second form if needed

**Risk: Timeline pressure to skip tests**
- Mitigation: Build tests incrementally (write test when building feature)
- Tests for service layer are fast to write (pure functions, no DB setup)

---

### Implementation Timeline Estimate

Assuming 1 developer, 6-hour workdays:

- **Step 1 (Foundation):** 3-4 days
- **Step 2 (Admin Panel):** 2-3 days
- **Step 3A (People CRUD):** 2 days
- **Step 3B (Dogs CRUD):** 1 day (copy pattern)
- **Step 3C (Videos CRUD):** 3 days (complex relationships)
- **Step 3D (Trips/Series):** 2 days
- **Step 4 (API):** 3-4 days (parallel with Step 3, incremental)
- **Step 5 (Auth Hardening):** 2 days
- **Step 6 (Testing/QA):** 2-3 days

**Total: ~20-25 working days (4-5 weeks)**

If multiple developers work in parallel:
- Dev 1: Foundation + Admin Panel (Steps 1-2)
- Dev 2: Entity CRUD (Step 3) - starts after Step 1 done
- Dev 3: API (Step 4) - starts after Step 1 done
**Parallel timeline: ~12-15 working days (2.5-3 weeks)**

— Claude
