"""Person service - Business logic for people entity.

Handles CRUD operations, soft/hard delete, and validation for people.
Includes alias management for "also known as" names.
"""

import sqlite3
import json
from typing import Optional, List, Dict, Any
from services.base_service import (
    NotFoundError, ValidationError, DatabaseError, ReferenceError,
    row_to_dict, rows_to_dicts, validate_required_fields, validate_string_length
)


def get_all_people(
    db_conn: sqlite3.Connection,
    include_deleted: bool = False,
    limit: Optional[int] = None,
    offset: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get all people with optional pagination.

    Args:
        db_conn: Database connection
        include_deleted: If True, include soft-deleted people
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        List of people as dicts
    """
    query = 'SELECT * FROM people'

    if not include_deleted:
        query += ' WHERE deleted_at IS NULL'

    query += ' ORDER BY canonical_name ASC'

    if limit is not None:
        query += f' LIMIT {limit}'
        if offset is not None:
            query += f' OFFSET {offset}'

    try:
        rows = db_conn.execute(query).fetchall()
        return rows_to_dicts(rows)
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to fetch people: {e}")


def get_person_by_id(
    db_conn: sqlite3.Connection,
    person_id: int,
    include_deleted: bool = False
) -> Dict[str, Any]:
    """Get a single person by ID.

    Args:
        db_conn: Database connection
        person_id: Person ID
        include_deleted: If True, can return soft-deleted person

    Returns:
        Person dict

    Raises:
        NotFoundError: If person doesn't exist or is deleted (and include_deleted=False)
    """
    query = 'SELECT * FROM people WHERE person_id = ?'

    if not include_deleted:
        query += ' AND deleted_at IS NULL'

    try:
        row = db_conn.execute(query, (person_id,)).fetchone()
        if not row:
            raise NotFoundError('Person', person_id)
        return row_to_dict(row)
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to fetch person: {e}")


def create_person(
    db_conn: sqlite3.Connection,
    canonical_name: str,
    bio: Optional[str] = None,
    photo_url: Optional[str] = None,
    photo_local_path: Optional[str] = None,
    photo_visible: bool = True
) -> Dict[str, Any]:
    """Create a new person.

    Args:
        db_conn: Database connection
        canonical_name: Person's full name
        bio: Optional biography
        photo_url: Optional photo URL
        photo_local_path: Optional local file path for uploaded photo
        photo_visible: Whether photo is visible (privacy control), default True

    Returns:
        Created person dict

    Raises:
        ValidationError: If validation fails
        DatabaseError: If database operation fails
    """
    # Validate required fields
    validate_required_fields({'canonical_name': canonical_name}, ['canonical_name'])

    # Validate field lengths
    validate_string_length(canonical_name, 'canonical_name', 200, 1)
    if bio:
        validate_string_length(bio, 'bio', 5000)
    if photo_url:
        validate_string_length(photo_url, 'photo_url', 500)
    if photo_local_path:
        validate_string_length(photo_local_path, 'photo_local_path', 500)

    # Check for duplicate name
    existing = db_conn.execute(
        'SELECT person_id FROM people WHERE canonical_name = ? AND deleted_at IS NULL',
        (canonical_name,)
    ).fetchone()

    if existing:
        raise ValidationError(
            f"Person with name '{canonical_name}' already exists",
            field='canonical_name'
        )

    try:
        cursor = db_conn.execute(
            'INSERT INTO people (canonical_name, bio, photo_url, photo_local_path, photo_visible) VALUES (?, ?, ?, ?, ?)',
            (canonical_name, bio, photo_url, photo_local_path, photo_visible)
        )
        db_conn.commit()

        # Fetch and return the created person
        person_id = cursor.lastrowid
        return get_person_by_id(db_conn, person_id)

    except sqlite3.Error as e:
        db_conn.rollback()
        raise DatabaseError(f"Failed to create person: {e}")


def update_person(
    db_conn: sqlite3.Connection,
    person_id: int,
    **kwargs
) -> Dict[str, Any]:
    """Update an existing person.

    Args:
        db_conn: Database connection
        person_id: Person ID
        **kwargs: Fields to update (canonical_name, bio, photo_url)

    Returns:
        Updated person dict

    Raises:
        NotFoundError: If person doesn't exist
        ValidationError: If validation fails
        DatabaseError: If database operation fails
    """
    # Check person exists and is not deleted
    person = get_person_by_id(db_conn, person_id, include_deleted=False)

    # Validate allowed fields
    allowed_fields = {'canonical_name', 'bio', 'photo_url', 'photo_local_path', 'photo_visible'}
    update_fields = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not update_fields:
        return person  # Nothing to update

    # Validate field lengths
    if 'canonical_name' in update_fields:
        validate_string_length(update_fields['canonical_name'], 'canonical_name', 200, 1)

        # Check for duplicate name (excluding current person)
        existing = db_conn.execute(
            'SELECT person_id FROM people WHERE canonical_name = ? AND person_id != ? AND deleted_at IS NULL',
            (update_fields['canonical_name'], person_id)
        ).fetchone()

        if existing:
            raise ValidationError(
                f"Person with name '{update_fields['canonical_name']}' already exists",
                field='canonical_name'
            )

    if 'bio' in update_fields and update_fields['bio']:
        validate_string_length(update_fields['bio'], 'bio', 5000)

    if 'photo_url' in update_fields and update_fields['photo_url']:
        validate_string_length(update_fields['photo_url'], 'photo_url', 500)

    if 'photo_local_path' in update_fields and update_fields['photo_local_path']:
        validate_string_length(update_fields['photo_local_path'], 'photo_local_path', 500)

    # Build UPDATE query
    set_clause = ', '.join([f'{field} = ?' for field in update_fields.keys()])
    values = list(update_fields.values()) + [person_id]

    try:
        db_conn.execute(
            f'UPDATE people SET {set_clause} WHERE person_id = ?',
            values
        )
        db_conn.commit()

        # Fetch and return updated person
        return get_person_by_id(db_conn, person_id)

    except sqlite3.Error as e:
        db_conn.rollback()
        raise DatabaseError(f"Failed to update person: {e}")


def delete_person(
    db_conn: sqlite3.Connection,
    person_id: int,
    deleted_by_user_id: Optional[int] = None
) -> None:
    """Soft delete a person (marks as deleted, preserves data).

    Args:
        db_conn: Database connection
        person_id: Person ID
        deleted_by_user_id: ID of user performing the deletion (for audit)

    Raises:
        NotFoundError: If person doesn't exist or is already deleted
        DatabaseError: If database operation fails
    """
    # Check person exists and is not already deleted
    person = get_person_by_id(db_conn, person_id, include_deleted=False)

    try:
        db_conn.execute(
            'UPDATE people SET deleted_at = CURRENT_TIMESTAMP, deleted_by = ? WHERE person_id = ?',
            (deleted_by_user_id, person_id)
        )
        db_conn.commit()

    except sqlite3.Error as e:
        db_conn.rollback()
        raise DatabaseError(f"Failed to delete person: {e}")


def restore_person(
    db_conn: sqlite3.Connection,
    person_id: int
) -> Dict[str, Any]:
    """Restore a soft-deleted person.

    Args:
        db_conn: Database connection
        person_id: Person ID

    Returns:
        Restored person dict

    Raises:
        NotFoundError: If person doesn't exist
        ValidationError: If person is not deleted
        DatabaseError: If database operation fails
    """
    # Get person (include deleted)
    person = get_person_by_id(db_conn, person_id, include_deleted=True)

    if person['deleted_at'] is None:
        raise ValidationError(f"Person {person_id} is not deleted")

    try:
        db_conn.execute(
            'UPDATE people SET deleted_at = NULL, deleted_by = NULL WHERE person_id = ?',
            (person_id,)
        )
        db_conn.commit()

        # Fetch and return restored person
        return get_person_by_id(db_conn, person_id)

    except sqlite3.Error as e:
        db_conn.rollback()
        raise DatabaseError(f"Failed to restore person: {e}")


def count_person_references(
    db_conn: sqlite3.Connection,
    person_id: int
) -> Dict[str, int]:
    """Count how many videos reference this person.

    Args:
        db_conn: Database connection
        person_id: Person ID

    Returns:
        Dict with reference counts: {'video_count': X}
    """
    try:
        video_count = db_conn.execute(
            'SELECT COUNT(*) FROM video_people WHERE person_id = ?',
            (person_id,)
        ).fetchone()[0]

        return {'video_count': video_count}

    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to count person references: {e}")


def hard_delete_person(
    db_conn: sqlite3.Connection,
    person_id: int,
    force: bool = False
) -> None:
    """Permanently delete a person (CANNOT BE UNDONE).

    This will cascade delete all references in video_people table.

    Args:
        db_conn: Database connection
        person_id: Person ID
        force: If True, delete even if references exist

    Raises:
        NotFoundError: If person doesn't exist
        ReferenceError: If references exist and force=False
        DatabaseError: If database operation fails
    """
    # Check person exists (include deleted)
    person = get_person_by_id(db_conn, person_id, include_deleted=True)

    # Count references
    references = count_person_references(db_conn, person_id)
    video_count = references['video_count']

    if video_count > 0 and not force:
        raise ReferenceError('Person', person_id, video_count, 'videos')

    try:
        # Cascade delete references first
        if video_count > 0:
            db_conn.execute(
                'DELETE FROM video_people WHERE person_id = ?',
                (person_id,)
            )

        # Delete the person
        db_conn.execute(
            'DELETE FROM people WHERE person_id = ?',
            (person_id,)
        )

        db_conn.commit()

    except sqlite3.Error as e:
        db_conn.rollback()
        raise DatabaseError(f"Failed to hard delete person: {e}")


def get_deleted_people(
    db_conn: sqlite3.Connection,
    limit: Optional[int] = None,
    offset: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get all soft-deleted people for admin review.

    Args:
        db_conn: Database connection
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        List of deleted people with deletion info
    """
    query = '''
        SELECT p.*, u.username as deleted_by_username
        FROM people p
        LEFT JOIN users u ON p.deleted_by = u.user_id
        WHERE p.deleted_at IS NOT NULL
        ORDER BY p.deleted_at DESC
    '''

    if limit is not None:
        query += f' LIMIT {limit}'
        if offset is not None:
            query += f' OFFSET {offset}'

    try:
        rows = db_conn.execute(query).fetchall()
        return rows_to_dicts(rows)
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to fetch deleted people: {e}")


# ============================================================================
# ALIAS MANAGEMENT (Also Known As)
# ============================================================================

def get_aliases(
    db_conn: sqlite3.Connection,
    person_id: int
) -> List[str]:
    """Get list of aliases for a person.

    Args:
        db_conn: Database connection
        person_id: Person ID

    Returns:
        List of alias strings

    Raises:
        NotFoundError: If person doesn't exist
    """
    person = get_person_by_id(db_conn, person_id, include_deleted=False)

    if not person['aliases']:
        return []

    try:
        aliases = json.loads(person['aliases'])
        return aliases if isinstance(aliases, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def add_alias(
    db_conn: sqlite3.Connection,
    person_id: int,
    alias: str
) -> List[str]:
    """Add a new alias to a person.

    Args:
        db_conn: Database connection
        person_id: Person ID
        alias: Alias to add

    Returns:
        Updated list of aliases

    Raises:
        NotFoundError: If person doesn't exist
        ValidationError: If alias is empty or already exists
    """
    # Validate alias
    if not alias or not alias.strip():
        raise ValidationError("Alias cannot be empty", field='alias')

    alias = alias.strip()
    validate_string_length(alias, 'alias', 100, 1)

    # Get current aliases
    current_aliases = get_aliases(db_conn, person_id)

    # Check for duplicate (case-insensitive)
    if any(a.lower() == alias.lower() for a in current_aliases):
        raise ValidationError(
            f"Alias '{alias}' already exists for this person",
            field='alias'
        )

    # Add new alias
    current_aliases.append(alias)

    # Update in database
    try:
        db_conn.execute(
            'UPDATE people SET aliases = ? WHERE person_id = ?',
            (json.dumps(current_aliases), person_id)
        )
        db_conn.commit()
        return current_aliases
    except sqlite3.Error as e:
        db_conn.rollback()
        raise DatabaseError(f"Failed to add alias: {e}")


def remove_alias(
    db_conn: sqlite3.Connection,
    person_id: int,
    alias: str
) -> List[str]:
    """Remove an alias from a person.

    Args:
        db_conn: Database connection
        person_id: Person ID
        alias: Alias to remove (case-insensitive match)

    Returns:
        Updated list of aliases

    Raises:
        NotFoundError: If person doesn't exist
        ValidationError: If alias doesn't exist
    """
    current_aliases = get_aliases(db_conn, person_id)

    # Find and remove alias (case-insensitive)
    alias_lower = alias.lower()
    found_index = next(
        (i for i, a in enumerate(current_aliases) if a.lower() == alias_lower),
        None
    )

    if found_index is None:
        raise ValidationError(
            f"Alias '{alias}' not found for this person",
            field='alias'
        )

    # Remove the alias
    current_aliases.pop(found_index)

    # Update in database
    try:
        db_conn.execute(
            'UPDATE people SET aliases = ? WHERE person_id = ?',
            (json.dumps(current_aliases), person_id)
        )
        db_conn.commit()
        return current_aliases
    except sqlite3.Error as e:
        db_conn.rollback()
        raise DatabaseError(f"Failed to remove alias: {e}")


def update_aliases(
    db_conn: sqlite3.Connection,
    person_id: int,
    aliases: List[str]
) -> List[str]:
    """Replace all aliases for a person.

    Args:
        db_conn: Database connection
        person_id: Person ID
        aliases: New list of aliases

    Returns:
        Updated list of aliases

    Raises:
        NotFoundError: If person doesn't exist
        ValidationError: If aliases list contains invalid data
    """
    # Check person exists
    get_person_by_id(db_conn, person_id, include_deleted=False)

    # Validate aliases list
    if not isinstance(aliases, list):
        raise ValidationError("Aliases must be a list", field='aliases')

    # Clean and validate each alias
    cleaned_aliases = []
    seen = set()

    for alias in aliases:
        if not isinstance(alias, str):
            raise ValidationError("Each alias must be a string", field='aliases')

        alias = alias.strip()
        if not alias:
            continue  # Skip empty strings

        validate_string_length(alias, 'alias', 100, 1)

        # Check for duplicates (case-insensitive)
        alias_lower = alias.lower()
        if alias_lower in seen:
            raise ValidationError(
                f"Duplicate alias: '{alias}'",
                field='aliases'
            )

        seen.add(alias_lower)
        cleaned_aliases.append(alias)

    # Update in database
    try:
        db_conn.execute(
            'UPDATE people SET aliases = ? WHERE person_id = ?',
            (json.dumps(cleaned_aliases), person_id)
        )
        db_conn.commit()
        return cleaned_aliases
    except sqlite3.Error as e:
        db_conn.rollback()
        raise DatabaseError(f"Failed to update aliases: {e}")
