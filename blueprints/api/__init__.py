"""API package root.

This package contains versioned API blueprints.
All API endpoints are CSRF-exempt but require token authentication.
"""

from flask import Blueprint, jsonify

# Base API blueprint for shared error handlers
api_base_bp = Blueprint('api_base', __name__, url_prefix='/api')


@api_base_bp.errorhandler(404)
def api_not_found(error):
    """JSON 404 response for API endpoints"""
    return jsonify({'error': 'Not found', 'message': str(error)}), 404


@api_base_bp.errorhandler(400)
def api_bad_request(error):
    """JSON 400 response for API endpoints"""
    return jsonify({'error': 'Bad request', 'message': str(error)}), 400


@api_base_bp.errorhandler(500)
def api_server_error(error):
    """JSON 500 response for API endpoints"""
    return jsonify({'error': 'Internal server error', 'message': 'An error occurred'}), 500
