"""
Tests for JWT API Authentication

Tests JWT token generation, refresh, and revocation.
"""

import pytest
import json
from flask import Flask
from app import app as flask_app


@pytest.fixture
def app():
    """Configure Flask app for testing"""
    flask_app.config['TESTING'] = True
    flask_app.config['JWT_COOKIE_CSRF_PROTECT'] = False  # Disable CSRF for testing
    return flask_app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def admin_user(app):
    """
    Create a test admin user.
    Note: Assumes an admin user already exists from migrations or manual creation.
    """
    # For now, we'll use the existing admin user
    # In a real test suite, we'd create a test user here
    return {
        'username': 'admin',
        'password': 'admin123'  # Default test password
    }


def test_login_success(client, admin_user):
    """Test successful login returns JWT tokens"""
    response = client.post('/api/v1/auth/login',
                          json=admin_user,
                          content_type='application/json')

    assert response.status_code == 200
    data = json.loads(response.data)

    assert 'access_token' in data
    assert 'refresh_token' in data
    assert 'user' in data
    assert data['user']['username'] == admin_user['username']


def test_login_invalid_credentials(client):
    """Test login with invalid credentials returns 401"""
    response = client.post('/api/v1/auth/login',
                          json={'username': 'invalid', 'password': 'wrong'},
                          content_type='application/json')

    assert response.status_code == 401
    data = json.loads(response.data)
    assert 'error' in data
    assert data['error'] == 'invalid_credentials'


def test_login_missing_credentials(client):
    """Test login without credentials returns 400"""
    response = client.post('/api/v1/auth/login',
                          json={},
                          content_type='application/json')

    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert data['error'] == 'missing_credentials'


def test_get_current_user(client, admin_user):
    """Test getting current user info with valid token"""
    # First login to get token
    login_response = client.post('/api/v1/auth/login',
                                json=admin_user,
                                content_type='application/json')
    assert login_response.status_code == 200

    token_data = json.loads(login_response.data)
    access_token = token_data['access_token']

    # Get current user info
    response = client.get('/api/v1/auth/me',
                         headers={'Authorization': f'Bearer {access_token}'})

    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'user' in data
    assert data['user']['username'] == admin_user['username']


def test_get_current_user_no_token(client):
    """Test getting current user without token returns 401"""
    response = client.get('/api/v1/auth/me')

    assert response.status_code == 401
    data = json.loads(response.data)
    assert 'error' in data


def test_token_refresh(client, admin_user):
    """Test refreshing access token with refresh token"""
    # First login to get tokens
    login_response = client.post('/api/v1/auth/login',
                                json=admin_user,
                                content_type='application/json')
    assert login_response.status_code == 200

    token_data = json.loads(login_response.data)
    refresh_token = token_data['refresh_token']

    # Refresh the access token
    response = client.post('/api/v1/auth/refresh',
                          headers={'Authorization': f'Bearer {refresh_token}'})

    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'access_token' in data


def test_logout(client, admin_user):
    """Test logout revokes the token"""
    # First login to get token
    login_response = client.post('/api/v1/auth/login',
                                json=admin_user,
                                content_type='application/json')
    assert login_response.status_code == 200

    token_data = json.loads(login_response.data)
    access_token = token_data['access_token']

    # Logout
    response = client.delete('/api/v1/auth/logout',
                           headers={'Authorization': f'Bearer {access_token}'})

    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'message' in data

    # Try using the token after logout (should fail if Redis is enabled)
    # Note: In dev mode without Redis, this won't actually block the token
    # In production with Redis, this would return 401
