# Phase 2B Bugs and Issues

This document outlines the bugs and issues encountered during the development of Phase 2B.

## Persistent CSRF Error on API Endpoints

**Status:** Unresolved
**Severity:** Critical

### Description

All API endpoints under `/api/v1/` are unexpectedly protected by CSRF, resulting in a "400 Bad Request: The CSRF token is missing" error. This prevents any interaction with the API, including the authentication endpoints, which are intended to be exempt from CSRF and protected by JWT and rate limiting.

### Steps to Reproduce

1.  Start the Flask application.
2.  Make a POST request to any API endpoint that is expected to be exempt from CSRF (e.g., `/api/v1/auth/login`).

    ```bash
    curl -H 'Content-Type: application/json' \
        -X POST http://127.0.0.1:5001/api/v1/auth/login \
        -d '{"username":"admin","password":"wrong"}'
    ```

3.  The request fails with a 400 Bad Request and a CSRF error message.

### Investigation and Attempts to Resolve

The following approaches have been attempted to resolve the issue, without success:

1.  **Exempting the Parent Blueprint:** Exempting the `api_v1_bp` blueprint from CSRF protection in `app.py` did not resolve the issue.
2.  **Exempting the Nested Blueprint:** Exempting the `auth_api_bp` blueprint (which is nested inside `api_v1_bp`) from CSRF protection in `app.py` did not resolve the issue.
3.  **Exempting via Function:** Creating a function in the blueprint's `__init__.py` to exempt the nested blueprint and calling it from `app.py` did not resolve the issue.
4.  **Global CSRF Disablement:** Setting `WTF_CSRF_CHECK_DEFAULT = False` in `config.py` to globally disable CSRF protection did not resolve the issue. The error still persists, which is highly unexpected and suggests a more complex issue.
5.  **Rate Limiter Removal:** Temporarily removing the `@limiter.limit` decorator from the `api_login` route did not resolve the issue.

### Current Hypothesis

The cause of the issue is still unknown. The fact that the CSRF error persists even with global CSRF protection disabled suggests that the error may not be coming from `Flask-WTF` as expected, or that there is a configuration issue that is overriding the settings.

## CSRF Configuration and Ramifications

### Current Configuration

The current configuration in `app.py` directly imports the nested `auth_api_bp` blueprint from `blueprints.api.v1.auth` and attempts to exempt it from CSRF protection:

```python
# app.py
from blueprints.api.v1.auth import auth_api_bp
# ...
csrf.exempt(auth_api_bp)
```

This is the most logical configuration, as it directly targets the blueprint that needs to be exempted. However, this configuration is not working as expected.

### Ramifications

The primary ramification of this issue is that the entire API is currently unusable. All API endpoints that require a `POST`, `PUT`, `PATCH`, or `DELETE` request are blocked by the CSRF error. This includes the login endpoint, which is the entry point for all other API functionality.

### Recommended Actions

1.  **Deep Dive into Flask-WTF and Flask-JWT-Extended:** A thorough review of the documentation and source code for both extensions is needed to understand how they interact and why the CSRF exemption is not being applied as expected.
2.  **Alternative CSRF Protection:** If the issue cannot be resolved, we should consider using a different CSRF protection library or implementing CSRF protection manually for the API endpoints.
3.  **Isolate the Issue:** A minimal, reproducible example should be created to isolate the issue from the rest of the application. This will help to determine if the issue is with the application's configuration or with the extensions themselves.

## 403 Error Handler Verification

**Status:** Verified

### Description

The 403 error handler has been verified to be working correctly. When a logged-in user without the required permissions attempts to access a protected route, the application correctly returns a 403 "Access Denied" page. The page is also themed correctly.

### Steps to Verify

1.  Create a user with a non-admin role (e.g., 'viewer').
2.  Log in as the non-admin user.
3.  Attempt to access a route protected by the `@admin_required` decorator.
4.  The application returns a 403 error page.

```