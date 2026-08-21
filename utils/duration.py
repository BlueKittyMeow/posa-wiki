"""Duration parsing/formatting helpers.

The ``videos.duration`` column stores a pre-formatted human string produced by
the importers -- ``'0:21'`` (M:SS), ``'9:31'`` (MM:SS) or ``'10:00:36'``
(H:MM:SS).  Older rows and raw YouTube API payloads may still carry ISO 8601
durations (``'PT1H2M3S'``), so the parser accepts those too.

``videos.duration_seconds`` (migration 008) holds the parsed integer so that
``ORDER BY`` is numeric instead of lexicographic.
"""

import re

__all__ = ['parse_duration_to_seconds', 'format_seconds']

_ISO_RE = re.compile(
    r'^P(?:(?P<days>\d+)D)?'
    r'(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$',
    re.IGNORECASE,
)


def parse_duration_to_seconds(value):
    """Parse a duration into whole seconds, or return ``None`` if unparseable.

    Accepts:
      * ``int``/``float`` (already seconds)
      * clock strings ``'S'``, ``'M:SS'``, ``'H:MM:SS'`` (any field width)
      * ISO 8601 durations such as ``'PT1H2M3S'``
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value >= 0 else None

    text = str(value).strip()
    if not text:
        return None

    # ISO 8601 remnants (PT#H#M#S)
    if text[0] in 'Pp':
        match = _ISO_RE.match(text)
        if not match:
            return None
        parts = match.groupdict()
        if not any(parts.values()):
            return None
        return int(
            int(parts['days'] or 0) * 86400
            + int(parts['hours'] or 0) * 3600
            + int(parts['minutes'] or 0) * 60
            + float(parts['seconds'] or 0)
        )

    # Clock form: [[H:]M:]S
    segments = text.split(':')
    if len(segments) > 3:
        return None

    total = 0
    for segment in segments:
        segment = segment.strip()
        if not segment.isdigit():
            return None
        total = total * 60 + int(segment)
    return total


def format_seconds(seconds):
    """Render whole seconds as ``H:MM:SS`` or ``M:SS``."""
    if seconds is None:
        return None
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return None
    if total < 0:
        return None

    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
