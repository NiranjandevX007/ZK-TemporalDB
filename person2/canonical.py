"""
ZK-TemporalDB — Deterministic JSON Canonicalization

Produces a unique, deterministic string representation of an academic record
so that semantically identical data always yields the same SHA-256 hash.

Canonicalization rules:
    1. UTF-8 encoding throughout.
    2. Keys sorted lexicographically at every nesting level.
    3. No trailing whitespace, no optional spaces.
    4. Dates serialized as ISO-8601 strings: "YYYY-MM-DD".
    5. Decimal values (grades, CGPA, marks) serialized as fixed-point strings
       with explicit precision — NEVER as floating-point. This avoids
       platform-dependent rounding (e.g., 9.50 vs 9.5).
    6. None/NULL values serialized as JSON null.
    7. Lists maintain their original order (position-sensitive).
    8. Minimal JSON: no extra whitespace, no trailing commas.

Usage:
    from person2.canonical import canonicalize, canonical_hash
    canon = canonicalize(record_dict)
    h = canonical_hash(record_dict)
"""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def _normalize_value(value: Any) -> Any:
    """
    Recursively normalize a Python value for deterministic JSON output.

    - Decimal → string with trailing zeros preserved (e.g. "9.50")
    - date/datetime → ISO-8601 string
    - dict → sorted-key dict with normalized values
    - list → list with each element normalized
    - float → DISALLOWED (must use Decimal for academic data)
    - None → None (becomes JSON null)
    - int, str, bool → unchanged
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        # Serialize with explicit precision, preserving trailing zeros.
        # Decimal('9.50') → "9.50", not "9.5"
        return str(value)
    if isinstance(value, float):
        raise TypeError(
            f"Float values are not allowed in canonical records. "
            f"Use Decimal for academic data. Got: {value!r}"
        )
    if isinstance(value, str):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]  # YYYY-MM-DD
    if isinstance(value, dict):
        return {k: _normalize_value(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    # Fallback: convert to string
    return str(value)


def canonicalize(record: dict) -> str:
    """
    Produce the canonical JSON string for an academic record dict.

    The output is deterministic: the same logical record always yields
    the same byte-for-byte string, regardless of original key ordering
    or Python dict insertion order.

    Args:
        record: The academic record as a Python dict.

    Returns:
        A minimal, sorted-keys JSON string in UTF-8.

    Raises:
        TypeError: If the record contains float values (must use Decimal).
    """
    normalized = _normalize_value(record)
    return json.dumps(normalized, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def canonical_hash(record: dict) -> str:
    """
    Compute the SHA-256 hash of the canonical representation.

    Args:
        record: The academic record as a Python dict.

    Returns:
        Lowercase hex SHA-256 digest (64 characters).
    """
    canon_str = canonicalize(record)
    return hashlib.sha256(canon_str.encode('utf-8')).hexdigest()


def verify_hash(record: dict, expected_hash: str) -> bool:
    """
    Recompute the canonical hash and check if it matches the expected hash.

    Args:
        record: The academic record as a Python dict.
        expected_hash: The previously stored SHA-256 hex digest.

    Returns:
        True if the hashes match, False if the record has been modified.
    """
    return canonical_hash(record) == expected_hash
