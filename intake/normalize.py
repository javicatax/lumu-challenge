"""Normalization of a single collector record."""

from datetime import datetime, timezone, timedelta

IDENTITY_FIELDS = ("ts", "collector_id")
ATTRIBUTE_FIELDS = ("client_ip", "query", "verdict")
REQUIRED_FIELDS = IDENTITY_FIELDS + ATTRIBUTE_FIELDS
#REQUIRED_FIELDS = ("ts", "collector_id", "client_ip", "query", "verdict")
MAX_FUTURE_CLOCK_SKEW = timedelta(minutes=5)
MAX_PAST_CLOCK_SKEW = timedelta(hours=24)


def _to_utc(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_epoch(value):
    n = int(value)
    # Figure out whether this is seconds or milliseconds by checking which
    # interpretation gives a sensible year.
    try:
        as_seconds = datetime.fromtimestamp(n, tz=timezone.utc)
        if 1990 < as_seconds.year < 2035:
            return as_seconds
    except (OverflowError, OSError, ValueError):
        pass
    return datetime.fromtimestamp(n / 1000.0, tz=timezone.utc)


def _parse_iso(value):
    text = value.strip().replace(" ", "T")
    if text.endswith("Z"):
        text = text[:-1]
    return _to_utc(datetime.fromisoformat(text))

def parse_timestamp(value):
    """Parse a device timestamp in any of the formats collectors send."""
    if isinstance(value, (int, float)):
        return _parse_epoch(value)
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return _parse_epoch(text)
        return _parse_iso(text)
    raise ValueError("unsupported timestamp type")

# -- Validation fields

def _clean_identity_string(value, field):
    """Identity fields must be non-empty strings.
    """
    if value is None:
        raise ValueError(f"{field} is None")
    if not isinstance(value, str):
        raise TypeError(f"{field} is not a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field} is empty")
    return text


def _clean_attribute_string(value):
    """Attribute fields may be None, but if present must be a non-empty string.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text


# -- Validation clock
def clock_validation(event_time, received_at):
    """Check if clock is valid - suspect or not."""
    clock_suspect = False
    if received_at is not None:
        delta = event_time - received_at
        if delta > MAX_FUTURE_CLOCK_SKEW or delta < -MAX_PAST_CLOCK_SKEW:
            clock_suspect = True
    return clock_suspect



def normalize(raw):
    """Turn one raw collector record into a normalized record.

    Returns None if the record cannot be used.
    """
    # Validate row
    if not isinstance(raw, dict):
        return None, "not_a_dict"

    # Validate identity fields
    for field in IDENTITY_FIELDS:
        if field not in raw:
            return None, f"missing_{field}"

    # Validate collector ID
    try:
        collector_id = _clean_identity_string(raw["collector_id"], "collector_id")
    except (ValueError, TypeError):
        return None, "bad_collector_id"

    # Validate attributes
    client_ip = _clean_attribute_string(raw.get("client_ip"))
    query = _clean_attribute_string(raw.get("query"))
    verdict = _clean_attribute_string(raw.get("verdict"))

    if query is not None:
        query = query.lower()

    # Parse 'received_at' field
    received_at = None
    if "received_at" in raw and raw["received_at"] is not None:
        try:
            received_at = parse_timestamp(raw["received_at"])
        except (ValueError, TypeError, OverflowError, OSError):
            received_at = None

    # Parse 'event_time' field
    try:
        event_time = parse_timestamp(raw["ts"])
    except (ValueError, TypeError, OverflowError, OSError):
        return None, "bad_timestamp"

    # Validate clock
    clock_suspect = clock_validation(event_time, received_at)

    # Build the normalized record
    record = {
        "event_time": event_time.isoformat(),
        "received_at": received_at.isoformat() if received_at else None,
        "collector_id": collector_id,
        "client_ip": client_ip,
        "query": query,
        "verdict": verdict,
        "clock_suspect": clock_suspect,
    }

    return record, None
