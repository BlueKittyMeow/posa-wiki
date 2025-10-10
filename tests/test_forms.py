"""Unit tests for CRUD forms.

Tests form validation, custom validators, and field requirements.
"""

import pytest
from flask import Flask
from forms.crud_forms import (
    PersonForm, DogForm, VideoForm, TripForm, SeriesForm,
    UserCreateForm, UserEditForm, AliasForm, ValidDuration, ValidYouTubeID
)
from wtforms.validators import ValidationError


@pytest.fixture
def app():
    """Create Flask app for testing forms."""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-secret-key'
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing
    return app


@pytest.fixture
def app_context(app):
    """Create application context for tests."""
    with app.app_context():
        yield app


class MockField:
    """Mock field for testing validators."""
    def __init__(self, data):
        self.data = data


class MockForm:
    """Mock form for testing validators."""
    def __init__(self, **kwargs):
        self._fields = kwargs


def test_person_form_instantiation(app_context):
    """Test that PersonForm can be instantiated."""
    form = PersonForm()
    assert hasattr(form, 'canonical_name')
    assert hasattr(form, 'youtube_handle')
    assert hasattr(form, 'bio')


def test_dog_form_instantiation(app_context):
    """Test that DogForm can be instantiated."""
    form = DogForm()
    assert hasattr(form, 'name')
    assert hasattr(form, 'breed_primary')
    assert hasattr(form, 'birth_date')


def test_video_form_instantiation(app_context):
    """Test that VideoForm can be instantiated."""
    form = VideoForm()
    assert hasattr(form, 'video_id')
    assert hasattr(form, 'title')
    assert hasattr(form, 'duration')
    assert hasattr(form, 'season')


def test_trip_form_instantiation(app_context):
    """Test that TripForm can be instantiated."""
    form = TripForm()
    assert hasattr(form, 'trip_name')
    assert hasattr(form, 'start_date')
    assert hasattr(form, 'end_date')


def test_series_form_instantiation(app_context):
    """Test that SeriesForm can be instantiated."""
    form = SeriesForm()
    assert hasattr(form, 'name')
    assert hasattr(form, 'is_episodic')
    assert hasattr(form, 'series_type')


def test_user_create_form_instantiation(app_context):
    """Test that UserCreateForm can be instantiated."""
    form = UserCreateForm()
    assert hasattr(form, 'username')
    assert hasattr(form, 'email')
    assert hasattr(form, 'password')
    assert hasattr(form, 'role')


def test_user_edit_form_instantiation(app_context):
    """Test that UserEditForm can be instantiated."""
    form = UserEditForm()
    assert hasattr(form, 'username')
    assert hasattr(form, 'email')
    assert hasattr(form, 'new_password')
    assert hasattr(form, 'role')


def test_alias_form_instantiation(app_context):
    """Test that AliasForm can be instantiated."""
    form = AliasForm()
    assert hasattr(form, 'alias')


# ============================================================================
# CUSTOM VALIDATOR TESTS
# ============================================================================

def test_valid_youtube_id_validator_success():
    """Test ValidYouTubeID accepts 11-character IDs."""
    validator = ValidYouTubeID()
    field = MockField('dQw4w9WgXcQ')
    form = MockForm()

    # Should not raise
    validator(form, field)


def test_valid_youtube_id_validator_too_short():
    """Test ValidYouTubeID rejects IDs that are too short."""
    validator = ValidYouTubeID()
    field = MockField('short')
    form = MockForm()

    with pytest.raises(ValidationError) as exc_info:
        validator(form, field)

    assert 'Invalid YouTube video ID' in str(exc_info.value)


def test_valid_youtube_id_validator_too_long():
    """Test ValidYouTubeID rejects IDs that are too long."""
    validator = ValidYouTubeID()
    field = MockField('dQw4w9WgXcQtoolong')
    form = MockForm()

    with pytest.raises(ValidationError) as exc_info:
        validator(form, field)

    assert 'Invalid YouTube video ID' in str(exc_info.value)


def test_valid_duration_validator_hhmmss():
    """Test ValidDuration accepts HH:MM:SS format."""
    validator = ValidDuration()
    field = MockField('01:23:45')
    form = MockForm()

    # Should not raise
    validator(form, field)


def test_valid_duration_validator_mmss():
    """Test ValidDuration accepts MM:SS format."""
    validator = ValidDuration()
    field = MockField('23:45')
    form = MockForm()

    # Should not raise
    validator(form, field)


def test_valid_duration_validator_invalid_format():
    """Test ValidDuration rejects invalid formats."""
    validator = ValidDuration()
    field = MockField('1:2:3:4')
    form = MockForm()

    with pytest.raises(ValidationError) as exc_info:
        validator(form, field)

    assert 'Invalid duration format' in str(exc_info.value)


def test_valid_duration_validator_non_numeric():
    """Test ValidDuration rejects non-numeric values."""
    validator = ValidDuration()
    field = MockField('12:ab:34')
    form = MockForm()

    with pytest.raises(ValidationError) as exc_info:
        validator(form, field)

    assert 'Invalid duration format' in str(exc_info.value)


def test_valid_duration_validator_empty():
    """Test ValidDuration accepts empty/None values (optional)."""
    validator = ValidDuration()
    field = MockField(None)
    form = MockForm()

    # Should not raise
    validator(form, field)


# ============================================================================
# FORM FIELD VALIDATION TESTS
# ============================================================================

def test_person_form_required_fields(app_context):
    """Test that PersonForm enforces required fields."""
    form = PersonForm(data={})

    # Should have canonical_name as required
    assert 'canonical_name' in form.errors or not form.validate()


def test_dog_form_required_fields(app_context):
    """Test that DogForm enforces required fields."""
    form = DogForm(data={})

    # Should have name as required
    assert 'name' in form.errors or not form.validate()


def test_video_form_required_fields(app_context):
    """Test that VideoForm enforces required fields."""
    form = VideoForm(data={})

    # Should have video_id and title as required
    assert not form.validate()


def test_user_create_form_required_fields(app_context):
    """Test that UserCreateForm enforces required fields."""
    form = UserCreateForm(data={})

    # Should have username, email, password, role as required
    assert not form.validate()


def test_alias_form_required_fields(app_context):
    """Test that AliasForm enforces required fields."""
    form = AliasForm(data={})

    # Should have alias as required
    assert not form.validate()
