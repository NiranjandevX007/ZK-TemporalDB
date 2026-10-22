"""
ZK-TemporalDB — Record Versioning with SHA-256 Hash Chain

Creates append-only versioned snapshots of academic records.
Each version contains:
    - A canonical JSON snapshot of the student's record at that point
    - A SHA-256 hash of the canonical snapshot
    - A prev_hash linking to the previous version (NULL for version 1)
    - A monotonically increasing version number per student

The version chain provides tamper-evidence: modifying any stored snapshot
breaks the hash chain. This does NOT prevent a privileged admin who controls
both PostgreSQL and MongoDB from rewriting the entire chain — that threat
requires Merkle roots published to an external trust anchor.

Usage:
    from person2.versioning import RecordVersionService
    svc = RecordVersionService(pg_conn, mongo_db)
    version = svc.create_version(student_id=1)
    ok = svc.verify_version(version_id=1)
"""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

from person2.canonical import canonicalize, canonical_hash

logger = logging.getLogger(__name__)


def build_academic_record(pg_conn, student_id: int) -> dict:
    """
    Fetch and assemble a complete academic record from PostgreSQL.

    Returns a dict suitable for canonicalization, with all numeric values
    as Decimal (not float) and dates as date objects.

    Structure:
        {
            "student": { usn, first_name, last_name, dob, email, program,
                         admission_year, department_name },
            "enrollments": [ { course_code, course_name, credits,
                               academic_year, semester_number,
                               internal_marks, external_marks,
                               grade, grade_point } ],
            "semester_results": [ { sem_no, sgpa, total_credits,
                                    result_status } ],
            "record_timestamp": "YYYY-MM-DDTHH:MM:SSZ"
        }
    """
    import psycopg2.extras

    cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Fetch student info with department name
    cur.execute("""
        SELECT s.student_id, s.usn, s.first_name, s.last_name,
               s.dob, s.email, s.program, s.admission_year,
               d.department_name
        FROM student s
        JOIN department d ON d.department_id = s.department_id
        WHERE s.student_id = %s
    """, (student_id,))
    student_row = cur.fetchone()
    if not student_row:
        raise ValueError(f"Student {student_id} not found")

    student_dict = {
        "usn": student_row["usn"],
        "first_name": student_row["first_name"],
        "last_name": student_row["last_name"],
        "dob": student_row["dob"],
        "email": student_row["email"],
        "program": student_row["program"],
        "admission_year": student_row["admission_year"],
        "department_name": student_row["department_name"],
    }

    # Fetch enrollments (sorted for determinism)
    cur.execute("""
        SELECT c.course_code, c.course_name, c.credits,
               e.academic_year, e.semester_number,
               e.internal_marks, e.external_marks,
               e.grade, e.grade_point
        FROM enrolled_in e
        JOIN course c ON c.course_id = e.course_id
        WHERE e.student_id = %s
        ORDER BY e.academic_year, e.semester_number, c.course_code
    """, (student_id,))
    enrollments = []
    for row in cur.fetchall():
        enrollments.append({
            "course_code": row["course_code"],
            "course_name": row["course_name"],
            "credits": row["credits"],
            "academic_year": row["academic_year"],
            "semester_number": row["semester_number"],
            "internal_marks": row["internal_marks"],
            "external_marks": row["external_marks"],
            "grade": row["grade"],
            "grade_point": row["grade_point"],
        })

    # Fetch semester results (sorted for determinism)
    cur.execute("""
        SELECT sem_no, sgpa, total_credits, result_status
        FROM semester_result
        WHERE student_id = %s
        ORDER BY sem_no
    """, (student_id,))
    sem_results = []
    for row in cur.fetchall():
        sem_results.append({
            "sem_no": row["sem_no"],
            "sgpa": row["sgpa"],
            "total_credits": row["total_credits"],
            "result_status": row["result_status"],
        })

    cur.close()

    return {
        "student": student_dict,
        "enrollments": enrollments,
        "semester_results": sem_results,
        "record_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


class RecordVersionService:
    """
    High-level service for creating and verifying record versions.

    Stores version metadata in PostgreSQL (record_version table)
    and the full canonical snapshot in MongoDB (record_snapshots collection).

    Cross-database consistency:
        PostgreSQL is written first (version metadata).
        MongoDB is written second (full snapshot document).
        If MongoDB write fails, the PostgreSQL transaction is rolled back.
        The version is only committed when both writes succeed.

    Limitations:
        This is NOT a true distributed transaction (no 2PC).
        If the process crashes between PG commit and Mongo write, the PG row
        exists without a Mongo document. The verify_version method detects
        this inconsistency. A recovery/cleanup procedure is documented.
    """

    def __init__(self, pg_conn, mongo_db=None, auto_commit: bool = True):
        """
        Args:
            pg_conn: A psycopg2 connection (autocommit=False).
            mongo_db: A pymongo Database object, or None for PG-only mode.
            auto_commit: Whether to commit PostgreSQL transactions automatically (default True).
        """
        self.pg_conn = pg_conn
        self.mongo_db = mongo_db
        self.auto_commit = auto_commit

    def get_latest_version(self, student_id: int) -> dict | None:
        """Return the latest version row for a student, or None."""
        import psycopg2.extras
        cur = self.pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT version_id, student_id, version_number,
                   snapshot_hash, prev_hash, canonical_snapshot,
                   snapshot_scope, created_at
            FROM record_version
            WHERE student_id = %s
            ORDER BY version_number DESC
            LIMIT 1
        """, (student_id,))
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None

    def create_version(self, student_id: int, record: dict = None) -> dict:
        """
        Create a new record version for a student.

        Steps:
            1. Build the academic record from PostgreSQL (or use provided).
            2. Determine version_number and prev_hash.
            3. Canonicalize and hash.
            4. INSERT into record_version (PostgreSQL).
            5. INSERT into record_snapshots (MongoDB).
            6. COMMIT PostgreSQL.

        Args:
            student_id: The student's ID in the student table.
            record: Optional pre-built record dict (for testing).

        Returns:
            Dict with version metadata including version_id, hash, etc.

        Raises:
            ValueError: If the student doesn't exist.
            Exception: On database errors (transaction is rolled back).
        """
        import psycopg2.extras

        try:
            # Step 1: Build or use provided record
            if record is None:
                record = build_academic_record(self.pg_conn, student_id)

            # Step 2: Determine version chain
            latest = self.get_latest_version(student_id)
            if latest:
                version_number = latest["version_number"] + 1
                prev_hash = latest["snapshot_hash"]
            else:
                version_number = 1
                prev_hash = None

            # Step 3: Canonicalize and hash
            canon_str = canonicalize(record)
            snap_hash = canonical_hash(record)

            # Step 4: Insert into PostgreSQL
            cur = self.pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                INSERT INTO record_version
                    (student_id, version_number, snapshot_hash, prev_hash,
                     canonical_snapshot, snapshot_scope)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING version_id, student_id, version_number,
                          snapshot_hash, prev_hash, snapshot_scope, created_at
            """, (student_id, version_number, snap_hash, prev_hash,
                  canon_str, 'full_academic_record'))
            version_row = dict(cur.fetchone())
            cur.close()

            # Step 5: Insert into MongoDB (if available)
            mongo_doc_id = None
            if self.mongo_db is not None:
                try:
                    doc = {
                        "version_id": version_row["version_id"],
                        "student_id": student_id,
                        "version_number": version_number,
                        "snapshot_hash": snap_hash,
                        "prev_hash": prev_hash,
                        "canonical_snapshot": canon_str,
                        "record": json.loads(canon_str),
                        "created_at": datetime.now(timezone.utc),
                    }
                    result = self.mongo_db.record_snapshots.insert_one(doc)
                    mongo_doc_id = str(result.inserted_id)
                    logger.info("MongoDB snapshot saved: %s", mongo_doc_id)
                except Exception as e:
                    # MongoDB write failed — roll back PostgreSQL
                    self.pg_conn.rollback()
                    raise RuntimeError(
                        f"MongoDB write failed, PostgreSQL rolled back: {e}"
                    ) from e

            # Step 6: Commit PostgreSQL (if auto_commit is enabled)
            if self.auto_commit:
                self.pg_conn.commit()

            version_row["mongo_doc_id"] = mongo_doc_id
            logger.info(
                "Created version %d for student %d (hash: %s…)",
                version_number, student_id, snap_hash[:16]
            )
            return version_row

        except Exception:
            self.pg_conn.rollback()
            raise

    def verify_version(self, version_id: int) -> dict:
        """
        Verify the integrity of a stored record version.

        Checks:
            1. The canonical snapshot in PostgreSQL produces the stored hash.
            2. The prev_hash matches the previous version's snapshot_hash.
            3. If MongoDB is available, the MongoDB copy matches PostgreSQL.

        Returns:
            {
                "valid": bool,
                "checks": {
                    "hash_matches": bool,
                    "prev_hash_valid": bool or None,
                    "mongo_consistent": bool or None,
                },
                "details": str
            }
        """
        import psycopg2.extras
        import hashlib

        cur = self.pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT version_id, student_id, version_number,
                   snapshot_hash, prev_hash, canonical_snapshot,
                   snapshot_scope, created_at
            FROM record_version
            WHERE version_id = %s
        """, (version_id,))
        row = cur.fetchone()
        if not row:
            return {
                "valid": False,
                "checks": {},
                "details": f"Version {version_id} not found"
            }

        checks = {}
        details = []

        # Check 1: Recompute hash from stored canonical snapshot
        stored_canon = row["canonical_snapshot"]
        recomputed = hashlib.sha256(stored_canon.encode('utf-8')).hexdigest()
        checks["hash_matches"] = (recomputed == row["snapshot_hash"])
        if not checks["hash_matches"]:
            details.append(
                f"HASH MISMATCH: stored={row['snapshot_hash']}, "
                f"recomputed={recomputed}"
            )

        # Check 2: Verify prev_hash chain
        if row["version_number"] == 1:
            checks["prev_hash_valid"] = (row["prev_hash"] is None)
            if not checks["prev_hash_valid"]:
                details.append("Version 1 should have NULL prev_hash")
        else:
            # Find the previous version
            cur.execute("""
                SELECT snapshot_hash
                FROM record_version
                WHERE student_id = %s AND version_number = %s
            """, (row["student_id"], row["version_number"] - 1))
            prev_row = cur.fetchone()
            if prev_row:
                checks["prev_hash_valid"] = (
                    row["prev_hash"] == prev_row["snapshot_hash"]
                )
                if not checks["prev_hash_valid"]:
                    details.append(
                        f"PREV_HASH MISMATCH: stored={row['prev_hash']}, "
                        f"expected={prev_row['snapshot_hash']}"
                    )
            else:
                checks["prev_hash_valid"] = False
                details.append(
                    f"Previous version {row['version_number']-1} not found"
                )

        # Check 3: Cross-check MongoDB if available
        checks["mongo_consistent"] = None
        if self.mongo_db is not None:
            try:
                mongo_doc = self.mongo_db.record_snapshots.find_one(
                    {"version_id": row["version_id"]}
                )
                if mongo_doc:
                    mongo_hash = mongo_doc.get("snapshot_hash")
                    mongo_canon = mongo_doc.get("canonical_snapshot")
                    checks["mongo_consistent"] = (
                        mongo_hash == row["snapshot_hash"]
                        and mongo_canon == stored_canon
                    )
                    if not checks["mongo_consistent"]:
                        details.append("MongoDB snapshot differs from PostgreSQL")
                else:
                    checks["mongo_consistent"] = False
                    details.append("MongoDB document not found for this version")
            except Exception as e:
                checks["mongo_consistent"] = None
                details.append(f"MongoDB check skipped: {e}")

        cur.close()

        all_valid = all(
            v is True for v in checks.values() if v is not None
        )
        return {
            "valid": all_valid,
            "checks": checks,
            "details": "; ".join(details) if details else "All checks passed",
        }

    def verify_chain(self, student_id: int) -> dict:
        """
        Verify the entire version chain for a student.

        Returns:
            {
                "valid": bool,
                "versions_checked": int,
                "first_failure": int or None,
                "details": str
            }
        """
        import psycopg2.extras

        cur = self.pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT version_id, version_number
            FROM record_version
            WHERE student_id = %s
            ORDER BY version_number
        """, (student_id,))
        versions = cur.fetchall()
        cur.close()

        if not versions:
            return {
                "valid": True,
                "versions_checked": 0,
                "first_failure": None,
                "details": "No versions found for student",
            }

        for v in versions:
            result = self.verify_version(v["version_id"])
            if not result["valid"]:
                return {
                    "valid": False,
                    "versions_checked": v["version_number"],
                    "first_failure": v["version_number"],
                    "details": result["details"],
                }

        return {
            "valid": True,
            "versions_checked": len(versions),
            "first_failure": None,
            "details": f"All {len(versions)} versions verified successfully",
        }

    def get_record(self, student_id: int, version_number: int = None) -> dict:
        """
        Retrieve a student's academic record snapshot.

        Args:
            student_id: The student's ID.
            version_number: Specific version, or None for latest.

        Returns:
            Dict with version metadata and parsed record.
        """
        import psycopg2.extras

        cur = self.pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if version_number:
            cur.execute("""
                SELECT version_id, student_id, version_number,
                       snapshot_hash, prev_hash, canonical_snapshot,
                       snapshot_scope, created_at
                FROM record_version
                WHERE student_id = %s AND version_number = %s
            """, (student_id, version_number))
        else:
            cur.execute("""
                SELECT version_id, student_id, version_number,
                       snapshot_hash, prev_hash, canonical_snapshot,
                       snapshot_scope, created_at
                FROM record_version
                WHERE student_id = %s
                ORDER BY version_number DESC
                LIMIT 1
            """, (student_id,))

        row = cur.fetchone()
        cur.close()

        if not row:
            return None

        result = dict(row)
        result["record"] = json.loads(row["canonical_snapshot"])
        # Convert created_at to string for JSON serialization
        if result.get("created_at"):
            result["created_at"] = result["created_at"].isoformat()
        return result
