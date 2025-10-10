"""
API v1 Authentication Endpoints

Provides JWT token management for API authentication:
- POST /api/v1/auth/login - Issue access and refresh tokens
- POST /api/v1/auth/refresh - Refresh access token using refresh token
- DELETE /api/v1/auth/logout - Revoke current tokens
- GET /api/v1/auth/me - Get current authenticated user info
"""

from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies
)
from werkzeug.security import check_password_hash
import sqlite3

from models.user import User
from services.auth_service import revoke_token, log_token_event

# URL prefix is relative to parent blueprint (api_v1_bp with /api/v1)
auth_api_bp = Blueprint('auth_api', __name__, url_prefix='/auth')


def get_db_connection():
    """Get database connection"""
    db_path = current_app.config['DATABASE_PATH']
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@auth_api_bp.route('/login', methods=['POST'])
def api_login():
    """
    Issue JWT tokens for API authentication.

    Request JSON:
        {
            "username": "admin",
            "password": "secret"
        }

    Response JSON:
        {
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "user": {
                "user_id": 1,
                "username": "admin",
                "email": "admin@example.com",
                "role": "admin"
            }
        }

    The tokens are also set as HTTP-only cookies for web clients.
    """
    data = request.get_json()

    if not data or not data.get('username') or not data.get('password'):
        return jsonify({
            'error': 'missing_credentials',
            'message': 'Username and password required'
        }), 400

    username = data['username']
    password = data['password']

    # Authenticate user
    conn = get_db_connection()
    try:
        user = User.get_by_username(username, conn)

        if not user or not check_password_hash(user.password_hash, password):
            log_token_event('login_failed', 0, username=username)
            return jsonify({
                'error': 'invalid_credentials',
                'message': 'Invalid username or password'
            }), 401

        # Check if user is active
        if not user.is_active:
            log_token_event('login_failed_inactive', user.user_id, username=username)
            return jsonify({
                'error': 'account_inactive',
                'message': 'Account is inactive'
            }), 403

        # Create JWT tokens
        access_token = create_access_token(identity=user.user_id)
        refresh_token = create_refresh_token(identity=user.user_id)

        # Log successful login
        log_token_event('token_issued', user.user_id, username=username)

        # Prepare response
        response = jsonify({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': {
                'user_id': user.user_id,
                'username': user.username,
                'email': user.email,
                'role': user.role
            }
        })

        # Set cookies for web clients
        set_access_cookies(response, access_token)
        set_refresh_cookies(response, refresh_token)

        return response, 200

    finally:
        conn.close()


@auth_api_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def api_refresh():
    """
    Refresh access token using refresh token.

    Requires valid refresh token in Authorization header or cookies.

    Response JSON:
        {
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
        }
    """
    user_id = get_jwt_identity()
    jwt_data = get_jwt()

    # Create new access token
    access_token = create_access_token(identity=user_id)

    # Log token refresh
    log_token_event('token_refreshed', user_id, token_jti=jwt_data.get('jti'))

    response = jsonify({
        'access_token': access_token
    })

    # Set cookie for web clients
    set_access_cookies(response, access_token)

    return response, 200


@auth_api_bp.route('/logout', methods=['DELETE'])
@jwt_required(verify_type=False)  # Accept both access and refresh tokens
def api_logout():
    """
    Logout by revoking the current token.

    Requires valid JWT token in Authorization header or cookies.
    The token is added to the blacklist to prevent reuse.

    Response JSON:
        {
            "message": "Successfully logged out"
        }
    """
    user_id = get_jwt_identity()
    jwt_data = get_jwt()
    jti = jwt_data.get('jti')
    token_type = jwt_data.get('type', 'access')

    # Revoke the token
    if jti:
        revoke_token(jti, token_type)
        log_token_event('token_revoked', user_id, token_jti=jti, token_type=token_type)

    response = jsonify({
        'message': 'Successfully logged out'
    })

    # Clear cookies
    unset_jwt_cookies(response)

    return response, 200


@auth_api_bp.route('/me', methods=['GET'])
@jwt_required()
def api_get_current_user():
    """
    Get current authenticated user information.

    Requires valid JWT access token.

    Response JSON:
        {
            "user": {
                "user_id": 1,
                "username": "admin",
                "email": "admin@example.com",
                "role": "admin",
                "is_active": true
            }
        }
    """
    user_id = get_jwt_identity()
    conn = get_db_connection()

    try:
        user = User.get_by_id(user_id, conn)

        if not user:
            return jsonify({
                'error': 'user_not_found',
                'message': 'User no longer exists'
            }), 404

        return jsonify({
            'user': {
                'user_id': user.user_id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'is_active': user.is_active
            }
        }), 200

    finally:
        conn.close()
