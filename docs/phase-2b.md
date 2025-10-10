# Phase 2B: API & CRUD Development

**Status:** In Progress - Step 1.3 Complete (+ Image Features) ✓
**Goal:** Deliver a fully functional admin panel with CRUD operations for all major data models, a versioned REST API, and hardened security.

## Progress Update

**Step 1.1: Blueprint Restructuring** ✓ COMPLETE
- Created admin.py, crud.py, api/__init__.py, api/v1/__init__.py blueprints
- Registered all blueprints in app.py
- Verified all existing routes still functional
*Completed by Claude*

**Step 1.2: Service Layer Scaffold** ✓ COMPLETE
- Created services/base_service.py with custom exceptions (NotFoundError, ValidationError, DatabaseError, ReferenceError)
- Created migration 005_add_soft_delete.sql (adds deleted_at and deleted_by columns to all major tables)
- Implemented services/person_service.py with complete functionality:
  - CRUD operations (create, read, update, delete, list)
  - Soft delete (default) and hard delete (with reference checking)
  - Restore functionality for soft-deleted items
  - Alias management (get, add, remove, update "also known as" names)
- Written 39 comprehensive unit tests (21 core + 18 alias tests) - ALL PASSING
- Service layer pattern validated and ready for replication to other entities
*Completed by Claude*

**Step 1.3: Forms Library** ✓ COMPLETE
- Created forms/crud_forms.py with comprehensive WTForms for all entities:
  - PersonForm, DogForm, VideoForm, TripForm, SeriesForm
  - UserCreateForm, UserEditForm (for admin panel user management)
  - AliasForm (for managing "also known as" names)
  - VideoRelationshipForm (for many-to-many relationships)
- Implemented custom validators:
  - UniqueValue (checks database for duplicate names/values)
  - ValidDateRange (ensures end dates are after start dates)
  - ValidYouTubeID (validates 11-character YouTube video IDs)
  - ValidDuration (validates HH:MM:SS or MM:SS time formats)
- All forms include proper field validation, length limits, and user-friendly placeholders
- Forms are reusable for both CRUD UI (HTML) and REST API (JSON validation)
- Written 21 comprehensive unit tests - ALL PASSING
*Completed by Claude*

**Step 1.3.1: Image Upload & Privacy Features** ✓ COMPLETE
- Created migration 006_add_image_fields.sql:
  - Added photo_url, photo_local_path, photo_visible to people table
  - Added photo_url, photo_local_path, photo_visible to dogs table
  - Created indexes for photo_visible queries
- Updated services/person_service.py:
  - Added photo_local_path and photo_visible parameters to create_person()
  - Added photo fields to allowed update fields
  - Added validation for photo_local_path (max 500 chars)
- Updated PersonForm and DogForm:
  - Added photo_url field (external URL input)
  - Added photo_file field (file upload with FileAllowed validator)
  - Added photo_visible checkbox (privacy control, default: visible)
  - Supports both URL-based and uploaded photos
- Updated display templates:
  - person_detail.html now displays photo if visible and exists
  - dog_detail.html now displays photo if visible and exists
  - Photos displayed with responsive sizing, rounded corners, and shadow
  - Graceful fallback if image fails to load (onerror handler)
- Admin privacy control:
  - photo_visible boolean allows hiding photos for privacy
  - Unchecking "Photo Visible" hides photo from public view
  - Field editable via CRUD forms (when built in Step 3)
*Completed by Claude*

**Implementation Notes:**
- Photos can be provided via URL (photo_url) or uploaded file (photo_file)
- Uploaded files stored locally (photo_local_path) with preference over URLs
- Privacy toggle (photo_visible) gives admin control over photo visibility
- Templates check both photo_visible AND photo existence before displaying
- Graceful degradation: if image fails to load, it's hidden automatically
- Forms support multiple image formats: JPG, JPEG, PNG, WebP

**Next Steps:** Step 1.4 - Security Infrastructure

---

## Executive Summary

Phase 2B focuses on building the administrative and API layer for the Posa Wiki, enabling content management and programmatic access. We will:

1. **Defer the SQLAlchemy migration** - Continue with sqlite3, focus on features not refactoring
2. **Build a service layer** - Shared business logic between CRUD UI and REST API (DRY principle)
3. **Use progressive enhancement** - Start with simple server-side forms, add polish later
4. **Implement incrementally** - Validate pattern on simple entities (People) before complex ones (Videos)

**Timeline:** 20-25 working days solo, 12-15 days with parallel development
**Deferred to Phase 3:** SQLAlchemy + Alembic, password reset flows, advanced optimization

---

## Architectural Principles

### 1. Service Layer Pattern
**Rationale:** DRY principle - API and CRUD share the same validation and data access logic

Both the CRUD UI and REST API need identical business logic. By centralizing this in a service layer, we:
- Eliminate code duplication
- Ensure API and CRUD always stay in sync
- Make the code testable (services are pure functions)
- Enable future refactoring (easy to swap sqlite3 → SQLAlchemy)

**Example:**
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

### 2. Form-First Validation
**Rationale:** Flask-WTF is already integrated, provides CSRF protection, and works for both HTML and API

Use WTForms for all validation. The API can call `form.validate()` without rendering HTML:

```python
# forms/crud_forms.py
class VideoForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description')

# API endpoint validates with same form
form = VideoForm(data=request.json)
if not form.validate():
    return jsonify({'errors': form.errors}), 400
```

### 3. Progressive Enhancement UX
**Rationale:** Simplicity first - avoid premature complexity

- **Start:** Server-side form pages (simple, reliable, browser handles everything)
- **Later:** Add AJAX/modal enhancements if desired

Modal UX requires: AJAX handlers, partial templates, JS state management, error handling
Server-side forms require: One route, one template

**Decision:** Build server-side forms first, modal enhancement is optional polish

### 4. Defer SQLAlchemy Migration
**Rationale:** Focus on features, not refactoring

- Current sqlite3 + row_factory pattern works well (610 lines in app.py)
- SQLAlchemy migration would touch every data access point (massive scope)
- Alembic without SQLAlchemy is awkward (they're designed together)
- Better as dedicated Phase 3 "Technical Debt" sprint

**Decision:** Continue with sqlite3, build service layer that abstracts data access for future ORM swap

### 5. Incremental Entity Rollout
**Rationale:** Validate pattern before scaling

1. Build complete pattern for ONE entity (People - simplest schema)
2. Validate service → CRUD → API → tests all work
3. Copy pattern to remaining entities (Dogs, Videos, Trips/Series)
4. Catches architecture issues early when changing is cheap

---

## Implementation Plan

### **Step 1: Foundation & Infrastructure**
*Build reusable components that all features depend on*

**1.1. Blueprint Restructuring**
- Extract `/admin` routes from app.py to `blueprints/admin.py`
- Create `blueprints/crud.py` for entity edit routes
- Create `blueprints/api/__init__.py` and `blueprints/api/v1/` structure
- Move app.py routes to appropriate blueprints (keep app.py < 200 lines)

**1.2. Service Layer Scaffold**
- Create `services/` directory with `base_service.py` (shared utilities)
- Implement `services/person_service.py` with basic CRUD operations
- Add error handling: custom exceptions (`NotFoundError`, `ValidationError`, `DatabaseError`)
- Implement soft delete pattern (default) with `deleted_at` column
- Implement hard delete with reference cleanup and warnings
- Write unit tests for service layer (mock DB, test logic)

**Deletion Strategy:**
- **Soft Delete (Default):** Mark `deleted_at = NOW()`, preserve all references, can be restored
- **Hard Delete (Admin Only):** Check for references, warn user, cascade delete if confirmed
- **Reference Cleanup:** Service layer checks `video_people`, `video_dogs` etc. before hard delete
- See "Referential Integrity & Deletion Strategy" section below for details

**1.3. Forms Library**
- Create `forms/crud_forms.py` with reusable field sets
- Implement `PersonForm`, `DogForm`, `VideoForm` with validation rules
- Add custom validators (e.g., unique name, valid dates, file uploads)

**1.4. Security Infrastructure**
- Add 403 error handler to app.py (theme-aware template)
- Create `utils/api_auth.py` for token-based authentication
- Implement rate limiting decorator (`@rate_limit('60 per minute')`)
- Add audit logging utility: `utils/audit_log.py` (logs to DB table)

**Why this order?** These are foundational components that every subsequent step depends on. Building them first prevents rework.

---

### **Step 2: Admin Panel & User Management**
*Self-contained feature that validates the architecture*

**2.1. Admin Blueprint Shell**
- Create admin layout template extending `base.html`
- Add navigation: Dashboard, Users, Audit Log
- Implement breadcrumb component
- Add admin landing page with stats (user count, recent activity)

**2.2. User Management CRUD**
- List users (paginated, searchable by username/email/role)
- Create user form (reuse/extend `LoginForm` pattern)
- Edit user (username, email, role, active status)
- Deactivate user (soft delete, preserve for audit trail)
- All routes protected with `@admin_required`

**2.4. Deleted Items Management**
- Create `/admin/trash` view showing all soft-deleted items
- Filter by entity type (People, Dogs, Videos, Users)
- Restore button for each item (calls service `restore_*` method)
- Hard delete button with confirmation modal showing:
  - Count of referencing entities (e.g., "appears in 15 videos")
  - List of affected items
  - Type "DELETE" confirmation required
  - Cascade deletes all references if confirmed

**2.3. Audit Logging**
- Create `audit_log` table migration script (004_create_audit_log.sql)
- Log user changes (created, updated, deactivated) with who/when/what
- Display audit log page (filterable by user, action, date)
- Add audit decorator: `@audit_action('user.update')`

**Why this order?** User management is isolated from video data complexity. Success here proves service layer → forms → CRUD → audit pipeline works.

---

### **Step 3: Entity CRUD (Incremental Rollout)**
*Build once, copy pattern to all entities*

**3A. People CRUD** *(Simplest entity - validate pattern)*
- Service: `services/person_service.py` (create, read, update, delete, list)
- Routes: `/crud/person/`, `/crud/person/new`, `/crud/person/<id>/edit`, `/crud/person/<id>/delete`
- Forms: `PersonForm` with name, bio, photo URL validation
- Templates: `crud/person_list.html`, `crud/person_form.html`
- All routes: `@editor_required` + audit logging
- Tests: Integration tests for full CRUD cycle

**3B. Dogs CRUD** *(Copy & adapt People pattern)*
- Service: `services/dog_service.py`
- Routes: Same pattern as People
- Forms: `DogForm` with breed, color, age fields
- Templates: Copy People templates, adjust fields
- Tests: Copy People tests, adjust assertions

**3C. Videos CRUD** *(Complex entity - relationships)*
- Service: `services/video_service.py`
- Handle relationships: video_people, video_dogs, video_trips, video_series
- Multi-select form fields for related entities (WTForms FieldList)
- Thumbnail upload handling
- Complex validation (duration format, YouTube URL)

**3D. Trips & Series CRUD**
- Services: `trip_service.py`, `series_service.py`
- Nested video management (videos belong to trip/series)
- Order/sequence handling for episodes

**Why this order?** Start simple (People/Dogs have minimal relationships), validate the pattern works, then tackle complex entities (Videos have many relationships). Each entity takes ~2-4 hours once pattern is established.

---

### **Step 4: REST API (Parallel to CRUD)**
*API endpoints reuse services built in Step 3*

**4.1. API Infrastructure**
- Create `blueprints/api/v1/__init__.py` with version prefix (`/api/v1`)
- Implement token generation endpoint: `POST /api/v1/auth/token`
- Add `@token_required` decorator using JWT or simple token table
- CSRF exemption for API blueprint (`csrf.exempt(api_bp)`)
- Rate limiting on all API endpoints
- Error response formatter (consistent JSON structure)

**4.2. Entity Endpoints** *(Build alongside Step 3)*

When People CRUD is done → Add `/api/v1/people` endpoints
When Dogs CRUD is done → Add `/api/v1/dogs` endpoints

Pattern for each entity:
- `GET /api/v1/people` - List (paginated, filterable)
- `GET /api/v1/people/<id>` - Get one
- `POST /api/v1/people` - Create (auth required)
- `PUT /api/v1/people/<id>` - Update (auth required)
- `DELETE /api/v1/people/<id>` - Delete (auth required)

Validation using same WTForms as CRUD UI
Service layer calls (same code path as CRUD)

**4.3. Search API**
- `GET /api/v1/search?q=query` - Uses existing FTS5 index
- Returns unified results (videos, people, dogs)
- Supports filtering by entity type

**4.4. API Documentation**
- Create `docs/api.md` with endpoint reference
- Include authentication instructions
- Provide curl examples for each endpoint
- Add rate limit information

**Why this order?** Building API endpoints immediately after each entity's CRUD validates that service layer is truly reusable. Catches coupling issues early.

---

### **Step 5: Authentication Hardening**
*Security improvements to auth system*

**5.1. Rate Limiting**
- Login endpoint: 5 attempts per 15 minutes per IP
- API endpoints: 60 requests per minute per token
- Implement with Flask-Limiter or custom decorator

**5.2. Password Policy**
- Minimum length: 8 characters
- Require mix of character types (optional, configurable)
- Password strength indicator in UI
- Reject common passwords (check against list)

**5.3. Session Security**
- Session timeout after 24 hours (configurable)
- "Remember me" extends to 30 days
- Force logout on password change
- Add "Last login from: IP" display on profile

**Why this order?** Auth hardening is easier after CRUD is complete. Features first, then security polish.

---

### **Step 6: Testing & Validation**
*Quality assurance across all new features*

**6.1. Integration Tests**
- CRUD workflows for each entity (create → read → update → delete)
- API endpoint tests (auth, validation, permissions)
- Access control tests (viewer/editor/admin roles)
- Audit logging verification

**6.2. Manual QA Checklist**
- Error pages (403/404/500) in all three themes
- Error pages when logged in vs. logged out
- CRUD operations with different roles
- Form validation (client and server side)
- API auth flows (missing token, invalid token, expired token)

**6.3. Performance**
- Index verification: `EXPLAIN QUERY PLAN` on list queries
- Load test: 100 concurrent API requests
- Pagination performance with 1000+ records
- Search performance with FTS5

**Why last?** Testing validates completed features. Build features first, then validate comprehensively.

---

## Directory Structure (Post-Phase 2B)

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

## Key Architectural Benefits

### 1. DRY (Don't Repeat Yourself)
- Service layer eliminates duplicate validation/data access between CRUD and API
- WTForms shared between HTML forms and API validation
- Templates can be reused (list/form patterns are similar across entities)

### 2. Testability
- Services are pure Python functions (easy to unit test)
- Routes are thin adapters (integration test the full flow)
- Mocking is simple (mock DB connection in services)

### 3. Maintainability
- Changes to business logic happen in ONE place (service layer)
- API and CRUD automatically stay in sync
- Blueprint structure keeps codebase organized as it grows

### 4. Future-Proofing
- Service layer abstracts data access (easy to swap sqlite3 → SQLAlchemy later)
- API versioning allows breaking changes (v2, v3) without breaking v1 clients
- Audit logging provides compliance trail and debugging history

### 5. Progressive Complexity
- Start simple (server-side forms), add polish later (modals/AJAX)
- Build one entity completely, then copy pattern (fast iteration)
- Defer big refactors (SQLAlchemy) until features are stable

---

## Risk Mitigation

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

## Implementation Timeline

### Solo Developer (6-hour workdays)

- **Step 1 (Foundation):** 3-4 days
- **Step 2 (Admin Panel):** 2-3 days
- **Step 3A (People CRUD):** 2 days
- **Step 3B (Dogs CRUD):** 1 day (copy pattern)
- **Step 3C (Videos CRUD):** 3 days (complex relationships)
- **Step 3D (Trips/Series):** 2 days
- **Step 4 (API):** 3-4 days (parallel with Step 3, incremental)
- **Step 5 (Auth Hardening):** 2 days
- **Step 6 (Testing/QA):** 2-3 days

**Total: 20-25 working days (4-5 weeks)**

### Parallel Development (3 developers)

- **Dev 1:** Foundation + Admin Panel (Steps 1-2)
- **Dev 2:** Entity CRUD (Step 3) - starts after Step 1 done
- **Dev 3:** API (Step 4) - starts after Step 1 done

**Total: 12-15 working days (2.5-3 weeks)**

---

## Referential Integrity & Deletion Strategy

### Soft Delete (Default Behavior)

**Purpose:** Preserve data and references for audit trail, allow restoration

**Implementation:**
- All major tables get `deleted_at TIMESTAMP NULL` and `deleted_by INTEGER` columns
- Default queries filter: `WHERE deleted_at IS NULL`
- Soft-deleted items hidden from normal views but preserved in database
- All references remain intact (video_people, video_dogs, etc.)

**Service Methods:**
```python
def delete_person(person_id, deleted_by_user_id):
    """Soft delete - marks as deleted, preserves all data and references"""
    conn.execute(
        'UPDATE people SET deleted_at = CURRENT_TIMESTAMP, deleted_by = ? WHERE person_id = ?',
        (deleted_by_user_id, person_id)
    )

def restore_person(person_id):
    """Restore soft-deleted person - all references still intact"""
    conn.execute('UPDATE people SET deleted_at = NULL, deleted_by = NULL WHERE person_id = ?', (person_id,))
```

### Hard Delete (Admin Panel Only)

**Purpose:** Permanently remove data when cleanup is needed

**Implementation:**
- Check for references before deletion
- Warn admin about affected entities
- Require explicit confirmation
- Cascade delete all references
- Log action in audit_log

**Service Method:**
```python
def hard_delete_person(person_id, force=False):
    """Permanently delete person (checks references first)"""
    conn = get_db_connection()

    # Count references
    video_count = conn.execute(
        'SELECT COUNT(*) FROM video_people WHERE person_id = ?',
        (person_id,)
    ).fetchone()[0]

    if video_count > 0 and not force:
        raise ValidationError(
            f'Cannot delete: {video_count} videos reference this person. '
            f'Use force=True to cascade delete.'
        )

    # Cascade delete references
    conn.execute('DELETE FROM video_people WHERE person_id = ?', (person_id,))

    # Delete entity
    conn.execute('DELETE FROM people WHERE person_id = ?', (person_id,))
    conn.commit()
```

**UI Flow (Admin Panel):**
1. Admin clicks "Delete ×" on soft-deleted item in trash view
2. Modal shows:
   - "Permanently delete Person Name?"
   - "Appears in 15 videos: [list]"
   - "Will remove all references"
   - Type "DELETE" to confirm
3. Backend calls `hard_delete_person(id, force=True)`
4. Audit log records: `"person.hard_deleted: removed with 15 video references"`

### Migration Required

```sql
-- 005_add_soft_delete.sql
ALTER TABLE people ADD COLUMN deleted_at TEXT DEFAULT NULL;
ALTER TABLE people ADD COLUMN deleted_by INTEGER REFERENCES users(user_id);
ALTER TABLE dogs ADD COLUMN deleted_at TEXT DEFAULT NULL;
ALTER TABLE dogs ADD COLUMN deleted_by INTEGER REFERENCES users(user_id);
ALTER TABLE videos ADD COLUMN deleted_at TEXT DEFAULT NULL;
ALTER TABLE videos ADD COLUMN deleted_by INTEGER REFERENCES users(user_id);
ALTER TABLE trips ADD COLUMN deleted_at TEXT DEFAULT NULL;
ALTER TABLE trips ADD COLUMN deleted_by INTEGER REFERENCES users(user_id);
ALTER TABLE users ADD COLUMN deleted_at TEXT DEFAULT NULL;
ALTER TABLE users ADD COLUMN deleted_by INTEGER REFERENCES users(user_id);

CREATE INDEX idx_people_deleted_at ON people(deleted_at);
CREATE INDEX idx_dogs_deleted_at ON dogs(deleted_at);
CREATE INDEX idx_videos_deleted_at ON videos(deleted_at);
CREATE INDEX idx_trips_deleted_at ON trips(deleted_at);
CREATE INDEX idx_users_deleted_at ON users(deleted_at);
```

### Reference Tables by Entity

**People:**
- `video_people` (many-to-many with videos)

**Dogs:**
- `video_dogs` (many-to-many with videos)

**Videos:**
- `video_people` (many-to-many with people)
- `video_dogs` (many-to-many with dogs)
- `video_versions` (one-to-many with trips)

**Trips/Series:**
- `video_versions` (one-to-many with videos)

**Users:**
- `audit_log.user_id` (one-to-many)
- `people.deleted_by`, `dogs.deleted_by`, etc. (one-to-many)

### Auto-Cleanup (Future Enhancement)

Optional Flask CLI command to clean up old soft-deleted items:
```bash
flask cleanup-deleted --days 30  # Hard delete anything deleted >30 days ago
```

---

## Deferred to Phase 3

**SQLAlchemy + Alembic Migration**
- Major refactor touching all data access
- Better as dedicated sprint after features are stable
- Service layer makes this swap easy

**Password Reset Flows**
- Requires email infrastructure (SMTP, templates, token generation)
- Not critical for initial admin panel

**Advanced Optimization**
- Connection pooling (SQLAlchemy brings this)
- Query caching (premature optimization)
- Redis session store (overkill for current scale)

---

*Plan finalized by Claude, synthesizing input from Codex and Gemini*
*Ready for implementation on branch: `2b-dev`*
