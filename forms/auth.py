"""Authentication-related WTForms."""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired


class LoginForm(FlaskForm):
    """Login form with CSRF protection."""

    username = StringField('Username', validators=[DataRequired(message='Username is required.')])
    password = PasswordField('Password', validators=[DataRequired(message='Password is required.')])
    remember_me = BooleanField('Remember me')
    submit = SubmitField('Login')
