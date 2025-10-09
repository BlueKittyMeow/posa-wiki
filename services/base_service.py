"""Base service with shared utilities and custom exceptions.

All service modules should import from here for consistency.
"""

import sqlite3
from typing import Optional, Dict, Any


# Custom Exceptions
class ServiceError(Exception):
    """Base exception for all service layer errors"""
    pass


class NotFoundError(ServiceError):
    """Raised when a requested entity is not found"""
    def __init__(self, entity_type: str, entity_id: Any):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} with ID {entity_id} not found")


class ValidationError(ServiceError):
    """Raised when validation fails"""
    def __init__(self, message: str, field: Optional[str] = None):
        self.field = field
        super().__init__(message)


class DatabaseError(ServiceError):
    """Raised when a database operation fails"""
    pass


class ReferenceError(ServiceError):
    """Raised when an entity cannot be deleted due to existing references"""
    def __init__(self, entity_type: str, entity_id: Any, reference_count: int, reference_type: str):
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.reference_count = reference_count
        self.reference_type = reference_type
        super().__init__(
            f"Cannot delete {entity_type} {entity_id}: "
            f"{reference_count} {reference_type} still reference it"
        )


# Utility Functions
def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert sqlite3.Row to dict"""
    if row is None:
        return None
    return dict(row)


def rows_to_dicts(rows: list) -> list:
    """Convert list of sqlite3.Row objects to list of dicts"""
    return [dict(row) for row in rows]


def validate_required_fields(data: Dict[str, Any], required_fields: list):
    """Validate that all required fields are present and not empty"""
    for field in required_fields:
        if field not in data or data[field] is None or (isinstance(data[field], str) and not data[field].strip()):
            raise ValidationError(f"Field '{field}' is required", field=field)


def validate_string_length(value: str, field_name: str, max_length: int, min_length: int = 0):
    """Validate string length"""
    if value is None:
        return

    length = len(value)
    if length < min_length:
        raise ValidationError(
            f"{field_name} must be at least {min_length} characters",
            field=field_name
        )
    if length > max_length:
        raise ValidationError(
            f"{field_name} must be at most {max_length} characters",
            field=field_name
        )
