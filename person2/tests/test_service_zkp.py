"""
ZK-TemporalDB — AcademicRecordService ZKP Facade Tests

Tests for the AcademicRecordService facade's generate_zkp() and verify_zkp()
methods.  Two independent test groups:

  TestServiceZKPMocked  — pure-Python mocks; no PostgreSQL or toolchain needed.
    Covers proof-type detection, CGPA privacy, mode dispatch, and error paths.

  TestServiceZKPIntegration — requires a live PostgreSQL connection.
    Covers the full generate->verify round-trip through the facade.
    Auto-skipped when PG is unavailable.

Test IDs:
    SVC-ZKP-1  : generate_zkp() returns a dict that contains proof_type
    SVC-ZKP-2  : generate_zkp() never exposes cgpa_scaled at the top level
    SVC-ZKP-3  : generate_zkp() public_proof never exposes cgpa_scaled (fallback)
    SVC-ZKP-4  : generate_zkp() attaches student_id to the response
    SVC-ZKP-5  : generate_zkp() raises ValueError for unknown student
    SVC-ZKP-6  : verify_zkp() fallback round-trip returns valid=True
    SVC-ZKP-7  : verify_zkp() with tampered commitment returns valid=False
    SVC-ZKP-8  : verify_zkp() without private_opening returns valid=False (fallback)
    SVC-ZKP-9  : verify_zkp() genuine mode dispatches correctly (genuine only)
    SVC-ZKP-10 : verify_zkp() genuine round-trip returns valid=True (genuine only)
    SVC-ZKP-11 : PG integration -- generate_zkp() full round-trip
    SVC-ZKP-12 : PG integration -- generate_zkp() for eligible student
    SVC-ZKP-13 : PG integration -- student_id attached to response
    SVC-ZKP-14 : PG integration -- no cgpa_scaled leak
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_semester_row(sgpa, total_credits):
    """Return a psycopg2-RealDictRow-compatible dict."""
    return {"sgpa": Decimal(str(sgpa)), "total_credits": total_credits}


def _make_mock_pg_conn(rows):
    """
    Build a minimal mock psycopg2 connection whose cursor().fetchall()
    returns *rows* (list of dicts with 'sgpa' and 'total_credits').
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


# ── Mock-based tests (no PG / no toolchain required) ─────────────────────────

class TestServiceZKPMocked:
    """SVC-ZKP-1 to SVC-ZKP-10: Pure-mock tests for the service facade."""

    def _build_svc(self, rows, zkp_svc_override=None):
        """Construct AcademicRecordService wired to a mock PG connection."""
        from person2.services import AcademicRecordService
        conn, _cursor = _make_mock_pg_conn(rows)
        return AcademicRecordService(
            conn,
            mongo_db=None,
            zkp_service=zkp_svc_override,
            auto_commit=False,
        )

    def test_generate_zkp_returns_proof_type(self):
        """SVC-ZKP-1: generate_zkp() result contains proof_type (either mode)."""
        svc = self._build_svc([_make_semester_row(9.50, 22)])
        proof = svc.generate_zkp(student_id=1, threshold=8.00)
        proof_type = proof.get("proof_type") or proof.get("public_proof", {}).get("proof_type")
        assert proof_type in ("groth16_genuine", "commitment_fallback"), (
            f"Unexpected proof_type: {proof_type!r}"
        )

    def test_generate_zkp_no_cgpa_at_top_level(self):
        """SVC-ZKP-2: The private CGPA is not a top-level key."""
        svc = self._build_svc([_make_semester_row(9.50, 22)])
        proof = svc.generate_zkp(student_id=1, threshold=8.00)
        assert "cgpa_scaled" not in proof, (
            "Private cgpa_scaled must not appear as a top-level key"
        )
        assert "cgpa" not in proof, (
            "Private cgpa must not appear as a top-level key"
        )

    def test_generate_zkp_no_cgpa_in_public_proof(self):
        """SVC-ZKP-3: In fallback mode, public_proof must not expose cgpa_scaled."""
        from person2.zkp import ZKPService
        if ZKPService().genuine_zkp:
            pytest.skip("Genuine ZKP active -- this test covers fallback mode only")
        svc = self._build_svc([_make_semester_row(9.50, 22)])
        proof = svc.generate_zkp(student_id=1, threshold=8.00)
        assert "public_proof" in proof, "Fallback mode must return public_proof key"
        pub = proof["public_proof"]
        assert "cgpa_scaled" not in pub
        assert "cgpa" not in pub

    def test_generate_zkp_attaches_student_id(self):
        """SVC-ZKP-4: generate_zkp() attaches student_id to the response."""
        svc = self._build_svc([_make_semester_row(9.50, 22)])
        proof = svc.generate_zkp(student_id=42, threshold=8.00)
        if "public_proof" in proof:
            assert proof["public_proof"].get("student_id") == 42
        else:
            assert proof.get("student_id") == 42

    def test_generate_zkp_raises_for_unknown_student(self):
        """SVC-ZKP-5: generate_zkp() raises ValueError when no results found."""
        svc = self._build_svc([])
        with pytest.raises(ValueError, match="No semester results"):
            svc.generate_zkp(student_id=9999, threshold=8.00)

    def test_verify_zkp_fallback_roundtrip_valid(self):
        """SVC-ZKP-6: Fallback generate->verify with opening returns valid=True."""
        from person2.zkp import ZKPService
        if ZKPService().genuine_zkp:
            pytest.skip("Genuine ZKP active -- this test covers fallback only")
        svc = self._build_svc([_make_semester_row(9.50, 22)])
        proof = svc.generate_zkp(student_id=1, threshold=8.00)
        result = svc.verify_zkp(
            proof["public_proof"],
            private_opening=proof["private_opening"],
        )
        assert result["valid"] is True
        assert result["eligible"] is True

    def test_verify_zkp_tampered_commitment_rejected(self):
        """SVC-ZKP-7: Tampered commitment returns valid=False."""
        from person2.zkp import ZKPService
        if ZKPService().genuine_zkp:
            pytest.skip("Genuine ZKP active -- this test covers fallback only")
        svc = self._build_svc([_make_semester_row(9.50, 22)])
        proof = svc.generate_zkp(student_id=1, threshold=8.00)
        tampered_pub = dict(proof["public_proof"])
        tampered_pub["commitment"] = "0" * 64
        result = svc.verify_zkp(
            tampered_pub,
            private_opening=proof["private_opening"],
        )
        assert result["valid"] is False

    def test_verify_zkp_without_opening_fails(self):
        """SVC-ZKP-8: Fallback verify without private_opening returns valid=False."""
        from person2.zkp import ZKPService
        if ZKPService().genuine_zkp:
            pytest.skip("Genuine ZKP active -- this test covers fallback only")
        svc = self._build_svc([_make_semester_row(9.50, 22)])
        proof = svc.generate_zkp(student_id=1, threshold=8.00)
        result = svc.verify_zkp(proof["public_proof"])
        assert result["valid"] is False

    def test_verify_zkp_genuine_dispatch(self):
        """SVC-ZKP-9: verify_zkp dispatches to genuine verifier for groth16_genuine."""
        from person2.zkp import ZKPService
        from pathlib import Path
        zkp = ZKPService()
        if not zkp.genuine_zkp:
            pytest.skip("Genuine ZKP toolchain not available")
        vkey = Path(zkp.work_dir) / "verification_key.json"
        if not vkey.exists():
            pytest.skip("Circuit not set up -- run ZKPService().setup_circuit() first")
        svc = self._build_svc([_make_semester_row(9.50, 22)])
        proof = svc.generate_zkp(student_id=1, threshold=8.00)
        assert proof.get("proof_type") == "groth16_genuine"
        result = svc.verify_zkp(proof)
        assert result["valid"] is True

    def test_verify_zkp_genuine_roundtrip(self):
        """SVC-ZKP-10: Genuine generate->verify returns valid=True."""
        from person2.zkp import ZKPService
        from pathlib import Path
        zkp = ZKPService()
        if not zkp.genuine_zkp:
            pytest.skip("Genuine ZKP toolchain not available")
        vkey = Path(zkp.work_dir) / "verification_key.json"
        if not vkey.exists():
            pytest.skip("Circuit not set up -- run ZKPService().setup_circuit() first")
        svc = self._build_svc([_make_semester_row(9.50, 22)])
        proof = svc.generate_zkp(student_id=1, threshold=8.00)
        result = svc.verify_zkp(proof)
        assert result["valid"] is True
        assert result["eligible"] is True

    def test_generate_zkp_ineligible_student(self):
        """SVC-ZKP-1b: generate_zkp() works for a student below the threshold."""
        from person2.zkp import ZKPService
        if ZKPService().genuine_zkp:
            pytest.skip("Skipping ineligible mock test in genuine mode (circuit call)")
        svc = self._build_svc([_make_semester_row(7.50, 22)])
        proof = svc.generate_zkp(student_id=2, threshold=8.00)
        eligible = (
            proof.get("eligible")
            if "eligible" in proof
            else proof.get("public_proof", {}).get("eligible")
        )
        assert eligible in (False, 0), (
            f"Ineligible student should get eligible=False/0, got {eligible!r}"
        )

    def test_generate_zkp_multi_semester_weighted_cgpa(self):
        """SVC-ZKP-1c: Weighted CGPA across semesters is computed correctly.

        Weighted: (8.0*20 + 9.0*22) / 42 = 358/42 ~= 8.52 -> scaled 852 >= 800 -> eligible
        """
        from person2.zkp import ZKPService
        if ZKPService().genuine_zkp:
            pytest.skip("Skipping mock test in genuine mode")
        rows = [
            _make_semester_row(8.0, 20),
            _make_semester_row(9.0, 22),
        ]
        svc = self._build_svc(rows)
        proof = svc.generate_zkp(student_id=1, threshold=8.00)
        eligible = (
            proof.get("eligible")
            if "eligible" in proof
            else proof.get("public_proof", {}).get("eligible")
        )
        assert eligible in (True, 1), (
            f"Weighted CGPA ~8.52 should be eligible, got {eligible!r}"
        )

    def test_verify_zkp_accepts_full_generate_dict(self):
        """SVC-ZKP: verify_zkp(full_proof_dict) works without manually unpacking."""
        from person2.zkp import ZKPService
        if ZKPService().genuine_zkp:
            pytest.skip("Genuine ZKP active -- this test covers fallback only")
        svc = self._build_svc([_make_semester_row(9.50, 22)])
        proof = svc.generate_zkp(student_id=1, threshold=8.00)
        # verify_threshold_proof sees 'public_proof' key and dispatches correctly
        result = svc.verify_zkp(
            proof,
            private_opening=proof.get("private_opening"),
        )
        assert result["valid"] is True


# ── PostgreSQL integration tests ──────────────────────────────────────────────

def _pg_available():
    try:
        from person2.db import get_pg_connection
        conn = get_pg_connection()
        conn.close()
        return True
    except Exception:
        return False


_PG_AVAILABLE = _pg_available()


@pytest.fixture(scope="session")
def _shared_zkp_svc():
    """
    Session-scoped ZKPService shared across all PG integration tests.

    Reusing one instance avoids a macOS APFS rapid create-delete-create race:
    each generate_genuine_proof call writes then deletes build/input.json.
    With separate ZKPService instances per test the filesystem may not flush
    the directory entry fast enough for the next Node.js subprocess.
    """
    from person2.zkp import ZKPService
    return ZKPService()


@pytest.fixture
def pg_conn():
    """Provide a PG connection that rolls back all changes after the test."""
    if not _PG_AVAILABLE:
        pytest.skip("PostgreSQL not available")
    from person2.db import get_pg_connection
    conn = get_pg_connection()
    conn.rollback()

    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(version_id), 0) FROM record_version")
    init_max_vid = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(MAX(batch_id), 0) FROM merkle_batch")
    init_max_bid = cur.fetchone()[0]
    cur.close()

    yield conn

    try:
        conn.rollback()
    except Exception:
        pass
    try:
        cur = conn.cursor()
        cur.execute(
            "ALTER TABLE merkle_batch_member"
            " DISABLE TRIGGER trg_deny_modify_merkle_batch_member"
        )
        cur.execute(
            "ALTER TABLE merkle_batch"
            " DISABLE TRIGGER trg_deny_modify_merkle_batch"
        )
        cur.execute(
            "ALTER TABLE record_version"
            " DISABLE TRIGGER trg_deny_modify_record_version"
        )
        cur.execute(
            "DELETE FROM merkle_batch_member"
            " WHERE batch_id > %s OR version_id > %s",
            (init_max_bid, init_max_vid),
        )
        cur.execute(
            "DELETE FROM merkle_batch WHERE batch_id > %s",
            (init_max_bid,),
        )
        cur.execute(
            "DELETE FROM record_version WHERE version_id > %s",
            (init_max_vid,),
        )
        cur.execute(
            "ALTER TABLE record_version"
            " ENABLE TRIGGER trg_deny_modify_record_version"
        )
        cur.execute(
            "ALTER TABLE merkle_batch"
            " ENABLE TRIGGER trg_deny_modify_merkle_batch"
        )
        cur.execute(
            "ALTER TABLE merkle_batch_member"
            " ENABLE TRIGGER trg_deny_modify_merkle_batch_member"
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cur.close()
        conn.close()


@pytest.fixture
def facade_svc(pg_conn, _shared_zkp_svc):
    """AcademicRecordService wired to the test PG connection."""
    from person2.services import AcademicRecordService
    return AcademicRecordService(
        pg_conn, mongo_db=None, zkp_service=_shared_zkp_svc, auto_commit=False
    )


@pytest.mark.skipif(not _PG_AVAILABLE, reason="PostgreSQL not available")
class TestServiceZKPIntegration:
    """SVC-ZKP-11 to 14: Full round-trip through the facade with live PG."""

    def test_generate_zkp_full_roundtrip(self, facade_svc):
        """SVC-ZKP-11: generate_zkp() -> verify_zkp() round-trip via the facade."""
        proof = facade_svc.generate_zkp(student_id=1, threshold=8.00)
        proof_type = (
            proof.get("proof_type")
            or proof.get("public_proof", {}).get("proof_type")
        )
        assert proof_type in ("groth16_genuine", "commitment_fallback")
        if proof_type == "groth16_genuine":
            result = facade_svc.verify_zkp(proof)
        else:
            result = facade_svc.verify_zkp(
                proof["public_proof"],
                private_opening=proof["private_opening"],
            )
        assert result["valid"] is True

    def test_generate_zkp_eligible_student(self, facade_svc):
        """SVC-ZKP-12: Student 1 (seed CGPA >= 8.00) is eligible."""
        proof = facade_svc.generate_zkp(student_id=1, threshold=8.00)
        eligible = (
            proof.get("eligible")
            if "eligible" in proof
            else proof.get("public_proof", {}).get("eligible")
        )
        assert eligible in (True, 1), (
            f"Student 1 should be eligible for threshold 8.00, got {eligible!r}"
        )

    def test_generate_zkp_student_id_attached(self, facade_svc):
        """SVC-ZKP-13: generate_zkp() attaches the correct student_id."""
        proof = facade_svc.generate_zkp(student_id=1, threshold=8.00)
        if "public_proof" in proof:
            sid = proof["public_proof"].get("student_id")
        else:
            sid = proof.get("student_id")
        assert sid == 1

    def test_generate_zkp_no_cgpa_leak_pg(self, facade_svc):
        """SVC-ZKP-14: Live PG: generate_zkp() does not expose cgpa_scaled."""
        proof = facade_svc.generate_zkp(student_id=1, threshold=8.00)
        assert "cgpa_scaled" not in proof
        if "public_proof" in proof:
            assert "cgpa_scaled" not in proof["public_proof"]
