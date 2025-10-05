"""User model for authentication with Flask-Login integration"""
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
from datetime import datetime


class User(UserMixin):
    """User model compatible with Flask-Login

    Attributes:
        user_id: Unique identifier (primary key)
        username: Login username
        email: User email
        password_hash: Hashed password
        role: Access level (admin, editor, viewer)
        created_at: Account creation timestamp
        last_login: Last login timestamp
    """

    def __init__(self, user_id, username, email, password_hash, role='viewer',
                 created_at=None, last_login=None):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.role = role
        self.created_at = created_at
        self.last_login = last_login

    def get_id(self):
        """Return user ID for Flask-Login"""
        return str(self.user_id)

    def check_password(self, password):
        """Verify password against stored hash"""
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        """Check if user has admin role"""
        return self.role == 'admin'

    def is_editor(self):
        """Check if user has editor or admin role"""
        return self.role in ('admin', 'editor')

    def update_last_login(self, db_conn):
        """Update last login timestamp"""
        now = datetime.utcnow().isoformat()
        db_conn.execute(
            'UPDATE users SET last_login = ? WHERE user_id = ?',
            (now, self.user_id)
        )
        db_conn.commit()
        self.last_login = now

    @staticmethod
    def get_by_id(user_id, db_conn):
        """Load user by ID (for Flask-Login user_loader)"""
        cursor = db_conn.execute(
            'SELECT * FROM users WHERE user_id = ?',
            (user_id,)
        )
        row = cursor.fetchone()

        if row:
            return User(
                user_id=row['user_id'],
                username=row['username'],
                email=row['email'],
                password_hash=row['password_hash'],
                role=row['role'],
                created_at=row['created_at'],
                last_login=row['last_login']
            )
        return None

    @staticmethod
    def get_by_username(username, db_conn):
        """Load user by username (for login)"""
        cursor = db_conn.execute(
            'SELECT * FROM users WHERE username = ?',
            (username,)
        )
        row = cursor.fetchone()

        if row:
            return User(
                user_id=row['user_id'],
                username=row['username'],
                email=row['email'],
                password_hash=row['password_hash'],
                role=row['role'],
                created_at=row['created_at'],
                last_login=row['last_login']
            )
        return None

    @staticmethod
    def create(username, email, password, role='viewer', db_conn=None):
        """Create a new user with hashed password"""
        password_hash = generate_password_hash(password)

        cursor = db_conn.execute(
            '''INSERT INTO users (username, email, password_hash, role)
               VALUES (?, ?, ?, ?)''',
            (username, email, password_hash, role)
        )
        db_conn.commit()

        return User.get_by_id(cursor.lastrowid, db_conn)

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'
