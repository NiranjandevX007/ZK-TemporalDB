"""
ZK-TemporalDB — Integration Tests: PostgreSQL + Versioning + Merkle

These tests require a LIVE PostgreSQL connection to zk_temporaldb
with Person 1's schema and seed data loaded, AND Person 2's
security schema (person2_security_schema.sql) applied.

Run with:
    pytest person2/tests/test_integration.py -v

Skip if PostgreSQL is unavailable:
    These tests are auto-skipped if the database cannot be reached.

Test IDs:
    T3: First version and linked versions
    T4: Modified snapshots detected
    T5: Altered prev_hash fails chain verification
    T8: SQL FK and uniqueness enforced
    T9: SQL+MongoDB association and failure handling
    T11: No corruption of Person 1 data
"""

import copy
import json
import hashlib
import pytest
from decimal import Decimal

# ── Skip if no PostgreSQL ─────────────────────────────────────────────────────

def _pg_available():
    try:
        from person2.db import get_pg_connection
        conn = get_pg_connection()
        conn.close()
        return True
    except Exception:
        return False

pg_available = _pg_available()
pytestmark = pytest.mark.skipif(
    not pg_available,
    reason="PostgreSQL not available — skipping integration tests"
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def pg_conn():
    """Provide a PostgreSQL connection, rolled back after each test."""
    from person2.db import get_pg_connection
    conn = get_pg_connection()
    conn.rollback()

    # Track pre-existing max IDs before test runs
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(version_id), 0) FROM record_version")
    init_max_vid = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(MAX(batch_id), 0) FROM merkle_batch")
    init_max_bid = cur.fetchone()[0]
    cur.close()

    yield conn

    # Teardown: rollback uncommitted changes
    try:
        conn.rollback()
    except Exception:
        pass

    # Safety cleanup: if anything was committed during the test, clean up ONLY test-created rows
    try:
        cur = conn.cursor()
        cur.execute("ALTER TABLE merkle_batch_member DISABLE TRIGGER trg_deny_modify_merkle_batch_member")
        cur.execute("ALTER TABLE merkle_batch DISABLE TRIGGER trg_deny_modify_merkle_batch")
        cur.execute("ALTER TABLE record_version DISABLE TRIGGER trg_deny_modify_record_version")

        cur.execute("DELETE FROM merkle_batch_member WHERE batch_id > %s OR version_id > %s", (init_max_bid, init_max_vid))
        cur.execute("DELETE FROM merkle_batch WHERE batch_id > %s", (init_max_bid,))
        cur.execute("DELETE FROM record_version WHERE version_id > %s", (init_max_vid,))

        cur.execute("ALTER TABLE record_version ENABLE TRIGGER trg_deny_modify_record_version")
        cur.execute("ALTER TABLE merkle_batch ENABLE TRIGGER trg_deny_modify_merkle_batch")
        cur.execute("ALTER TABLE merkle_batch_member ENABLE TRIGGER trg_deny_modify_merkle_batch_member")
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cur.close()
        conn.close()


@pytest.fixture
def version_svc(pg_conn):
    from person2.versioning import RecordVersionService
    return RecordVersionService(pg_conn, mongo_db=None, auto_commit=False)


@pytest.fixture
def merkle_svc(pg_conn):
    from person2.merkle import MerkleBatchService
    return MerkleBatchService(pg_conn, mongo_db=None, auto_commit=False)


# ── T3: Version Creation ─────────────────────────────────────────────────────

class TestVersionCreation:
    """First version and subsequent linked versions."""

    def test_first_version(self, pg_conn, version_svc):
        """T3.1: First version has version_number=1, prev_hash=NULL."""
        v = version_svc.create_version(student_id=1)
        assert v["version_number"] == 1
        assert v["prev_hash"] is None
        assert v["snapshot_hash"] is not None
        assert len(v["snapshot_hash"]) == 64

    def test_second_version_linked(self, pg_conn, version_svc):
        """T3.2: Second version links to first via prev_hash."""
        v1 = version_svc.create_version(student_id=1)
        v2 = version_svc.create_version(student_id=1)
        assert v2["version_number"] == v1["version_number"] + 1
        assert v2["prev_hash"] == v1["snapshot_hash"]

    def test_version_contains_snapshot(self, pg_conn, version_svc):
        """T3.3: Version contains a parseable canonical snapshot."""
        v = version_svc.create_version(student_id=1)
        # Retrieve and check
        record = version_svc.get_record(student_id=1)
        assert record is not None
        assert "record" in record
        assert record["record"]["student"]["usn"] == "1CS22001"


# ── T4: Tamper Detection ─────────────────────────────────────────────────────

class TestTamperDetection:
    """Modified snapshots are detected by hash verification."""

    def test_valid_version_passes(self, pg_conn, version_svc):
        """T4.1: Unmodified version passes verification."""
        v = version_svc.create_version(student_id=1)
        result = version_svc.verify_version(v["version_id"])
        assert result["valid"] is True
        assert result["checks"]["hash_matches"] is True

    def test_tampered_snapshot_detected(self, pg_conn, version_svc):
        """T4.2: If we tamper with the stored snapshot, verification fails."""
        v = version_svc.create_version(student_id=1)
        vid = v["version_id"]

        # Bypass append-only trigger for testing
        import psycopg2.extras
        cur = pg_conn.cursor()

        # Disable trigger temporarily for tamper simulation
        cur.execute("ALTER TABLE record_version DISABLE TRIGGER trg_deny_modify_record_version")
        cur.execute("""
            UPDATE record_version
            SET canonical_snapshot = replace(canonical_snapshot, 'Arjun', 'TAMPERED')
            WHERE version_id = %s
        """, (vid,))
        cur.execute("ALTER TABLE record_version ENABLE TRIGGER trg_deny_modify_record_version")

        result = version_svc.verify_version(vid)
        assert result["valid"] is False
        assert result["checks"]["hash_matches"] is False


# ── T5: Chain Verification ───────────────────────────────────────────────────

class TestChainVerification:
    """Altered prev_hash fails chain verification."""

    def test_valid_chain(self, pg_conn, version_svc):
        """T5.1: Valid chain passes."""
        version_svc.create_version(student_id=2)
        version_svc.create_version(student_id=2)
        result = version_svc.verify_chain(student_id=2)
        assert result["valid"] is True
        assert result["versions_checked"] == 2

    def test_broken_prev_hash(self, pg_conn, version_svc):
        """T5.2: Altered prev_hash breaks chain verification."""
        version_svc.create_version(student_id=3)
        v2 = version_svc.create_version(student_id=3)

        # Tamper with prev_hash
        cur = pg_conn.cursor()
        cur.execute("ALTER TABLE record_version DISABLE TRIGGER trg_deny_modify_record_version")
        cur.execute("""
            UPDATE record_version SET prev_hash = %s WHERE version_id = %s
        """, ("0" * 64, v2["version_id"]))
        cur.execute("ALTER TABLE record_version ENABLE TRIGGER trg_deny_modify_record_version")

        result = version_svc.verify_chain(student_id=3)
        assert result["valid"] is False


# ── T8: SQL Constraints ──────────────────────────────────────────────────────

class TestSQLConstraints:
    """Foreign keys and uniqueness rules are enforced."""

    def test_fk_student_enforced(self, pg_conn):
        """T8.1: Cannot insert version for nonexistent student."""
        cur = pg_conn.cursor()
        with pytest.raises(Exception):  # ForeignKeyViolation
            cur.execute("""
                INSERT INTO record_version
                (student_id, version_number, snapshot_hash, canonical_snapshot)
                VALUES (9999, 1, %s, '{}')
            """, ("a" * 64,))

    def test_unique_version_enforced(self, pg_conn, version_svc):
        """T8.2: Cannot create duplicate version number for same student."""
        version_svc.create_version(student_id=1)
        cur = pg_conn.cursor()
        with pytest.raises(Exception):  # UniqueViolation
            cur.execute("""
                INSERT INTO record_version
                (student_id, version_number, snapshot_hash, canonical_snapshot)
                VALUES (1, 1, %s, '{}')
            """, ("b" * 64,))

    def test_append_only_no_update(self, pg_conn, version_svc):
        """T8.3: UPDATE on record_version is blocked by trigger."""
        v = version_svc.create_version(student_id=1)
        cur = pg_conn.cursor()
        with pytest.raises(Exception, match="append-only"):
            cur.execute("""
                UPDATE record_version SET snapshot_hash = %s
                WHERE version_id = %s
            """, ("c" * 64, v["version_id"]))

    def test_append_only_no_delete(self, pg_conn, version_svc):
        """T8.4: DELETE on record_version is blocked by trigger."""
        v = version_svc.create_version(student_id=1)
        cur = pg_conn.cursor()
        with pytest.raises(Exception, match="append-only"):
            cur.execute("""
                DELETE FROM record_version WHERE version_id = %s
            """, (v["version_id"],))

    def test_prev_hash_null_for_v1(self, pg_conn):
        """T8.5: Version 1 must have NULL prev_hash (CHECK constraint)."""
        cur = pg_conn.cursor()
        with pytest.raises(Exception):  # CheckViolation
            cur.execute("""
                INSERT INTO record_version
                (student_id, version_number, snapshot_hash, prev_hash, canonical_snapshot)
                VALUES (1, 1, %s, %s, '{}')
            """, ("d" * 64, "e" * 64))

    def test_prev_hash_required_for_v2(self, pg_conn):
        """T8.6: Version > 1 must have non-NULL prev_hash."""
        cur = pg_conn.cursor()
        with pytest.raises(Exception):  # CheckViolation
            cur.execute("""
                INSERT INTO record_version
                (student_id, version_number, snapshot_hash, prev_hash, canonical_snapshot)
                VALUES (1, 2, %s, NULL, '{}')
            """, ("f" * 64,))


# ── T11: Person 1 Data Integrity ──────────────────────────────────────────────

class TestPerson1Integrity:
    """Verify Person 1's tables and data remain intact."""

    def test_person1_tables_exist(self, pg_conn):
        """T11.1: All 6 Person 1 tables still exist."""
        cur = pg_conn.cursor()
        expected = ['department', 'student', 'course', 'enrolled_in',
                    'semester_result', 'system_user']
        for table in expected:
            cur.execute("""
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
            """, (table,))
            assert cur.fetchone() is not None, f"Table {table} missing!"

    def test_person1_row_counts(self, pg_conn):
        """T11.2: Person 1 row counts unchanged."""
        cur = pg_conn.cursor()
        expected = {
            'department': 3,
            'student': 5,
            'course': 6,
            'enrolled_in': 12,
            'semester_result': 5,
        }
        for table, count in expected.items():
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            actual = cur.fetchone()[0]
            assert actual == count, (
                f"{table}: expected {count} rows, found {actual}"
            )

    def test_student_usns_intact(self, pg_conn):
        """T11.3: Student USNs match seed data."""
        cur = pg_conn.cursor()
        cur.execute("SELECT usn FROM student ORDER BY student_id")
        usns = [row[0] for row in cur.fetchall()]
        assert usns == ['1CS22001', '1CS22002', '1CS22003', '1EC22001', '1EC22002']


# ── T9: Merkle Batch with PostgreSQL ─────────────────────────────────────────

class TestMerkleBatchIntegration:
    """Merkle batch creation and verification against PostgreSQL."""

    def test_create_and_verify_batch(self, pg_conn, version_svc, merkle_svc):
        """T9.1: Create versions, batch them, verify inclusion."""
        v1 = version_svc.create_version(student_id=1)
        v2 = version_svc.create_version(student_id=2)

        batch = merkle_svc.create_batch(
            [v1["version_id"], v2["version_id"]],
            description="Test batch"
        )
        assert batch["merkle_root"] is not None
        assert batch["leaf_count"] == 2

        # Verify inclusion
        r1 = merkle_svc.verify_inclusion(batch["batch_id"], v1["version_id"])
        assert r1["valid"] is True

        r2 = merkle_svc.verify_inclusion(batch["batch_id"], v2["version_id"])
        assert r2["valid"] is True

    def test_non_member_fails(self, pg_conn, version_svc, merkle_svc):
        """T9.2: Non-member version fails inclusion check."""
        v1 = version_svc.create_version(student_id=1)
        v2 = version_svc.create_version(student_id=2)
        v3 = version_svc.create_version(student_id=3)

        batch = merkle_svc.create_batch([v1["version_id"], v2["version_id"]])

        result = merkle_svc.verify_inclusion(batch["batch_id"], v3["version_id"])
        assert result["valid"] is False
