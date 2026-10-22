"""
ZK-TemporalDB — Unit Tests: Canonicalization and Hashing

These tests run WITHOUT any database connection.
They verify the deterministic canonicalization and SHA-256 hashing logic.

Test IDs:
    T1: Same data → same hash (determinism)
    T2: Changed mark → different hash (sensitivity)
    T3: Key ordering doesn't matter
    T4: Decimal precision preserved (9.50 ≠ 9.5 in string, but same Decimal)
    T5: Date serialization
    T6: None/NULL handling
    T7: Float rejection
    T8: Nested structures
"""

import pytest
from datetime import date
from decimal import Decimal

from person2.canonical import canonicalize, canonical_hash, verify_hash


# ── Test Data ─────────────────────────────────────────────────────────────────

SAMPLE_RECORD = {
    "student": {
        "usn": "1CS22001",
        "first_name": "Arjun",
        "last_name": "Sharma",
        "dob": date(2004, 3, 15),
        "email": "arjun.sharma@college.edu",
        "program": "B.E. Computer Science",
        "admission_year": 2022,
        "department_name": "Computer Science and Engineering",
    },
    "enrollments": [
        {
            "course_code": "CS101",
            "course_name": "Introduction to Programming",
            "credits": 4,
            "academic_year": 2022,
            "semester_number": 1,
            "internal_marks": Decimal("28.00"),
            "external_marks": Decimal("62.00"),
            "grade": "A+",
            "grade_point": Decimal("10.00"),
        },
        {
            "course_code": "MA101",
            "course_name": "Engineering Mathematics I",
            "credits": 4,
            "academic_year": 2022,
            "semester_number": 1,
            "internal_marks": Decimal("25.00"),
            "external_marks": Decimal("58.00"),
            "grade": "A",
            "grade_point": Decimal("9.00"),
        },
    ],
    "semester_results": [
        {
            "sem_no": 1,
            "sgpa": Decimal("9.50"),
            "total_credits": 8,
            "result_status": "PASS",
        },
    ],
    "record_timestamp": "2026-10-22T10:00:00Z",
}


# ── T1: Determinism ──────────────────────────────────────────────────────────

class TestDeterminism:
    """Same canonical data produces the same SHA-256 hash."""

    def test_same_data_same_hash(self):
        """T1.1: Identical dicts produce identical hashes."""
        import copy
        record_a = copy.deepcopy(SAMPLE_RECORD)
        record_b = copy.deepcopy(SAMPLE_RECORD)
        assert canonical_hash(record_a) == canonical_hash(record_b)

    def test_same_data_same_canonical(self):
        """T1.2: Identical dicts produce identical canonical strings."""
        import copy
        record_a = copy.deepcopy(SAMPLE_RECORD)
        record_b = copy.deepcopy(SAMPLE_RECORD)
        assert canonicalize(record_a) == canonicalize(record_b)

    def test_repeated_calls(self):
        """T1.3: Multiple calls produce the same result."""
        hashes = [canonical_hash(SAMPLE_RECORD) for _ in range(10)]
        assert len(set(hashes)) == 1

    def test_hash_is_64_hex(self):
        """T1.4: SHA-256 produces a 64-character hex string."""
        h = canonical_hash(SAMPLE_RECORD)
        assert len(h) == 64
        assert all(c in '0123456789abcdef' for c in h)


# ── T2: Sensitivity ──────────────────────────────────────────────────────────

class TestSensitivity:
    """Changed data produces different hashes."""

    def test_changed_mark_changes_hash(self):
        """T2.1: Changing internal_marks changes the hash."""
        import copy
        modified = copy.deepcopy(SAMPLE_RECORD)
        modified["enrollments"][0]["internal_marks"] = Decimal("27.00")
        assert canonical_hash(modified) != canonical_hash(SAMPLE_RECORD)

    def test_changed_grade_changes_hash(self):
        """T2.2: Changing a grade changes the hash."""
        import copy
        modified = copy.deepcopy(SAMPLE_RECORD)
        modified["enrollments"][0]["grade"] = "A"
        assert canonical_hash(modified) != canonical_hash(SAMPLE_RECORD)

    def test_changed_name_changes_hash(self):
        """T2.3: Changing the student name changes the hash."""
        import copy
        modified = copy.deepcopy(SAMPLE_RECORD)
        modified["student"]["first_name"] = "Arjuna"
        assert canonical_hash(modified) != canonical_hash(SAMPLE_RECORD)

    def test_changed_sgpa_changes_hash(self):
        """T2.4: Changing SGPA changes the hash."""
        import copy
        modified = copy.deepcopy(SAMPLE_RECORD)
        modified["semester_results"][0]["sgpa"] = Decimal("9.00")
        assert canonical_hash(modified) != canonical_hash(SAMPLE_RECORD)

    def test_changed_timestamp_changes_hash(self):
        """T2.5: Changing record_timestamp changes the hash."""
        import copy
        modified = copy.deepcopy(SAMPLE_RECORD)
        modified["record_timestamp"] = "2026-10-22T10:00:01Z"
        assert canonical_hash(modified) != canonical_hash(SAMPLE_RECORD)


# ── T3: Key Ordering ─────────────────────────────────────────────────────────

class TestKeyOrdering:
    """Key ordering in the input dict doesn't affect the canonical form."""

    def test_different_key_order_same_hash(self):
        """T3.1: Different key insertion order → same hash."""
        record_a = {
            "z_field": "last",
            "a_field": "first",
            "m_field": Decimal("5.00"),
        }
        record_b = {
            "a_field": "first",
            "m_field": Decimal("5.00"),
            "z_field": "last",
        }
        assert canonicalize(record_a) == canonicalize(record_b)
        assert canonical_hash(record_a) == canonical_hash(record_b)

    def test_nested_key_order(self):
        """T3.2: Nested dict key order doesn't matter."""
        record_a = {"outer": {"z": 1, "a": 2}}
        record_b = {"outer": {"a": 2, "z": 1}}
        assert canonicalize(record_a) == canonicalize(record_b)


# ── T4: Decimal Precision ────────────────────────────────────────────────────

class TestDecimalPrecision:
    """Decimal values are serialized with explicit precision."""

    def test_decimal_trailing_zeros(self):
        """T4.1: Decimal('9.50') serializes as '9.50', not '9.5'."""
        canon = canonicalize({"value": Decimal("9.50")})
        assert '"9.50"' in canon

    def test_decimal_no_trailing_zero(self):
        """T4.2: Decimal('9.5') serializes as '9.5'."""
        canon = canonicalize({"value": Decimal("9.5")})
        assert '"9.5"' in canon

    def test_decimal_integer_like(self):
        """T4.3: Decimal('10.00') serializes as '10.00'."""
        canon = canonicalize({"value": Decimal("10.00")})
        assert '"10.00"' in canon


# ── T5: Date Serialization ───────────────────────────────────────────────────

class TestDateSerialization:
    def test_date_iso_format(self):
        """T5.1: date objects serialize as YYYY-MM-DD."""
        canon = canonicalize({"dob": date(2004, 3, 15)})
        assert '"2004-03-15"' in canon

    def test_datetime_truncated(self):
        """T5.2: datetime objects are truncated to date."""
        from datetime import datetime
        canon = canonicalize({"dob": datetime(2004, 3, 15, 10, 30, 0)})
        assert '"2004-03-15"' in canon


# ── T6: None Handling ─────────────────────────────────────────────────────────

class TestNoneHandling:
    def test_none_becomes_null(self):
        """T6.1: None serializes as JSON null."""
        canon = canonicalize({"email": None})
        assert '"email":null' in canon

    def test_none_in_list(self):
        """T6.2: None in a list serializes as null."""
        canon = canonicalize({"marks": [None, Decimal("28.00")]})
        assert "[null," in canon


# ── T7: Float Rejection ──────────────────────────────────────────────────────

class TestFloatRejection:
    def test_float_raises_error(self):
        """T7.1: Float values are rejected — must use Decimal."""
        with pytest.raises(TypeError, match="Float values are not allowed"):
            canonicalize({"sgpa": 9.5})

    def test_float_in_nested(self):
        """T7.2: Float in nested structure is rejected."""
        with pytest.raises(TypeError):
            canonicalize({"results": [{"sgpa": 9.5}]})


# ── T8: Verify Hash ──────────────────────────────────────────────────────────

class TestVerifyHash:
    def test_verify_correct(self):
        """T8.1: verify_hash returns True for correct hash."""
        h = canonical_hash(SAMPLE_RECORD)
        assert verify_hash(SAMPLE_RECORD, h) is True

    def test_verify_wrong_hash(self):
        """T8.2: verify_hash returns False for wrong hash."""
        assert verify_hash(SAMPLE_RECORD, "0" * 64) is False

    def test_verify_modified_data(self):
        """T8.3: Modified data fails verification against original hash."""
        import copy
        h = canonical_hash(SAMPLE_RECORD)
        modified = copy.deepcopy(SAMPLE_RECORD)
        modified["enrollments"][0]["internal_marks"] = Decimal("29.00")
        assert verify_hash(modified, h) is False
