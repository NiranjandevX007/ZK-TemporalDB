"""
ZK-TemporalDB -- MongoDB Integration Tests (T9 Extension)

Tests B: Verify PostgreSQL/MongoDB integration (Task B from the brief).

Demonstrates:
  - check_mongo() behaviour (live + unavailable scenarios)
  - Saving/retrieving a fictional JSON academic-record snapshot in MongoDB
    linked to an existing PostgreSQL student_id
  - Verifying that modifications to a snapshot are detected (hash chain)
  - Verifying that MongoDB and PostgreSQL remain consistent

Run:
    pytest person2/tests/test_mongo_integration.py -v

These tests need:
  - A live PostgreSQL database (zk_temporaldb) -- auto-skipped if unavailable.
  - A live MongoDB server -- tests that require Mongo are skipped if unavailable.
    Tests that verify *unavailability* behaviour always run.

Test IDs:
    T9-A: check_mongo() reports correct status
    T9-B: Save/retrieve fictional academic snapshot in MongoDB
    T9-C: Modification detected via hash mismatch
    T9-D: PG+Mongo consistent after create_version with mongo_db
    T9-E: Service works in PG-only mode
"""

import json
import hashlib
import pytest
from datetime import datetime, timezone


# -- Skip guards ---------------------------------------------------------------

def _pg_available():
    try:
        from person2.db import get_pg_connection
        conn = get_pg_connection()
        conn.close()
        return True
    except Exception:
        return False


def _mongo_available():
    try:
        import person2.db as db_module
        old = db_module._mongo_client
        db_module._mongo_client = None
        client = db_module.get_mongo_client()
        client.admin.command("ping")
        db_module.close_mongo()
        db_module._mongo_client = old
        return True
    except Exception:
        return False


PG_AVAILABLE = _pg_available()
MONGO_AVAILABLE = _mongo_available()

pg_skip = pytest.mark.skipif(
    not PG_AVAILABLE, reason="PostgreSQL not available"
)
mongo_skip = pytest.mark.skipif(
    not MONGO_AVAILABLE, reason="MongoDB not available at localhost:27017"
)


# -- Fixtures ------------------------------------------------------------------

@pytest.fixture
def pg_conn():
    """PostgreSQL connection, always rolled back after test."""
    if not PG_AVAILABLE:
        pytest.skip("PostgreSQL not available")
    from person2.db import get_pg_connection
    conn = get_pg_connection()
    conn.rollback()

    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(version_id), 0) FROM record_version")
    init_vid = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(MAX(batch_id), 0) FROM merkle_batch")
    init_bid = cur.fetchone()[0]
    cur.close()

    yield conn

    try:
        conn.rollback()
    except Exception:
        pass
    try:
        cur = conn.cursor()
        cur.execute("ALTER TABLE merkle_batch_member DISABLE TRIGGER trg_deny_modify_merkle_batch_member")
        cur.execute("ALTER TABLE merkle_batch DISABLE TRIGGER trg_deny_modify_merkle_batch")
        cur.execute("ALTER TABLE record_version DISABLE TRIGGER trg_deny_modify_record_version")
        cur.execute("DELETE FROM merkle_batch_member WHERE batch_id > %s OR version_id > %s", (init_bid, init_vid))
        cur.execute("DELETE FROM merkle_batch WHERE batch_id > %s", (init_bid,))
        cur.execute("DELETE FROM record_version WHERE version_id > %s", (init_vid,))
        cur.execute("ALTER TABLE record_version ENABLE TRIGGER trg_deny_modify_record_version")
        cur.execute("ALTER TABLE merkle_batch ENABLE TRIGGER trg_deny_modify_merkle_batch")
        cur.execute("ALTER TABLE merkle_batch_member ENABLE TRIGGER trg_deny_modify_merkle_batch_member")
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


@pytest.fixture
def mongo_db():
    """Live MongoDB database fixture; skips if unavailable."""
    if not MONGO_AVAILABLE:
        pytest.skip("MongoDB not available at localhost:27017")
    from person2.db import get_mongo_db, close_mongo
    db = get_mongo_db()
    yield db
    db.record_snapshots_test.drop()
    close_mongo()


# -- T9-A: check_mongo() status -----------------------------------------------

class TestCheckMongoStatus:
    """T9-A: check_mongo() returns expected shape regardless of availability."""

    def test_check_mongo_returns_dict(self):
        """T9-A.1: check_mongo() always returns a dict."""
        from person2.db import check_mongo, close_mongo
        result = check_mongo()
        close_mongo()
        assert isinstance(result, dict)

    def test_check_mongo_has_status_key(self):
        """T9-A.2: check_mongo() dict contains 'status' key."""
        from person2.db import check_mongo, close_mongo
        result = check_mongo()
        close_mongo()
        assert "status" in result

    def test_check_mongo_status_value(self):
        """T9-A.3: check_mongo() status is 'ok' or 'error'."""
        from person2.db import check_mongo, close_mongo
        result = check_mongo()
        close_mongo()
        assert result["status"] in ("ok", "error")

    @mongo_skip
    def test_check_mongo_ok_when_available(self):
        """T9-A.4: check_mongo() returns 'ok' when MongoDB is running."""
        from person2.db import check_mongo, close_mongo
        result = check_mongo()
        close_mongo()
        assert result["status"] == "ok"
        assert "version" in result
        assert len(result["version"]) > 0

    def test_check_mongo_error_when_unavailable(self):
        """T9-A.5: check_mongo() returns 'error' when connection is refused.

        Temporarily points the module at port 1 (always refused on macOS).
        """
        import os
        import person2.db as db_module
        original_uri = os.environ.get("MONGO_URI")
        old_client = db_module._mongo_client
        os.environ["MONGO_URI"] = "mongodb://localhost:1/"
        db_module._mongo_client = None
        try:
            result = db_module.check_mongo()
            assert result["status"] == "error"
            assert "error" in result
        finally:
            if original_uri is not None:
                os.environ["MONGO_URI"] = original_uri
            else:
                os.environ.pop("MONGO_URI", None)
            db_module._mongo_client = old_client


# -- T9-B: Save/retrieve academic snapshot in MongoDB -------------------------

class TestMongoSnapshotCRUD:
    """T9-B: Save and retrieve a fictional JSON academic-record snapshot."""

    @mongo_skip
    def test_insert_fictional_snapshot(self, mongo_db):
        """T9-B.1: Insert a fictional snapshot and retrieve it by student_id."""
        fictional_snapshot = {
            "student_id": 9901,
            "student": {
                "usn": "FICTIONAL001",
                "first_name": "Alice",
                "last_name": "Demo",
                "cgpa": 9.5,
                "program": "B.E. Computer Science",
                "department": "CSE",
                "admission_year": 2022,
            },
            "enrollments": [
                {
                    "course_code": "CS101",
                    "course_name": "Introduction to Programming",
                    "credits": 4,
                    "grade": "O",
                    "grade_point": 10,
                }
            ],
            "semester_results": [
                {"sem_no": 1, "sgpa": 9.5, "total_credits": 4, "result_status": "PASS"}
            ],
            "record_timestamp": "2026-10-22T11:00:00Z",
        }
        canonical_str = json.dumps(fictional_snapshot, sort_keys=True, separators=(',', ':'))
        snapshot_hash = hashlib.sha256(canonical_str.encode()).hexdigest()

        doc = {
            "version_id": 99001,
            "student_id": 9901,
            "version_number": 1,
            "snapshot_hash": snapshot_hash,
            "prev_hash": None,
            "canonical_snapshot": canonical_str,
            "record": fictional_snapshot,
            "created_at": datetime.now(timezone.utc),
        }

        result = mongo_db.record_snapshots_test.insert_one(doc)
        assert result.inserted_id is not None

        retrieved = mongo_db.record_snapshots_test.find_one({"student_id": 9901})
        assert retrieved is not None
        assert retrieved["student_id"] == 9901
        assert retrieved["snapshot_hash"] == snapshot_hash
        assert retrieved["version_number"] == 1
        assert retrieved["record"]["student"]["usn"] == "FICTIONAL001"

    @mongo_skip
    def test_hash_links_to_postgres_student_id(self, mongo_db):
        """T9-B.2: Snapshot stored with PostgreSQL student_id=1; hash matches."""
        fictional_record = {
            "student_id": 1,
            "usn": "1CS22001",
            "cgpa": 9.5,
            "note": "fictional snapshot for testing",
        }
        canonical_str = json.dumps(fictional_record, sort_keys=True, separators=(',', ':'))
        expected_hash = hashlib.sha256(canonical_str.encode()).hexdigest()

        mongo_db.record_snapshots_test.insert_one({
            "version_id": 99002,
            "student_id": 1,
            "version_number": 1,
            "snapshot_hash": expected_hash,
            "canonical_snapshot": canonical_str,
            "record": fictional_record,
            "created_at": datetime.now(timezone.utc),
        })

        found = mongo_db.record_snapshots_test.find_one({"version_id": 99002})
        recomputed = hashlib.sha256(found["canonical_snapshot"].encode()).hexdigest()
        assert recomputed == found["snapshot_hash"], (
            "Hash mismatch: stored hash does not match re-computation of canonical_snapshot"
        )

    @mongo_skip
    def test_retrieve_by_version_id(self, mongo_db):
        """T9-B.3: Retrieve snapshot by version_id (like versioning.py does)."""
        record = {"student_id": 9903, "note": "retrieve test"}
        canon = json.dumps(record, sort_keys=True, separators=(',', ':'))
        h = hashlib.sha256(canon.encode()).hexdigest()

        mongo_db.record_snapshots_test.insert_one({
            "version_id": 99003,
            "student_id": 9903,
            "snapshot_hash": h,
            "canonical_snapshot": canon,
            "created_at": datetime.now(timezone.utc),
        })

        found = mongo_db.record_snapshots_test.find_one({"version_id": 99003})
        assert found is not None
        assert found["version_id"] == 99003


# -- T9-C: Modification detection ---------------------------------------------

class TestMongoModificationDetection:
    """T9-C: Verify that modifications to stored snapshots are detected."""

    @mongo_skip
    def test_tampered_canonical_snapshot_detected(self, mongo_db):
        """T9-C.1: If canonical_snapshot is tampered, re-computed hash differs."""
        original = {"student_id": 9910, "cgpa": 9.5, "name": "Alice"}
        canon = json.dumps(original, sort_keys=True, separators=(',', ':'))
        stored_hash = hashlib.sha256(canon.encode()).hexdigest()

        mongo_db.record_snapshots_test.insert_one({
            "version_id": 99010,
            "student_id": 9910,
            "snapshot_hash": stored_hash,
            "canonical_snapshot": canon,
            "created_at": datetime.now(timezone.utc),
        })

        # Tamper: change the CGPA value in the stored document
        mongo_db.record_snapshots_test.update_one(
            {"version_id": 99010},
            {"$set": {"canonical_snapshot": canon.replace("9.5", "10.0")}}
        )

        found = mongo_db.record_snapshots_test.find_one({"version_id": 99010})
        recomputed = hashlib.sha256(found["canonical_snapshot"].encode()).hexdigest()
        assert recomputed != found["snapshot_hash"], (
            "Expected hash mismatch after tampering, but hashes still match!"
        )

    @mongo_skip
    def test_stored_hash_matches_unmodified(self, mongo_db):
        """T9-C.2: Unmodified snapshot passes hash re-verification."""
        original = {"student_id": 9911, "cgpa": 7.5, "name": "Bob"}
        canon = json.dumps(original, sort_keys=True, separators=(',', ':'))
        h = hashlib.sha256(canon.encode()).hexdigest()

        mongo_db.record_snapshots_test.insert_one({
            "version_id": 99011,
            "snapshot_hash": h,
            "canonical_snapshot": canon,
            "created_at": datetime.now(timezone.utc),
        })

        found = mongo_db.record_snapshots_test.find_one({"version_id": 99011})
        recomputed = hashlib.sha256(found["canonical_snapshot"].encode()).hexdigest()
        assert recomputed == found["snapshot_hash"]


# -- T9-D: PG + Mongo dual-write (live) ---------------------------------------

class TestPGMongoConsistency:
    """T9-D: PG + MongoDB dual-write via RecordVersionService."""

    @pg_skip
    @mongo_skip
    def test_dual_write_create_version(self, pg_conn, mongo_db):
        """T9-D.1: create_version writes to PG AND Mongo; both consistent."""
        from person2.versioning import RecordVersionService
        svc = RecordVersionService(pg_conn, mongo_db=mongo_db, auto_commit=False)
        v = svc.create_version(student_id=1)
        pg_conn.commit()

        assert v["version_id"] is not None
        assert v["mongo_doc_id"] is not None

        mongo_doc = mongo_db.record_snapshots.find_one({"version_id": v["version_id"]})
        assert mongo_doc is not None, "MongoDB document not created"
        assert mongo_doc["snapshot_hash"] == v["snapshot_hash"]
        assert mongo_doc["student_id"] == 1

        mongo_db.record_snapshots.delete_one({"version_id": v["version_id"]})

    @pg_skip
    @mongo_skip
    def test_verify_version_includes_mongo_check(self, pg_conn, mongo_db):
        """T9-D.2: verify_version checks MongoDB consistency when available."""
        from person2.versioning import RecordVersionService
        svc = RecordVersionService(pg_conn, mongo_db=mongo_db, auto_commit=False)
        v = svc.create_version(student_id=2)
        pg_conn.commit()

        result = svc.verify_version(v["version_id"])
        assert result["valid"] is True
        assert result["checks"].get("mongo_consistent") is True

        mongo_db.record_snapshots.delete_one({"version_id": v["version_id"]})

    @pg_skip
    @mongo_skip
    def test_pg_mongo_discrepancy_detected(self, pg_conn, mongo_db):
        """T9-D.3: If Mongo snapshot is altered, verify_version reports invalid."""
        from person2.versioning import RecordVersionService
        svc = RecordVersionService(pg_conn, mongo_db=mongo_db, auto_commit=False)
        v = svc.create_version(student_id=3)
        pg_conn.commit()

        mongo_db.record_snapshots.update_one(
            {"version_id": v["version_id"]},
            {"$set": {"snapshot_hash": "0" * 64}}
        )

        result = svc.verify_version(v["version_id"])
        assert result["checks"].get("mongo_consistent") is False

        mongo_db.record_snapshots.delete_one({"version_id": v["version_id"]})


# -- T9-E: PG-only mode when Mongo is unavailable -----------------------------

class TestPGOnlyMode:
    """T9-E: Service works in PG-only mode when MongoDB is unavailable."""

    @pg_skip
    def test_create_version_without_mongo(self, pg_conn):
        """T9-E.1: create_version succeeds with mongo_db=None."""
        from person2.versioning import RecordVersionService
        svc = RecordVersionService(pg_conn, mongo_db=None, auto_commit=False)
        v = svc.create_version(student_id=1)
        assert v["version_id"] is not None
        assert v["mongo_doc_id"] is None

    @pg_skip
    def test_verify_version_skips_mongo_check(self, pg_conn):
        """T9-E.2: verify_version sets mongo_consistent=None when mongo_db=None."""
        from person2.versioning import RecordVersionService
        svc = RecordVersionService(pg_conn, mongo_db=None, auto_commit=False)
        v = svc.create_version(student_id=1)

        result = svc.verify_version(v["version_id"])
        assert result["valid"] is True
        assert result["checks"].get("mongo_consistent") is None

    def test_services_from_env_tolerates_no_mongo(self, monkeypatch):
        """T9-E.3: AcademicRecordService.from_env() does not crash if MongoDB down."""
        if not PG_AVAILABLE:
            pytest.skip("PostgreSQL not available")
        import person2.db as db_module
        old_client = db_module._mongo_client
        db_module._mongo_client = None
        monkeypatch.setenv("MONGO_URI", "mongodb://localhost:1/")

        try:
            from person2.services import AcademicRecordService
            svc = AcademicRecordService.from_env(require_mongo=False)
            assert svc.mongo_db is None
            svc.close()
        finally:
            db_module._mongo_client = old_client
