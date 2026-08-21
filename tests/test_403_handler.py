
import pytest
import sqlite3
import tempfile
import os
from flask import Blueprint, Flask, render_template
from models.user import User
from utils.decorators import admin_required
from flask_login import login_required, LoginManager

# Create a temporary blueprint for the test
test_bp = Blueprint('test_bp_403', __name__)

@test_bp.route('/admin-test-route')
@login_required
@admin_required
def admin_test_route():
    """An admin-only route for testing the 403 handler."""
    return "You should not see this.", 200

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    db_fd, db_path = tempfile.mkstemp()

    app = Flask(__name__, template_folder='../templates')
    app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
        "DATABASE_PATH": db_path,
    })

    # Add a dummy index route to satisfy the login redirect
    @app.route('/')
    def index():
        return "Test Index Page"

    # Add the custom 403 error handler to the test app
    @app.errorhandler(403)
    def handle_forbidden(error):
        return render_template('errors/403.html'), 403

    # Register the auth blueprint needed for login
    from blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)

    # Register the temporary blueprint for this test
    app.register_blueprint(test_bp)

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        with sqlite3.connect(app.config['DATABASE_PATH']) as conn:
            conn.row_factory = sqlite3.Row
            return User.get_by_id(user_id, conn)

    # Create database schema and test user
    with app.app_context():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        with open('migrations/003_create_users_table.sql') as f:
            conn.executescript(f.read())
        
        User.create('testviewer', 'viewer@test.com', 'password', role='viewer', db_conn=conn)
        conn.close()

    yield app

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

def test_403_handler_for_non_admin(client):
    """
    GIVEN a logged-in non-admin user
    WHEN they attempt to access an admin-only route
    THEN they should receive a 403 Forbidden error page
    """
    # 1. Log in as the non-admin 'testviewer' user
    login_res = client.post('/auth/login', data={
        'username': 'testviewer',
        'password': 'password'
    }, follow_redirects=True)
    
    assert login_res.status_code == 200
    assert b'Invalid username or password' not in login_res.data
    
    # 2. Attempt to access the admin-only test route
    response = client.get('/admin-test-route')

    # 3. Assert that the 403 error page is returned
    assert response.status_code == 403
    assert b"Access Denied" in response.data
    assert b"You don't have permission to access this resource." in response.data
