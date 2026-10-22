"""
ZK-TemporalDB — High-Level Integration Services

Provides a unified Python API for Person 3's application layer.
All methods return plain dicts suitable for JSON serialization.

This module is the integration interface. Person 3 should call these
functions from their application backend rather than importing the
lower-level modules directly.

Usage:
    from person2.services import AcademicRecordService
    svc = AcademicRecordService.from_env()
    record = svc.get_record(student_id=1)
    version = svc.create_version(student_id=1)
    verify = svc.verify_version(version_id=1)
    batch = svc.create_merkle_batch([1, 2, 3])
    inclusion = svc.verify_merkle_inclusion(batch_id=1, version_id=1)
    proof = svc.generate_zkp(student_id=1, threshold=8.00)
    valid = svc.verify_zkp(proof)
"""

import json
import logging
from decimal import Decimal
from typing import Optional

from person2.db import get_pg_connection, get_mongo_db, check_pg, check_mongo
from person2.versioning import RecordVersionService, build_academic_record
from person2.merkle import MerkleBatchService, MerkleTree
from person2.zkp import ZKPService
from person2.canonical import canonicalize, canonical_hash, verify_hash

logger = logging.getLogger(__name__)


class AcademicRecordService:
    """
    Unified service facade for Person 3.

    Wraps versioning, Merkle trees, and ZKP functionality
    into a clean, documented API.
    """

    def __init__(self, pg_conn, mongo_db=None, zkp_service=None, auto_commit: bool = True):
        """
        Args:
            pg_conn: psycopg2 connection to PostgreSQL.
            mongo_db: pymongo Database object (optional).
            zkp_service: ZKPService instance (optional, created lazily).
            auto_commit: Whether child services auto-commit (default True).
        """
        self.pg_conn = pg_conn
        self.mongo_db = mongo_db
        self.auto_commit = auto_commit
        self.version_svc = RecordVersionService(pg_conn, mongo_db, auto_commit=auto_commit)
        self.merkle_svc = MerkleBatchService(pg_conn, mongo_db, auto_commit=auto_commit)
        self._zkp_svc = zkp_service

    @classmethod
    def from_env(cls, require_mongo: bool = False):
        """
        Create a service instance using environment variables.

        Args:
            require_mongo: If True, raises if MongoDB is unavailable.

        Returns:
            AcademicRecordService instance.
        """
        pg_conn = get_pg_connection()
        mongo_db = None
        try:
            mongo_db = get_mongo_db()
        except Exception as e:
            if require_mongo:
                raise
            logger.warning("MongoDB not available: %s. Running PG-only.", e)
        return cls(pg_conn, mongo_db)

    @property
    def zkp_svc(self):
        if self._zkp_svc is None:
            self._zkp_svc = ZKPService()
        return self._zkp_svc

    # ── Health ────────────────────────────────────────────────────────────────

    def health_check(self) -> dict:
        """
        Check connectivity to all backend services.

        Returns:
            {
                "postgresql": { "status": "ok"|"error", ... },
                "mongodb": { "status": "ok"|"error"|"not_configured", ... },
                "zkp_toolchain": { "genuine_zkp": bool, ... }
            }
        """
        result = {
            "postgresql": check_pg(),
            "mongodb": (
                check_mongo() if self.mongo_db
                else {"status": "not_configured"}
            ),
            "zkp_toolchain": self.zkp_svc.get_toolchain_status(),
        }
        return result

    # ── Record Retrieval ──────────────────────────────────────────────────────

    def get_record(
        self,
        student_id: int,
        version_number: int = None
    ) -> dict:
        """
        Retrieve a student's academic record.

        Args:
            student_id: The student's ID.
            version_number: Specific version (None = latest, 0 = live from PG).

        Returns:
            Dict with version info and record data, or None.

        API: GET /api/records/{student_id}?version={version_number}
        """
        if version_number == 0:
            # Fetch live data directly from PostgreSQL (not a stored version)
            record = build_academic_record(self.pg_conn, student_id)
            return {
                "student_id": student_id,
                "version_number": 0,
                "source": "live_postgresql",
                "record": json.loads(canonicalize(record)),
                "snapshot_hash": canonical_hash(record),
            }

        return self.version_svc.get_record(student_id, version_number)

    # ── Versioning ────────────────────────────────────────────────────────────

    def create_version(self, student_id: int) -> dict:
        """
        Create a new versioned snapshot of a student's academic record.

        Fetches the current record from PostgreSQL, canonicalizes it,
        computes SHA-256 hash, and stores with prev_hash link.

        Args:
            student_id: The student's ID.

        Returns:
            Version metadata dict with version_id, hash, version_number.

        API: POST /api/records/{student_id}/versions
        """
        return self.version_svc.create_version(student_id)

    def verify_version(self, version_id: int) -> dict:
        """
        Verify a stored version's hash and chain integrity.

        Checks:
            - Recomputed hash matches stored hash
            - prev_hash matches previous version's hash
            - MongoDB copy matches PostgreSQL (if available)

        Args:
            version_id: The version to verify.

        Returns:
            { "valid": bool, "checks": {...}, "details": str }

        API: GET /api/versions/{version_id}/verify
        """
        return self.version_svc.verify_version(version_id)

    def verify_chain(self, student_id: int) -> dict:
        """
        Verify the entire version chain for a student.

        API: GET /api/records/{student_id}/verify-chain
        """
        return self.version_svc.verify_chain(student_id)

    # ── Merkle Batches ────────────────────────────────────────────────────────

    def create_merkle_batch(
        self,
        version_ids: list[int],
        description: str = None
    ) -> dict:
        """
        Create a Merkle batch from record version IDs.

        Args:
            version_ids: List of version_id values.
            description: Optional batch description.

        Returns:
            { "batch_id": int, "merkle_root": str, "leaf_count": int, ... }

        API: POST /api/merkle/batches
             Body: { "version_ids": [1, 2, 3], "description": "..." }
        """
        return self.merkle_svc.create_batch(version_ids, description)

    def verify_merkle_inclusion(
        self,
        batch_id: int,
        version_id: int
    ) -> dict:
        """
        Verify a record version's inclusion in a Merkle batch.

        Args:
            batch_id: The Merkle batch ID.
            version_id: The version to verify.

        Returns:
            { "valid": bool, "details": str }

        API: GET /api/merkle/batches/{batch_id}/verify/{version_id}
        """
        return self.merkle_svc.verify_inclusion(batch_id, version_id)

    # ── Zero-Knowledge Proofs ─────────────────────────────────────────────────

    def generate_zkp(
        self,
        student_id: int,
        threshold: float = 8.00,
    ) -> dict:
        """
        Generate a ZKP proving a student's CGPA meets a threshold.

        The student's exact CGPA is NEVER included in the returned proof.
        Only the threshold and eligibility result are public.

        Args:
            student_id: The student's ID.
            threshold: Minimum CGPA threshold (e.g., 8.00).

        Returns:
            Dict with proof data (public) and private opening (separate).
            The private opening must be stored securely and NOT shared
            unless the student consents to reveal their CGPA.

        API: POST /api/zkp/generate
             Body: { "student_id": 1, "threshold": 8.00 }
             Response: { "public_proof": {...}, "private_opening": {...} }
        """
        import psycopg2.extras

        # Compute CGPA from semester results
        cur = self.pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT sr.sgpa, sr.total_credits
            FROM semester_result sr
            WHERE sr.student_id = %s
            ORDER BY sr.sem_no
        """, (student_id,))
        results = cur.fetchall()
        cur.close()

        if not results:
            raise ValueError(
                f"No semester results found for student {student_id}"
            )

        # Compute weighted CGPA
        total_weighted = sum(
            r["sgpa"] * r["total_credits"] for r in results
        )
        total_credits = sum(r["total_credits"] for r in results)
        cgpa = total_weighted / Decimal(total_credits)

        # Convert to scaled integer
        cgpa_scaled = self.zkp_svc.cgpa_to_scaled(cgpa)
        threshold_scaled = self.zkp_svc.cgpa_to_scaled(threshold)

        proof = self.zkp_svc.generate_threshold_proof(
            cgpa_scaled, threshold_scaled
        )

        # Add student context (without revealing CGPA)
        if "public_proof" in proof:
            proof["public_proof"]["student_id"] = student_id
        else:
            proof["student_id"] = student_id

        return proof

    def verify_zkp(
        self,
        proof_data: dict,
        private_opening: dict = None
    ) -> dict:
        """
        Verify a ZKP threshold proof.

        Without private_opening: verifies proof structure only (commitment).
        With private_opening: fully verifies the claim (reveals CGPA).

        Args:
            proof_data: The public proof from generate_zkp.
            private_opening: Optional opening for full verification.

        Returns:
            { "valid": bool, "eligible": bool, "details": str }

        API: POST /api/zkp/verify
             Body: { "proof": {...}, "private_opening": {...} }
        """
        return self.zkp_svc.verify_threshold_proof(
            proof_data, private_opening
        )

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def close(self):
        """Close database connections."""
        try:
            self.pg_conn.close()
        except Exception:
            pass
        from person2.db import close_mongo
        close_mongo()
