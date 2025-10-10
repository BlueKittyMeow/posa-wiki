# Step 1.4: Security Infrastructure - Detailed Implementation Plan

**Status:** Planning Phase - Awaiting Approval
**Goal:** Implement production-grade security without weak points

---

## Overview

Based on research and analysis of Flask security best practices (2024/2025), this plan implements:
1. Theme-aware 403 error handling
2. JWT-based API authentication with revocation
3. Production-grade rate limiting
4. Comprehensive audit logging with PII protection

**Architecture Philosophy:**
- Security-first, but pragmatic for 2-3 admin scale
- No single points of failure
- Performance-conscious (async where needed)
- Future-proof (scales to distributed if needed)

---

## Substep Breakdown

### **1.4.1: 403 Error Handler (Theme-Aware)**
**Estimated Time:** 30 minutes
**Complexity:** Low
**Dependencies:** None

#### Implementation
Create `templates/errors/403.html` that extends base template and respects theme system.

**Template Structure:**
```html
{% extends "base.html" %}
{% block title %}403 - Access Denied{% endblock %}
{% block content %}
<div class="card" style="max-width: 600px; margin: 4rem auto;">
    <div class="card-header">
        <h2 class="card-title">🚫 Access Denied</h2>
    </div>
    <p>You don't have permission to access this resource.</p>
    <a href="{{ url_for('index') }}" class="btn">← Back to Home</a>
</div>
{% endblock %}
```

**Error Handler:**
```python
@app.errorhandler(403)
def forbidden(error):
    """403 Forbidden error handler - theme-aware"""
    return render_template('errors/403.html'), 403
```

**Testing:**
- Test with the `fairyfloss.css` theme and ensure it adapts gracefully.
- Test logged in vs logged out
- Test from different roles (viewer, editor, admin)

**Security Considerations:**
- ✅ No information leakage (don't reveal why access denied)
- ✅ User-friendly (clear message, easy navigation)
- ✅ Consistent with existing error pages

---

### **1.4.2: API Token Authentication (JWT)**
**Estimated Time:** 3-4 hours
**Complexity:** High
**Dependencies:** Redis (for blacklist)

#### Why JWT with HTTP-Only Cookies?

**Chosen Approach:**
- JWT for stateless authentication (no DB query per request)
- HTTP-only cookies for storage (XSS protection)
- Redis blacklist for revocation (immediate invalidation)
- Refresh token rotation (theft detection)

**Rejected Alternatives:**
- ❌ localStorage: Vulnerable to XSS
- ❌ Database tokens: Too slow for every request
- ❌ Pure JWT without blacklist: Cannot revoke

#### Architecture

```
┌─────────────┐
│   Client    │
│  (Browser)  │
└──────┬──────┘
       │
       │ POST /api/auth/login
       ▼
┌─────────────────────┐
│   Flask App         │
│  - Validate creds   │
│  - Issue JWT tokens │
│  - Set HTTP cookies │
└──────┬──────────────┘
       │
       │ Cookies: access_token, refresh_token
       ▼
┌─────────────┐
│   Client    │ Subsequent requests include cookies
└──────┬──────┘
       │
       │ GET /api/data (cookies auto-sent)
       ▼
┌─────────────────────┐
│   Flask App         │
│  - Verify JWT       │
│  - Check blacklist  │◄───┐
│  - Process request  │    │
└─────────────────────┘    │
                           │
                    ┌──────┴──────┐
                    │    Redis    │
                    │  (Blacklist)│
                    └─────────────┘
```

#### Note on Future SQLAlchemy Migration
The database queries in this plan are written to align with the project's current raw `sqlite3` pattern. This is intentional. By concentrating all database interaction logic within `service` modules (like `user_service`), we create a clean data access layer. When the time comes to migrate to an ORM like SQLAlchemy, the refactoring effort will be isolated to these service modules, preventing a complex, application-wide search for queries.

#### Implementation Steps

**A. Install Dependencies**
```bash
pip install Flask-JWT-Extended==4.6.0 redis==5.0.1
```

**B. Configuration**
```python
# config.py additions
import os
from datetime import timedelta

class Config:
    # JWT Configuration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')  # MUST be different from SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)

    # Cookie Security
    JWT_TOKEN_LOCATION = ['cookies']
    JWT_COOKIE_SECURE = True  # HTTPS only in production
    JWT_COOKIE_HTTPONLY = True  # JavaScript cannot access
    JWT_COOKIE_SAMESITE = 'Strict'  # CSRF protection
    JWT_COOKIE_CSRF_PROTECT = True  # Enable CSRF for cookies
    JWT_SESSION_COOKIE = False  # Persistent

    # Algorithm
    JWT_ALGORITHM = 'HS256'

    # Redis for token blacklist
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
```

**C. Create services/api_auth_service.py**
```python
"""API authentication services using JWT."""

from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token
from flask_jwt_extended import get_jwt, jwt_required, get_jwt_identity
from flask import jsonify
import redis

# Redis client for token blacklist
redis_client = redis.Redis(
    host='localhost',
    port=6379,
    decode_responses=True,
    db=0
)

jwt = JWTManager()

def init_jwt(app):
    """Initialize JWT extension with app"""
    jwt.init_app(app)

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        """Check if token is in blacklist"""
        jti = jwt_payload['jti']
        return redis_client.exists(f'blacklist:{jti}')

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({'error': 'Token has expired'}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({'error': 'Invalid token'}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({'error': 'Authorization required'}), 401

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return jsonify({'error': 'Token has been revoked'}), 401

def add_token_to_blacklist(jti, expires_delta):
    """Add revoked token to blacklist with TTL"""
    redis_client.setex(
        f'blacklist:{jti}',
        time=int(expires_delta.total_seconds()),
        value='revoked'
    )

def revoke_token(jti, reason='logout'):
    """Revoke a token immediately"""
    from datetime import timedelta
    from flask import current_app
    from services.audit_log_service import create_audit_log

    # Add to Redis blacklist
    expires = current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
    add_token_to_blacklist(jti, expires)

    # Log in audit log
    create_audit_log('token_revoked', details={'reason': reason})
```

**D. Create API Auth Blueprint**
```python
# blueprints/api/v1/auth.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from werkzeug.security import check_password_hash
# This assumes a user_service exists for DB operations
from services.user_service import get_user_by_username, get_user_by_id
from services.api_auth_service import add_token_to_blacklist

auth_api_bp = Blueprint('auth_api', __name__)

@auth_api_bp.route('/login', methods=['POST'])
def api_login():
    """API login endpoint - returns JWT tokens"""
    data = request.get_json()

    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Username and password required'}), 400

    # Using service layer for database access
    user = get_user_by_username(data['username'])

    if not user or not check_password_hash(user['password_hash'], data['password']):
        return jsonify({'error': 'Invalid credentials'}), 401

    # Create tokens with user identity
    access_token = create_access_token(
        identity=user['id'],
        additional_claims={'role': user['role'], 'username': user['username']}
    )
    refresh_token = create_refresh_token(identity=user['id'])

    response = jsonify({
        'message': 'Login successful',
        'user': {
            'id': user['id'],
            'username': user['username'],
            'role': user['role']
        }
    })

    # Set tokens as HTTP-only cookies
    from flask_jwt_extended import set_access_cookies, set_refresh_cookies
    set_access_cookies(response, access_token)
    set_refresh_cookies(response, refresh_token)

    return response, 200

@auth_api_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def api_refresh():
    """Refresh access token using refresh token"""
    identity = get_jwt_identity()
    current_token = get_jwt()

    # Blacklist old refresh token (rotation)
    jti = current_token['jti']
    from datetime import timedelta
    add_token_to_blacklist(jti, timedelta(days=7))

    # Create new tokens
    user = get_user_by_id(identity)
    new_access_token = create_access_token(
        identity=user['id'],
        additional_claims={'role': user['role'], 'username': user['username']}
    )
    new_refresh_token = create_refresh_token(identity=user['id'])

    response = jsonify({'message': 'Token refreshed'})

    from flask_jwt_extended import set_access_cookies, set_refresh_cookies
    set_access_cookies(response, new_access_token)
    set_refresh_cookies(response, new_refresh_token)

    return response, 200

@auth_api_bp.route('/logout', methods=['POST'])
@jwt_required()
def api_logout():
    """API logout - revokes token"""
    jti = get_jwt()['jti']
    from datetime import timedelta
    add_token_to_blacklist(jti, timedelta(minutes=15))

    response = jsonify({'message': 'Logout successful'})

    from flask_jwt_extended import unset_jwt_cookies
    unset_jwt_cookies(response)

    return response, 200
```

**E. Example Protected Endpoint**
```python
from flask_jwt_extended import jwt_required, get_jwt

@api_v1_bp.route('/protected-data', methods=['GET'])
@jwt_required()
def get_protected_data():
    """Example protected endpoint"""
    claims = get_jwt()
    user_id = get_jwt_identity()

    # Check role from JWT claims
    if claims.get('role') not in ['admin', 'editor']:
        return jsonify({'error': 'Insufficient permissions'}), 403

    return jsonify({'data': 'secret information'})
```

#### Security Considerations

**Strengths:**
- ✅ XSS-proof (HTTP-only cookies)
- ✅ Immediate revocation (Redis blacklist)
- ✅ Token theft detection (refresh rotation)
- ✅ CSRF protection (SameSite + CSRF tokens)
- ✅ Short-lived access tokens (15 min)

**Potential Weak Points & Mitigations:**

1. **Redis Failure = No Authentication**
   - **Mitigation**: Redis persistence (AOF), fail-closed check
   - **Config**: `appendonly yes` in redis.conf

2. **JWT Secret Compromise**
   - **Mitigation**: Use strong secret (32+ chars), rotate periodically
   - **Config**: Store in environment variable, never commit to repo

3. **Cookie Theft via MITM**
   - **Mitigation**: HTTPS only (`JWT_COOKIE_SECURE=True`)
   - **Config**: Enforce HTTPS in production

4. **Refresh Token Indefinite Validity**
   - **Mitigation**: 7-day expiration, rotation on use
   - **Config**: Already implemented

#### Testing Checklist

- [ ] Login returns tokens in HTTP-only cookies
- [ ] Access token expires after 15 minutes
- [ ] Refresh token works and rotates
- [ ] Logout blacklists token (request fails immediately)
- [ ] Revoked token cannot access protected endpoints
- [ ] CSRF protection works with cookie-based JWT
- [ ] Redis failure behavior (fail-closed vs fail-open decision)

---

### **1.4.3: Rate Limiting**
**Estimated Time:** 2-3 hours
**Complexity:** Medium
**Dependencies:** Redis (same instance as JWT blacklist)

#### Why Flask-Limiter?

**Chosen Approach:**
- Battle-tested library (5+ years, active maintenance)
- Redis backend (shared with JWT blacklist)
- Per-user + per-IP strategies
- Automatic distributed support

**Configuration:**
```python
# config.py additions
RATELIMIT_STORAGE_URI = 'redis://localhost:6379/1'  # Different DB from blacklist
RATELIMIT_SWALLOW_ERRORS = True  # Fail-open: if Redis down, allow requests
RATELIMIT_DEFAULT = "200 per day;50 per hour"
```

#### Implementation

**A. Install Flask-Limiter**
```bash
pip install Flask-Limiter==3.5.0
```

**B. Create services/rate_limit_service.py**
```python
"""Rate limiting configuration and utilities."""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import request
from flask_login import current_user

def get_rate_limit_key():
    """
    Custom key function for rate limiting.

    - Authenticated users: limited per user ID
    - Anonymous users: limited per IP address
    - Fallback to IP if user ID not available
    """
    if current_user.is_authenticated:
        return f"user:{current_user.id}"
    return f"ip:{request.remote_addr}"

def get_role_based_limit():
    """
    Dynamic rate limits based on user role.

    Admins get higher limits than editors, viewers get lower.
    """
    if not current_user.is_authenticated:
        return "10 per minute"

    role_limits = {
        'admin': "1000 per minute",
        'editor': "100 per minute",
        'viewer': "30 per minute"
    }

    return role_limits.get(current_user.role, "30 per minute")

limiter = Limiter(
    key_func=get_rate_limit_key,
    storage_uri=None,  # Set in init_app
    storage_options={"socket_connect_timeout": 30},
    strategy="fixed-window",
    default_limits=["200 per day", "50 per hour"],
    swallow_errors=True  # Fail-open for availability
)

def init_rate_limiter(app):
    """Initialize rate limiter with app"""
    limiter.init_app(app)

    # Custom error handler for rate limit exceeded
    @app.errorhandler(429)
    def ratelimit_handler(e):
        """Handle rate limit exceeded"""
        return jsonify({
            'error': 'Rate limit exceeded',
            'message': str(e.description)
        }), 429
```

**C. Apply Rate Limits**

```python
# Apply to specific routes
from services.rate_limit_service import limiter, get_role_based_limit

# Login endpoint - strict per-IP limit (prevent brute force)
@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute", key_func=lambda: request.remote_addr)
def login():
    pass

# API endpoints - per-user limit
@api_v1_bp.route('/data')
@jwt_required()
@limiter.limit(get_role_based_limit)
def get_data():
    pass

# Public endpoints - generous per-IP limit
@app.route('/api/public/videos')
@limiter.limit("60 per minute")
def public_videos():
    pass

# Admin operations - per-user, high limit
@admin_bp.route('/users')
@login_required
@admin_required
@limiter.limit("500 per hour")
def list_users():
    pass
```

#### Rate Limit Strategy by Endpoint Type

| Endpoint Type | Strategy | Limit | Reason |
|--------------|----------|-------|--------|
| Login/Auth | Per-IP | 5/min | Prevent brute force |
| Public Read API | Per-IP | 60/min | Generous for anonymous |
| Authenticated API | Per-User | 100/hour | Fair per user |
| Admin Operations | Per-User | 500/hour | Higher for admins |
| CRUD Operations | Per-User (role-based) | Varies | Based on role |

#### Security Considerations

**Strengths:**
- ✅ Prevents brute force attacks (login)
- ✅ Prevents API abuse (automated scraping)
- ✅ Fair resource allocation (per-user)
- ✅ Distributed-ready (Redis backend)

**Potential Weak Points & Mitigations:**

1. **Redis Failure = No Rate Limiting**
   - **Mitigation**: `swallow_errors=True` (availability over security)
   - **Monitoring**: Alert on Redis downtime

2. **IP Spoofing (behind proxy)**
   - **Mitigation**: Trust X-Forwarded-For header from known proxies
   - **Config**: Set `RATELIMIT_KEY_PREFIX` with proxy awareness

3. **Single User Hogging Resources**
   - **Mitigation**: Per-user limits + role-based limits
   - **Already Implemented**: Role-based quotas

#### Testing Checklist

- [ ] Login limit (5 attempts, then 429 error)
- [ ] Per-user limits work (separate users don't share)
- [ ] Per-IP limits work for anonymous users
- [ ] Role-based limits (admin gets higher limit)
- [ ] Redis failure doesn't break app (fail-open)
- [ ] Rate limit headers present in response

---

### **1.4.4: Audit Logging**
**Estimated Time:** 3-4 hours
**Complexity:** Medium-High
**Dependencies:** Python `logging` module, Database migration

#### Why Async Audit Logging?

**Performance Impact:**
- Synchronous DB write: +20-50ms per request
- Async queue: <1ms per request
- **Decision**: Use a non-blocking, asynchronous queue for all audit logging.

#### Architecture (Using Python's `logging` module)
This approach uses the robust, built-in Python `logging` framework to achieve non-blocking, asynchronous logging. It is the industry-standard method.

```
┌──────────────┐      ┌────────────────┐      ┌──────────────────┐      ┌──────────────┐
│   Request    ├─────►│ QueueHandler   ├─────►│      Queue       ├─────►│ QueueListener│
│   Handler    │      │(Adds context)  │      │ (In-memory)      │      │ (Background  ├─► To Handler
└──────────────┘      └────────────────┘      └──────────────────┘      │   Thread)    │
                                                                        └──────────────┘
```

#### Implementation

**A. Create Migration: 007_create_audit_log.sql**
```sql
-- Migration 007: Create Audit Log Table
-- Comprehensive audit logging for security and compliance

CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- User context
    user_id INTEGER,
    username TEXT, -- Logged sparingly, prefer user_id

    -- Request context
    ip_address TEXT,
    user_agent TEXT,
    endpoint TEXT,
    method TEXT,

    -- Event details
    event_type TEXT NOT NULL,
    severity TEXT DEFAULT 'INFO',

    -- Resource tracking
    resource_type TEXT,
    resource_id INTEGER,

    -- Additional details (JSON)
    details TEXT,  -- Store as JSON string

    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Indexes for common queries
CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_event ON audit_logs(event_type);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);

-- Composite index for user activity queries
CREATE INDEX idx_audit_user_time ON audit_logs(user_id, timestamp);
```

**B. Create services/audit_log_service.py**
```python
"""
Audit logging service using Python's standard logging module for
non-blocking, asynchronous processing.
"""
import logging
import logging.handlers
import queue
import json
import atexit
from flask import request, has_request_context
from flask_login import current_user

# 1. Create a dedicated logger for audit trails
audit_logger = logging.getLogger('audit')
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False # Prevent duplicate logs in root logger

# 2. Create a queue for log records
log_queue = queue.Queue(-1) # Unbounded queue

# 3. Create a handler that writes to the database
# This custom handler will be used by the listener in the background thread.
class DatabaseHandler(logging.Handler):
    def emit(self, record):
        # Import here to avoid circular dependencies at startup
        from app import get_db_connection

        details = record.details if hasattr(record, 'details') else None

        log_entry = (
            record.created,
            record.user_id if hasattr(record, 'user_id') else None,
            record.username if hasattr(record, 'username') else None,
            record.ip_address if hasattr(record, 'ip_address') else None,
            record.user_agent if hasattr(record, 'user_agent') else None,
            record.endpoint if hasattr(record, 'endpoint') else None,
            record.method if hasattr(record, 'method') else None,
            record.event_type,
            record.levelname,
            record.resource_type if hasattr(record, 'resource_type') else None,
            record.resource_id if hasattr(record, 'resource_id') else None,
            json.dumps(details) if details else None
        )

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO audit_logs
                (timestamp, user_id, username, ip_address, user_agent,
                 endpoint, method, event_type, severity, resource_type,
                 resource_id, details)
                VALUES (datetime(?, 'unixepoch'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', log_entry)
            conn.commit()
            conn.close()
        except Exception as e:
            # Handle database errors (e.g., log to stderr)
            import sys
            print(f"Failed to write audit log to database: {e}", file=sys.stderr)

# 4. Create a listener to process the queue
# The listener runs in a background thread and directs logs to the DatabaseHandler.
db_handler = DatabaseHandler()
queue_listener = logging.handlers.QueueListener(log_queue, db_handler)

# 5. Create a handler for the main thread to put logs ON the queue
queue_handler = logging.handlers.QueueHandler(log_queue)
audit_logger.addHandler(queue_handler)

# 6. Custom filter to add contextual data to log records
class ContextualFilter(logging.Filter):
    def filter(self, record):
        if has_request_context():
            record.ip_address = request.remote_addr
            record.user_agent = request.headers.get('User-Agent', '')[:500]
            record.endpoint = request.endpoint
            record.method = request.method
        if current_user and current_user.is_authenticated:
            record.user_id = current_user.id
            # Sparingly log username, prefer user_id
            record.username = current_user.username
        return True

audit_logger.addFilter(ContextualFilter())

def init_audit_logging(app):
    """Start the audit logging background thread."""
    queue_listener.start()
    # Ensure the listener is stopped cleanly on app shutdown
    atexit.register(queue_listener.stop)

def redact_sensitive_fields(data):
    """Redact sensitive fields from a dictionary."""
    if not isinstance(data, dict):
        return data
    sensitive_keys = ['password', 'password_hash', 'token', 'secret', 'api_key']
    return {k: '[REDACTED]' if k.lower() in sensitive_keys else v for k, v in data.items()}

def create_audit_log(event_type, severity='INFO', resource_type=None, resource_id=None, details=None):
    """
    Creates an audit log entry by sending it to the async logger.

    Args:
        event_type (str): The type of event (e.g., 'login_success').
        severity (str): 'INFO', 'WARNING', 'ERROR', 'CRITICAL'.
        resource_type (str, optional): The type of resource affected.
        resource_id (int, optional): The ID of the resource affected.
        details (dict, optional): Additional details, will be JSON-serialized.
    """
    extra_data = {
        'event_type': event_type,
        'resource_type': resource_type,
        'resource_id': resource_id,
        'details': redact_sensitive_fields(details) if details else None
    }
    
    log_level = getattr(logging, severity.upper(), logging.INFO)
    audit_logger.log(log_level, f"Event: {event_type}", extra=extra_data)

```

**C. Usage Examples**

```python
from services.audit_log_service import create_audit_log

# Login success
@auth_bp.route('/login', methods=['POST'])
def login():
    # ... authentication logic ...
    if user and check_password_hash(user.password_hash, password):
        login_user(user)
        create_audit_log('login_success', severity='INFO')
        return redirect(url_for('index'))
    else:
        create_audit_log(
            'login_failure',
            severity='WARNING',
            details={'username': username} # Username is safe here as it's the subject of the event
        )
        return render_template('login.html', error='Invalid credentials')

# CRUD operation
@crud_bp.route('/person/<int:person_id>', methods=['DELETE'])
@login_required
@editor_required
def delete_person(person_id):
    person = get_person_by_id(db_conn, person_id)

    create_audit_log(
        'data_delete',
        severity='WARNING',
        resource_type='person',
        resource_id=person_id,
        details={'name': person['canonical_name']}
    )

    delete_person_service(db_conn, person_id)
    return jsonify({'message': 'Deleted'})

# Access denied
@admin_bp.route('/users')
@login_required
def admin_users():
    if current_user.role != 'admin':
        create_audit_log(
            'access_denied',
            severity='WARNING',
            details={'denied_endpoint': '/admin/users'}
        )
        abort(403)
    # ... admin logic ...
```

**D. Cleanup & Retention**

```python
# services/audit_log_service.py additions

def cleanup_old_audit_logs(retention_days=90):
    """Delete audit logs older than retention period."""
    from datetime import timedelta, datetime
    from app import get_db_connection

    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM audit_logs WHERE timestamp < datetime(?, 'unixepoch')",
        (cutoff_date.timestamp(),)
    )

    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted_count

# Schedule with Flask-APScheduler (optional)
# Or run as cron job: flask cleanup-audit-logs
```

#### PII Protection

**What we DON'T log:**
- Passwords (plaintext or hashed)
- Full tokens or API keys (use redaction)
- Credit card numbers, SSNs, etc.
- Full email addresses (use `user_id` for correlation)

**What we DO log:**
- **`user_id` (Primary Identifier)**: For correlating actions to a user.
- **`username`**: Logged *only* when it is the subject of an action (e.g., a failed login attempt). Avoid logging it for general activity.
- IP address (for security analysis)
- Event type and severity
- Resource type and ID
- Redacted request details

#### Security Considerations

**Strengths:**
- ✅ Non-blocking and performant (standard async logging)
- ✅ PII-protected (redaction and clear guidelines)
- ✅ Comprehensive events (auth, data, admin)
- ✅ Clean shutdown handling (`atexit`)
- ✅ Retention policy (auto-cleanup)

**Potential Weak Points & Mitigations:**

1. **Queue Memory Usage**
   - **Mitigation**: The queue is unbounded, which prevents blocking but could consume memory if the DB writer falls behind.
   - **Monitoring**: Monitor application memory. For extreme-scale, a bounded queue or external message broker (e.g., RabbitMQ) would be the next step.

2. **PII Leakage in Details**
   - **Mitigation**: Automatic redaction of sensitive fields.
   - **Review**: Regular audit of logged data to ensure redaction is effective.

3. **Log Tampering**
   - **Mitigation**: Strict database permissions (the application user should have INSERT-only rights to the `audit_logs` table).
   - **Future**: Write-once storage, cryptographic signatures.

#### Testing Checklist

- [ ] Logs created for login success/failure
- [ ] Logs created for CRUD operations
- [ ] Logs created for access denied
- [ ] PII redaction works (passwords not logged)
- [ ] Async processing (request completes fast)
- [ ] Cleanup works (old logs deleted)
- [ ] App shutdown processes remaining logs in queue

---

## Redis Setup & Configuration

Both JWT blacklist (1.4.2) and rate limiting (1.4.3) require Redis.

### Installation

```bash
# Ubuntu/Debian
sudo apt-get install redis-server

# macOS
brew install redis

# Start Redis
sudo systemctl start redis  # Linux
brew services start redis   # macOS
```

### Production Configuration

**Enable Persistence (CRITICAL):**

```bash
# /etc/redis/redis.conf

# Append-Only File (AOF) - most durable
appendonly yes
appendfsync everysec  # Sync every second

# RDB snapshots (backup)
save 900 1      # After 900 sec (15 min) if at least 1 key changed
save 300 10     # After 300 sec (5 min) if at least 10 keys changed
save 60 10000   # After 60 sec if at least 10000 keys changed
```

**Why persistence matters:**
- Without it, server restart = all blacklisted tokens become valid
- Without it, rate limits reset on restart

### Redis Security

```bash
# Set password
requirepass your_strong_password_here

# Bind to localhost only (if single server)
bind 127.0.0.1

# Disable dangerous commands
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command CONFIG ""
```

### Database Separation

```
redis://localhost:6379/0  - JWT blacklist
redis://localhost:6379/1  - Rate limiting
```

---

## Environment Variables Required

```bash
# .env (NEVER commit this file)

# Flask
SECRET_KEY=your-flask-secret-key-min-32-chars
FLASK_ENV=production

# JWT
JWT_SECRET_KEY=different-jwt-secret-key-min-32-chars

# Redis
REDIS_URL=redis://localhost:6379

# Database
DATABASE_PATH=/path/to/posa_wiki.db

# Optional
AUDIT_LOG_RETENTION_DAYS=90
```

**Generate strong secrets:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Security Checklist

### Before Going to Production

**Configuration:**
- [ ] `DEBUG = False`
- [ ] `JWT_COOKIE_SECURE = True` (HTTPS)
- [ ] Strong `SECRET_KEY` and `JWT_SECRET_KEY` (32+ chars)
- [ ] Redis password set
- [ ] Redis persistence enabled (AOF)
- [ ] Environment variables not in code

**Testing:**
- [ ] All 403 errors render correctly
- [ ] JWT login/logout/refresh works
- [ ] Token revocation is immediate
- [ ] Rate limiting prevents brute force
- [ ] Audit logs capture all events
- [ ] PII redaction works
- [ ] Redis failure doesn't crash app

**Monitoring:**
- [ ] Redis uptime monitoring
- [ ] Audit log review process
- [ ] Rate limit exceeded alerts
- [ ] Failed login attempt alerts

---

## Implementation Order

1. **1.4.1**: 403 Error Handler (30 min)
2. **Redis Setup** (30 min - if not already installed)
3. **1.4.2**: JWT Authentication (3-4 hours)
4. **1.4.3**: Rate Limiting (2-3 hours)
5. **1.4.4**: Audit Logging (3-4 hours)

**Total Estimated Time: 10-12 hours**

---

## Potential Issues & Solutions

### Issue: "Redis connection failed"
**Solution**: Check Redis is running (`redis-cli ping` should return `PONG`)

### Issue: "JWT token not found"
**Solution**: Check `JWT_COOKIE_HTTPONLY` and ensure cookies are being set/sent

### Issue: "Rate limit not working"
**Solution**: Check Redis persistence, verify limiter is initialized

### Issue: "Audit logs not appearing"
**Solution**: Check audit worker thread is running, verify queue isn't full

---

## Questions for Approval

1. **Rate Limiting**: Agree with fail-open strategy (`swallow_errors=True`)? Or prefer fail-closed?
2. **Audit Retention**: 90 days default OK? Or different period?
3. **JWT Expiration**: 15-minute access token OK? Or prefer longer?
4. **Redis**: Can install locally or prefer Docker container?

---

*Plan created by Claude*
*Ready for review and approval*
