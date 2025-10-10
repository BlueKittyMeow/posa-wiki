"""Unit tests for person_service.

Tests all CRUD operations, soft delete, hard delete, restore, and error handling.
"""

import pytest
import sqlite3
import tempfile
import os
from services import person_service
from services.base_service import NotFoundError, ValidationError, ReferenceError


@pytest.fixture
def db_conn():
    """Create a temporary in-memory database for testing"""
    # Use a temporary file database
    db_fd, db_path = tempfile.mkstemp()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Create schema
    conn.executescript('''
        CREATE TABLE people (
            person_id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT NOT NULL,
            bio TEXT,
            photo_url TEXT,
            photo_local_path TEXT,
            photo_visible BOOLEAN DEFAULT 1,
            aliases TEXT,
            deleted_at TEXT DEFAULT NULL,
            deleted_by INTEGER DEFAULT NULL
        );

        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'viewer'
        );

        CREATE TABLE video_people (
            video_id TEXT NOT NULL,
            person_id INTEGER NOT NULL,
            PRIMARY KEY (video_id, person_id)
        );

        -- Create a test user for deleted_by tracking
        INSERT INTO users (username, email, password_hash, role)
        VALUES ('test_admin', 'admin@test.com', 'hashed', 'admin');
    ''')
    conn.commit()

    yield conn

    # Cleanup
    conn.close()
    os.close(db_fd)
    os.unlink(db_path)


def test_create_person_success(db_conn):
    """Test creating a person successfully"""
    person = person_service.create_person(
        db_conn,
        canonical_name='John Doe',
        bio='Test bio',
        photo_url='http://example.com/photo.jpg'
    )

    assert person['canonical_name'] == 'John Doe'
    assert person['bio'] == 'Test bio'
    assert person['photo_url'] == 'http://example.com/photo.jpg'
    assert person['deleted_at'] is None
    assert 'person_id' in person


def test_create_person_minimal(db_conn):
    """Test creating a person with only required fields"""
    person = person_service.create_person(
        db_conn,
        canonical_name='Jane Smith'
    )

    assert person['canonical_name'] == 'Jane Smith'
    assert person['bio'] is None
    assert person['photo_url'] is None


def test_create_person_duplicate_name(db_conn):
    """Test creating a person with duplicate name fails"""
    person_service.create_person(db_conn, canonical_name='John Doe')

    with pytest.raises(ValidationError) as exc_info:
        person_service.create_person(db_conn, canonical_name='John Doe')

    assert 'already exists' in str(exc_info.value)
    assert exc_info.value.field == 'canonical_name'


def test_create_person_validation_errors(db_conn):
    """Test validation errors when creating person"""
    # Empty name
    with pytest.raises(ValidationError):
        person_service.create_person(db_conn, canonical_name='')

    # Name too long (> 200 chars)
    with pytest.raises(ValidationError):
        person_service.create_person(db_conn, canonical_name='a' * 201)


def test_get_person_by_id_success(db_conn):
    """Test getting a person by ID"""
    created = person_service.create_person(db_conn, canonical_name='Test Person')

    fetched = person_service.get_person_by_id(db_conn, created['person_id'])

    assert fetched['person_id'] == created['person_id']
    assert fetched['canonical_name'] == 'Test Person'


def test_get_person_by_id_not_found(db_conn):
    """Test getting non-existent person raises NotFoundError"""
    with pytest.raises(NotFoundError) as exc_info:
        person_service.get_person_by_id(db_conn, 99999)

    assert exc_info.value.entity_type == 'Person'
    assert exc_info.value.entity_id == 99999


def test_get_all_people(db_conn):
    """Test getting all people"""
    person_service.create_person(db_conn, canonical_name='Person 1')
    person_service.create_person(db_conn, canonical_name='Person 2')
    person_service.create_person(db_conn, canonical_name='Person 3')

    people = person_service.get_all_people(db_conn)

    assert len(people) == 3
    assert all(p['deleted_at'] is None for p in people)


def test_get_all_people_with_pagination(db_conn):
    """Test getting people with pagination"""
    for i in range(5):
        person_service.create_person(db_conn, canonical_name=f'Person {i}')

    people = person_service.get_all_people(db_conn, limit=2, offset=1)

    assert len(people) == 2


def test_update_person_success(db_conn):
    """Test updating a person"""
    person = person_service.create_person(db_conn, canonical_name='Original Name')

    updated = person_service.update_person(
        db_conn,
        person['person_id'],
        canonical_name='Updated Name',
        bio='New bio'
    )

    assert updated['canonical_name'] == 'Updated Name'
    assert updated['bio'] == 'New bio'


def test_update_person_partial(db_conn):
    """Test updating only some fields"""
    person = person_service.create_person(
        db_conn,
        canonical_name='Test Person',
        bio='Original bio'
    )

    updated = person_service.update_person(
        db_conn,
        person['person_id'],
        bio='Updated bio only'
    )

    assert updated['canonical_name'] == 'Test Person'  # Unchanged
    assert updated['bio'] == 'Updated bio only'


def test_update_person_not_found(db_conn):
    """Test updating non-existent person"""
    with pytest.raises(NotFoundError):
        person_service.update_person(db_conn, 99999, canonical_name='Test')


def test_soft_delete_person(db_conn):
    """Test soft deleting a person"""
    person = person_service.create_person(db_conn, canonical_name='To Delete')

    person_service.delete_person(db_conn, person['person_id'], deleted_by_user_id=1)

    # Should not be found in normal queries
    with pytest.raises(NotFoundError):
        person_service.get_person_by_id(db_conn, person['person_id'])

    # Should be found when including deleted
    deleted = person_service.get_person_by_id(db_conn, person['person_id'], include_deleted=True)
    assert deleted['deleted_at'] is not None
    assert deleted['deleted_by'] == 1


def test_restore_person(db_conn):
    """Test restoring a soft-deleted person"""
    person = person_service.create_person(db_conn, canonical_name='To Restore')

    # Soft delete
    person_service.delete_person(db_conn, person['person_id'], deleted_by_user_id=1)

    # Restore
    restored = person_service.restore_person(db_conn, person['person_id'])

    assert restored['deleted_at'] is None
    assert restored['deleted_by'] is None

    # Should be findable again
    found = person_service.get_person_by_id(db_conn, person['person_id'])
    assert found['person_id'] == person['person_id']


def test_restore_non_deleted_person(db_conn):
    """Test restoring a person that is not deleted fails"""
    person = person_service.create_person(db_conn, canonical_name='Not Deleted')

    with pytest.raises(ValidationError) as exc_info:
        person_service.restore_person(db_conn, person['person_id'])

    assert 'not deleted' in str(exc_info.value)


def test_count_person_references(db_conn):
    """Test counting references to a person"""
    person = person_service.create_person(db_conn, canonical_name='Referenced Person')

    # Add some video references
    db_conn.execute(
        'INSERT INTO video_people (video_id, person_id) VALUES (?, ?)',
        ('video1', person['person_id'])
    )
    db_conn.execute(
        'INSERT INTO video_people (video_id, person_id) VALUES (?, ?)',
        ('video2', person['person_id'])
    )
    db_conn.commit()

    refs = person_service.count_person_references(db_conn, person['person_id'])

    assert refs['video_count'] == 2


def test_hard_delete_without_references(db_conn):
    """Test hard deleting a person with no references"""
    person = person_service.create_person(db_conn, canonical_name='To Hard Delete')

    person_service.hard_delete_person(db_conn, person['person_id'], force=True)

    # Should be completely gone
    with pytest.raises(NotFoundError):
        person_service.get_person_by_id(db_conn, person['person_id'], include_deleted=True)


def test_hard_delete_with_references_fails(db_conn):
    """Test hard deleting a person with references fails without force"""
    person = person_service.create_person(db_conn, canonical_name='Referenced Person')

    # Add video reference
    db_conn.execute(
        'INSERT INTO video_people (video_id, person_id) VALUES (?, ?)',
        ('video1', person['person_id'])
    )
    db_conn.commit()

    with pytest.raises(ReferenceError) as exc_info:
        person_service.hard_delete_person(db_conn, person['person_id'], force=False)

    assert exc_info.value.reference_count == 1
    assert exc_info.value.reference_type == 'videos'


def test_hard_delete_with_force_cascades(db_conn):
    """Test hard deleting with force=True cascades to references"""
    person = person_service.create_person(db_conn, canonical_name='Referenced Person')

    # Add video references
    db_conn.execute(
        'INSERT INTO video_people (video_id, person_id) VALUES (?, ?)',
        ('video1', person['person_id'])
    )
    db_conn.execute(
        'INSERT INTO video_people (video_id, person_id) VALUES (?, ?)',
        ('video2', person['person_id'])
    )
    db_conn.commit()

    # Hard delete with force
    person_service.hard_delete_person(db_conn, person['person_id'], force=True)

    # Person should be gone
    with pytest.raises(NotFoundError):
        person_service.get_person_by_id(db_conn, person['person_id'], include_deleted=True)

    # References should be gone
    ref_count = db_conn.execute(
        'SELECT COUNT(*) FROM video_people WHERE person_id = ?',
        (person['person_id'],)
    ).fetchone()[0]
    assert ref_count == 0


def test_get_deleted_people(db_conn):
    """Test getting list of soft-deleted people"""
    # Create and delete some people
    p1 = person_service.create_person(db_conn, canonical_name='Deleted 1')
    p2 = person_service.create_person(db_conn, canonical_name='Deleted 2')
    p3 = person_service.create_person(db_conn, canonical_name='Active')

    person_service.delete_person(db_conn, p1['person_id'], deleted_by_user_id=1)
    person_service.delete_person(db_conn, p2['person_id'], deleted_by_user_id=1)

    deleted = person_service.get_deleted_people(db_conn)

    assert len(deleted) == 2
    assert all(p['deleted_at'] is not None for p in deleted)


def test_get_all_excludes_deleted(db_conn):
    """Test that get_all_people excludes soft-deleted by default"""
    p1 = person_service.create_person(db_conn, canonical_name='Active')
    p2 = person_service.create_person(db_conn, canonical_name='Deleted')

    person_service.delete_person(db_conn, p2['person_id'], deleted_by_user_id=1)

    people = person_service.get_all_people(db_conn, include_deleted=False)

    assert len(people) == 1
    assert people[0]['canonical_name'] == 'Active'


def test_get_all_includes_deleted_when_requested(db_conn):
    """Test that get_all_people can include soft-deleted when requested"""
    p1 = person_service.create_person(db_conn, canonical_name='Active')
    p2 = person_service.create_person(db_conn, canonical_name='Deleted')

    person_service.delete_person(db_conn, p2['person_id'], deleted_by_user_id=1)

    people = person_service.get_all_people(db_conn, include_deleted=True)

    assert len(people) == 2


# ============================================================================
# ALIAS MANAGEMENT TESTS
# ============================================================================

def test_get_aliases_empty(db_conn):
    """Test getting aliases for person with none"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    aliases = person_service.get_aliases(db_conn, person['person_id'])

    assert aliases == []


def test_get_aliases_with_data(db_conn):
    """Test getting aliases for person with existing aliases"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    # Manually insert some aliases
    db_conn.execute(
        'UPDATE people SET aliases = ? WHERE person_id = ?',
        ('["Alias 1", "Alias 2"]', person['person_id'])
    )
    db_conn.commit()

    aliases = person_service.get_aliases(db_conn, person['person_id'])

    assert len(aliases) == 2
    assert 'Alias 1' in aliases
    assert 'Alias 2' in aliases


def test_add_alias_success(db_conn):
    """Test adding a new alias"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    aliases = person_service.add_alias(db_conn, person['person_id'], 'New Alias')

    assert len(aliases) == 1
    assert 'New Alias' in aliases

    # Verify it persisted
    fetched_aliases = person_service.get_aliases(db_conn, person['person_id'])
    assert fetched_aliases == ['New Alias']


def test_add_alias_multiple(db_conn):
    """Test adding multiple aliases"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    person_service.add_alias(db_conn, person['person_id'], 'First Alias')
    aliases = person_service.add_alias(db_conn, person['person_id'], 'Second Alias')

    assert len(aliases) == 2
    assert 'First Alias' in aliases
    assert 'Second Alias' in aliases


def test_add_alias_duplicate_fails(db_conn):
    """Test adding a duplicate alias fails"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    person_service.add_alias(db_conn, person['person_id'], 'Test Alias')

    # Try to add same alias (case-insensitive)
    with pytest.raises(ValidationError) as exc_info:
        person_service.add_alias(db_conn, person['person_id'], 'Test Alias')

    assert 'already exists' in str(exc_info.value)
    assert exc_info.value.field == 'alias'


def test_add_alias_duplicate_case_insensitive(db_conn):
    """Test duplicate checking is case-insensitive"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    person_service.add_alias(db_conn, person['person_id'], 'Test Alias')

    with pytest.raises(ValidationError) as exc_info:
        person_service.add_alias(db_conn, person['person_id'], 'TEST ALIAS')

    assert 'already exists' in str(exc_info.value)


def test_add_alias_empty_fails(db_conn):
    """Test adding empty alias fails"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    with pytest.raises(ValidationError) as exc_info:
        person_service.add_alias(db_conn, person['person_id'], '')

    assert 'cannot be empty' in str(exc_info.value)


def test_add_alias_too_long_fails(db_conn):
    """Test adding alias longer than 100 chars fails"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    with pytest.raises(ValidationError):
        person_service.add_alias(db_conn, person['person_id'], 'a' * 101)


def test_add_alias_person_not_found(db_conn):
    """Test adding alias to non-existent person fails"""
    with pytest.raises(NotFoundError):
        person_service.add_alias(db_conn, 99999, 'Test Alias')


def test_remove_alias_success(db_conn):
    """Test removing an alias"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    person_service.add_alias(db_conn, person['person_id'], 'Alias 1')
    person_service.add_alias(db_conn, person['person_id'], 'Alias 2')

    aliases = person_service.remove_alias(db_conn, person['person_id'], 'Alias 1')

    assert len(aliases) == 1
    assert 'Alias 2' in aliases
    assert 'Alias 1' not in aliases


def test_remove_alias_case_insensitive(db_conn):
    """Test removing alias is case-insensitive"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    person_service.add_alias(db_conn, person['person_id'], 'Test Alias')

    aliases = person_service.remove_alias(db_conn, person['person_id'], 'TEST ALIAS')

    assert len(aliases) == 0


def test_remove_alias_not_found(db_conn):
    """Test removing non-existent alias fails"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    with pytest.raises(ValidationError) as exc_info:
        person_service.remove_alias(db_conn, person['person_id'], 'Nonexistent')

    assert 'not found' in str(exc_info.value)
    assert exc_info.value.field == 'alias'


def test_update_aliases_success(db_conn):
    """Test replacing all aliases"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    # Add some initial aliases
    person_service.add_alias(db_conn, person['person_id'], 'Old 1')
    person_service.add_alias(db_conn, person['person_id'], 'Old 2')

    # Replace with new aliases
    new_aliases = ['New 1', 'New 2', 'New 3']
    updated = person_service.update_aliases(db_conn, person['person_id'], new_aliases)

    assert len(updated) == 3
    assert 'New 1' in updated
    assert 'New 2' in updated
    assert 'New 3' in updated
    assert 'Old 1' not in updated
    assert 'Old 2' not in updated


def test_update_aliases_empty_list(db_conn):
    """Test clearing all aliases"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    person_service.add_alias(db_conn, person['person_id'], 'Alias 1')

    updated = person_service.update_aliases(db_conn, person['person_id'], [])

    assert len(updated) == 0


def test_update_aliases_strips_whitespace(db_conn):
    """Test that update_aliases strips whitespace and skips empty strings"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    aliases = person_service.update_aliases(
        db_conn,
        person['person_id'],
        ['  Alias 1  ', '', '  Alias 2', 'Alias 3  ']
    )

    assert len(aliases) == 3
    assert 'Alias 1' in aliases
    assert 'Alias 2' in aliases
    assert 'Alias 3' in aliases


def test_update_aliases_duplicate_fails(db_conn):
    """Test that update_aliases rejects duplicate aliases"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    with pytest.raises(ValidationError) as exc_info:
        person_service.update_aliases(
            db_conn,
            person['person_id'],
            ['Alias 1', 'Alias 2', 'ALIAS 1']  # Duplicate (case-insensitive)
        )

    assert 'Duplicate' in str(exc_info.value)
    assert exc_info.value.field == 'aliases'


def test_update_aliases_not_a_list_fails(db_conn):
    """Test that update_aliases requires a list"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    with pytest.raises(ValidationError) as exc_info:
        person_service.update_aliases(db_conn, person['person_id'], 'Not a list')

    assert 'must be a list' in str(exc_info.value)


def test_update_aliases_non_string_fails(db_conn):
    """Test that all aliases must be strings"""
    person = person_service.create_person(db_conn, canonical_name='Test Person')

    with pytest.raises(ValidationError) as exc_info:
        person_service.update_aliases(db_conn, person['person_id'], ['Valid', 123, 'Also Valid'])

    assert 'must be a string' in str(exc_info.value)
