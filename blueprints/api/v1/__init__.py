"""API v1 blueprint - RESTful endpoints for all entities.

This module provides versioned API endpoints for:
- Videos (GET, POST, PUT, DELETE)
- People (GET, POST, PUT, DELETE)
- Dogs (GET, POST, PUT, DELETE)
- Trips/Series (GET, POST, PUT, DELETE)
- Search (GET)
- Authentication tokens (POST)

All endpoints return JSON and follow REST conventions.
Mutations (POST, PUT, DELETE) require token authentication.
To be implemented in Phase 2B Step 4.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user

api_v1_bp = Blueprint('api_v1', __name__, url_prefix='/api/v1')


# Example endpoint structure (to be implemented in Step 4):
# @api_v1_bp.route('/videos', methods=['GET'])
# def get_videos():
#     """List all videos with pagination"""
#     pass
#
# @api_v1_bp.route('/videos/<video_id>', methods=['GET'])
# def get_video(video_id):
#     """Get a single video by ID"""
#     pass


@api_v1_bp.route('/health', methods=['GET'])
def health_check():
    """API health check endpoint"""
    return jsonify({
        'status': 'ok',
        'version': 'v1',
        'authenticated': current_user.is_authenticated
    }), 200
