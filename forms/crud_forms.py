"""CRUD forms for all entities with validation.

All forms include CSRF protection via Flask-WTF.
Forms are reusable for both CRUD UI and API validation.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, TextAreaField, DateField, IntegerField,
    BooleanField, SelectField, SelectMultipleField, SubmitField
)
from wtforms.validators import (
    DataRequired, Optional, Length, Email, URL,
    ValidationError, NumberRange
)
from datetime import datetime


# ============================================================================
# CUSTOM VALIDATORS
# ============================================================================

class UniqueValue:
    """Validator to check if a value is unique in database.

    Usage:
        field = StringField('Name', validators=[
            UniqueValue(table='people', column='canonical_name', exclude_id=person_id)
        ])
    """
    def __init__(self, table, column, exclude_id=None, message=None):
        self.table = table
        self.column = column
        self.exclude_id = exclude_id
        self.message = message or f'This {column} already exists.'

    def __call__(self, form, field):
        # Import here to avoid circular imports
        from app import get_db_connection

        conn = get_db_connection()
        query = f'SELECT COUNT(*) FROM {self.table} WHERE {self.column} = ? AND deleted_at IS NULL'
        params = [field.data]

        # Exclude current record if editing
        if self.exclude_id:
            id_column = f'{self.table[:-1]}_id' if self.table.endswith('s') else f'{self.table}_id'
            query += f' AND {id_column} != ?'
            params.append(self.exclude_id)

        count = conn.execute(query, params).fetchone()[0]

        if count > 0:
            raise ValidationError(self.message)


class ValidDateRange:
    """Validator to check if end date is after start date."""
    def __init__(self, start_field, message=None):
        self.start_field = start_field
        self.message = message or 'End date must be after start date.'

    def __call__(self, form, field):
        start_date = form._fields.get(self.start_field)
        if start_date and start_date.data and field.data:
            if field.data < start_date.data:
                raise ValidationError(self.message)


class ValidYouTubeID:
    """Validator for YouTube video IDs (11 characters)."""
    def __init__(self, message=None):
        self.message = message or 'Invalid YouTube video ID format (must be 11 characters).'

    def __call__(self, form, field):
        if field.data:
            if len(field.data) != 11:
                raise ValidationError(self.message)


class ValidDuration:
    """Validator for duration format (HH:MM:SS or MM:SS)."""
    def __init__(self, message=None):
        self.message = message or 'Invalid duration format. Use HH:MM:SS or MM:SS.'

    def __call__(self, form, field):
        if field.data:
            parts = field.data.split(':')
            if len(parts) not in [2, 3]:
                raise ValidationError(self.message)
            try:
                for part in parts:
                    int(part)
            except ValueError:
                raise ValidationError(self.message)


# ============================================================================
# PERSON FORMS
# ============================================================================

class PersonForm(FlaskForm):
    """Form for creating/editing people."""

    canonical_name = StringField(
        'Full Name',
        validators=[
            DataRequired(message='Name is required'),
            Length(min=1, max=200, message='Name must be between 1 and 200 characters')
        ],
        render_kw={'placeholder': 'e.g., Matthew Posa'}
    )

    youtube_handle = StringField(
        'YouTube Handle',
        validators=[
            Optional(),
            Length(max=100, message='Handle must be at most 100 characters')
        ],
        render_kw={'placeholder': '@Username'}
    )

    youtube_url = StringField(
        'YouTube URL',
        validators=[
            Optional(),
            URL(message='Must be a valid URL'),
            Length(max=200, message='URL must be at most 200 characters')
        ],
        render_kw={'placeholder': 'https://youtube.com/@username'}
    )

    bio = TextAreaField(
        'Biography',
        validators=[
            Optional(),
            Length(max=5000, message='Bio must be at most 5000 characters')
        ],
        render_kw={'rows': 4, 'placeholder': 'Brief biography...'}
    )

    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=5000)],
        render_kw={'rows': 3, 'placeholder': 'Internal notes...'}
    )

    submit = SubmitField('Save Person')


# ============================================================================
# DOG FORMS
# ============================================================================

class DogForm(FlaskForm):
    """Form for creating/editing dogs."""

    name = StringField(
        'Name',
        validators=[
            DataRequired(message='Name is required'),
            Length(min=1, max=100, message='Name must be between 1 and 100 characters')
        ],
        render_kw={'placeholder': 'e.g., Monty'}
    )

    birth_date = DateField(
        'Birth Date',
        validators=[Optional()],
        format='%Y-%m-%d'
    )

    breed_primary = StringField(
        'Primary Breed',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': 'e.g., Rough Collie'}
    )

    breed_secondary = StringField(
        'Secondary Breed',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': 'For mixed breeds'}
    )

    breed_detail = StringField(
        'Breed Detail',
        validators=[Optional(), Length(max=200)],
        render_kw={'placeholder': 'Additional breed information'}
    )

    breed_source = StringField(
        'Breed Source',
        validators=[Optional(), Length(max=50)],
        render_kw={'placeholder': 'e.g., AKC, UKC, mixed'}
    )

    color = StringField(
        'Color',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': 'e.g., Sable, Tricolor'}
    )

    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=5000)],
        render_kw={'rows': 4, 'placeholder': 'Description...'}
    )

    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=5000)],
        render_kw={'rows': 3, 'placeholder': 'Internal notes...'}
    )

    submit = SubmitField('Save Dog')


# ============================================================================
# VIDEO FORMS
# ============================================================================

class VideoForm(FlaskForm):
    """Form for creating/editing videos (simplified)."""

    video_id = StringField(
        'YouTube Video ID',
        validators=[
            DataRequired(message='Video ID is required'),
            ValidYouTubeID()
        ],
        render_kw={'placeholder': '11-character YouTube ID', 'maxlength': 11}
    )

    title = StringField(
        'Title',
        validators=[
            DataRequired(message='Title is required'),
            Length(min=1, max=500, message='Title must be between 1 and 500 characters')
        ],
        render_kw={'placeholder': 'Video title'}
    )

    upload_date = DateField(
        'Upload Date',
        validators=[Optional()],
        format='%Y-%m-%d'
    )

    duration = StringField(
        'Duration',
        validators=[Optional(), ValidDuration()],
        render_kw={'placeholder': 'HH:MM:SS or MM:SS'}
    )

    view_count = IntegerField(
        'View Count',
        validators=[Optional(), NumberRange(min=0, message='View count must be positive')],
        default=0
    )

    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=10000)],
        render_kw={'rows': 6, 'placeholder': 'Video description...'}
    )

    thumbnail_url = StringField(
        'Thumbnail URL',
        validators=[Optional(), URL(), Length(max=500)],
        render_kw={'placeholder': 'https://...'}
    )

    thumbnail_file = FileField(
        'Upload Thumbnail',
        validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Images only!')]
    )

    number_of_nights = IntegerField(
        'Number of Nights',
        validators=[Optional(), NumberRange(min=0, max=365)],
        render_kw={'placeholder': '0'}
    )

    season = SelectField(
        'Season',
        choices=[
            ('', '-- Select Season --'),
            ('spring', 'Spring'),
            ('summer', 'Summer'),
            ('fall', 'Fall'),
            ('winter', 'Winter')
        ],
        validators=[Optional()]
    )

    weather_conditions = StringField(
        'Weather Conditions',
        validators=[Optional(), Length(max=200)],
        render_kw={'placeholder': 'e.g., Sunny, Rainy, Snowy'}
    )

    series_notes = TextAreaField(
        'Series Notes',
        validators=[Optional(), Length(max=5000)],
        render_kw={'rows': 3, 'placeholder': 'Notes about series/episodes...'}
    )

    submit = SubmitField('Save Video')


# ============================================================================
# TRIP FORMS
# ============================================================================

class TripForm(FlaskForm):
    """Form for creating/editing trips."""

    trip_name = StringField(
        'Trip Name',
        validators=[
            DataRequired(message='Trip name is required'),
            Length(min=1, max=200, message='Trip name must be between 1 and 200 characters')
        ],
        render_kw={'placeholder': 'e.g., Boundary Waters 2023'}
    )

    start_date = DateField(
        'Start Date',
        validators=[Optional()],
        format='%Y-%m-%d'
    )

    end_date = DateField(
        'End Date',
        validators=[Optional(), ValidDateRange('start_date')],
        format='%Y-%m-%d'
    )

    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=5000)],
        render_kw={'rows': 4, 'placeholder': 'Trip description...'}
    )

    location_primary = SelectField(
        'Primary Location',
        coerce=int,
        validators=[Optional()],
        choices=[]  # Will be populated dynamically from locations table
    )

    submit = SubmitField('Save Trip')


# ============================================================================
# SERIES FORMS
# ============================================================================

class SeriesForm(FlaskForm):
    """Form for creating/editing series."""

    name = StringField(
        'Series Name',
        validators=[
            DataRequired(message='Series name is required'),
            Length(min=1, max=200, message='Series name must be between 1 and 200 characters')
        ],
        render_kw={'placeholder': 'e.g., Canoe Camping'}
    )

    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=5000)],
        render_kw={'rows': 4, 'placeholder': 'Series description...'}
    )

    is_episodic = BooleanField(
        'Is Episodic?',
        default=False,
        description='Check if this is an episodic series with numbered episodes'
    )

    series_type = SelectField(
        'Series Type',
        choices=[
            ('', '-- Select Type --'),
            ('activity', 'Activity (e.g., Canoe Camping, Winter Camping)'),
            ('location', 'Location (e.g., Boundary Waters, Isle Royale)'),
            ('content', 'Content (e.g., Community Content, Special Series)'),
            ('special', 'Special Occasion (e.g., Birthdays, Holidays)')
        ],
        validators=[Optional()]
    )

    submit = SubmitField('Save Series')


# ============================================================================
# USER MANAGEMENT FORMS (Admin Panel)
# ============================================================================

class UserCreateForm(FlaskForm):
    """Form for creating new users (admin panel)."""

    username = StringField(
        'Username',
        validators=[
            DataRequired(message='Username is required'),
            Length(min=3, max=50, message='Username must be between 3 and 50 characters')
        ],
        render_kw={'placeholder': 'username'}
    )

    email = StringField(
        'Email',
        validators=[
            DataRequired(message='Email is required'),
            Email(message='Invalid email address'),
            Length(max=100)
        ],
        render_kw={'placeholder': 'user@example.com'}
    )

    password = StringField(
        'Password',
        validators=[
            DataRequired(message='Password is required'),
            Length(min=8, message='Password must be at least 8 characters')
        ],
        render_kw={'placeholder': 'Minimum 8 characters'}
    )

    role = SelectField(
        'Role',
        choices=[
            ('viewer', 'Viewer (Read-only)'),
            ('editor', 'Editor (Can create/edit content)'),
            ('admin', 'Admin (Full access)')
        ],
        validators=[DataRequired()],
        default='viewer'
    )

    submit = SubmitField('Create User')


class UserEditForm(FlaskForm):
    """Form for editing existing users (admin panel)."""

    username = StringField(
        'Username',
        validators=[
            DataRequired(message='Username is required'),
            Length(min=3, max=50)
        ],
        render_kw={'placeholder': 'username'}
    )

    email = StringField(
        'Email',
        validators=[
            DataRequired(message='Email is required'),
            Email(message='Invalid email address'),
            Length(max=100)
        ],
        render_kw={'placeholder': 'user@example.com'}
    )

    role = SelectField(
        'Role',
        choices=[
            ('viewer', 'Viewer (Read-only)'),
            ('editor', 'Editor (Can create/edit content)'),
            ('admin', 'Admin (Full access)')
        ],
        validators=[DataRequired()],
    )

    # Optional password change
    new_password = StringField(
        'New Password',
        validators=[
            Optional(),
            Length(min=8, message='Password must be at least 8 characters')
        ],
        render_kw={'placeholder': 'Leave blank to keep current password'}
    )

    submit = SubmitField('Update User')


# ============================================================================
# RELATIONSHIP FORMS (Many-to-Many)
# ============================================================================

class VideoRelationshipForm(FlaskForm):
    """Form for managing video relationships (people, dogs, locations, series)."""

    people = SelectMultipleField(
        'People in Video',
        coerce=int,
        validators=[Optional()],
        choices=[],  # Populated dynamically
        render_kw={'size': 10}
    )

    dogs = SelectMultipleField(
        'Dogs in Video',
        coerce=int,
        validators=[Optional()],
        choices=[],  # Populated dynamically
        render_kw={'size': 10}
    )

    locations = SelectMultipleField(
        'Locations',
        coerce=int,
        validators=[Optional()],
        choices=[],  # Populated dynamically
        render_kw={'size': 10}
    )

    series = SelectMultipleField(
        'Series',
        coerce=int,
        validators=[Optional()],
        choices=[],  # Populated dynamically
        render_kw={'size': 10}
    )

    submit = SubmitField('Update Relationships')


# ============================================================================
# ALIAS MANAGEMENT FORM
# ============================================================================

class AliasForm(FlaskForm):
    """Simple form for adding/editing aliases."""

    alias = StringField(
        'Alias',
        validators=[
            DataRequired(message='Alias is required'),
            Length(min=1, max=100, message='Alias must be between 1 and 100 characters')
        ],
        render_kw={'placeholder': 'e.g., "Captain Teeny Trout"'}
    )

    submit = SubmitField('Add Alias')
