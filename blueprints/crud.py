"""CRUD operations blueprint for entity management.

This blueprint will contain server-side forms for:
- People (create, read, update, delete)
- Dogs (create, read, update, delete)
- Videos (create, read, update, delete)
- Trips/Series (create, read, update, delete)

All routes will be protected with @editor_required decorator.
Forms will use Flask-WTF for validation and CSRF protection.
To be implemented in Phase 2B Step 3.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from utils.decorators import editor_required

crud_bp = Blueprint('crud', __name__, url_prefix='/crud')


# Routes will be added in Step 3
# Example structure:
# @crud_bp.route('/person/')
# @editor_required
# def person_list():
#     """List all people with edit links"""
#     pass
#
# @crud_bp.route('/person/new', methods=['GET', 'POST'])
# @editor_required
# def person_create():
#     """Create a new person"""
#     pass
