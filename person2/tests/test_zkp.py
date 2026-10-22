"""
ZK-TemporalDB — Unit Tests: ZKP (Commitment Fallback)

These tests verify the commitment-based ZKP fallback.
They run WITHOUT Circom/snarkjs — pure Python.

If Circom+snarkjs are installed, additional tests for genuine Groth16
proofs would run (marked with @pytest.mark.genuine_zkp).

Test IDs:
    T10.1: Eligible CGPA → valid proof, eligible=True
    T10.2: Non-qualifying CGPA → valid proof, eligible=False
    T10.3: Altered commitment fails verification
    T10.4: Wrong blinding fails verification
    T10.5: Wrong CGPA in opening fails verification
    T10.6: Input validation (out of range, wrong type)
    T10.7: Scaled ↔ CGPA conversion
    T10.8: Private CGPA not in public proof
"""

import pytest
from person2.zkp import ZKPService, CGPA_SCALE, CGPA_MIN, CGPA_MAX


@pytest.fixture
def zkp_svc():
    return ZKPService()


# ── T10.1: Eligible CGPA ─────────────────────────────────────────────────────

class TestEligibleCGPA:
    def test_eligible_proof(self, zkp_svc):
        """T10.1a: CGPA 9.50 (950) >= threshold 8.00 (800) → eligible."""
        result = zkp_svc.generate_commitment_proof(950, 800)
        public = result["public_proof"]
        private = result["private_opening"]

        assert public["eligible"] is True
        assert public["threshold_scaled"] == 800
        assert public["commitment"] is not None

        # Verify with opening
        verify = zkp_svc.verify_commitment_proof(public, private)
        assert verify["valid"] is True
        assert verify["commitment_verified"] is True
        assert verify["eligibility_verified"] is True

    def test_exact_threshold(self, zkp_svc):
        """T10.1b: CGPA == threshold → eligible."""
        result = zkp_svc.generate_commitment_proof(800, 800)
        assert result["public_proof"]["eligible"] is True
        verify = zkp_svc.verify_commitment_proof(
            result["public_proof"], result["private_opening"]
        )
        assert verify["valid"] is True

    def test_max_cgpa(self, zkp_svc):
        """T10.1c: Maximum CGPA 10.00 (1000) → eligible."""
        result = zkp_svc.generate_commitment_proof(1000, 800)
        assert result["public_proof"]["eligible"] is True


# ── T10.2: Non-qualifying CGPA ───────────────────────────────────────────────

class TestNonQualifyingCGPA:
    def test_below_threshold(self, zkp_svc):
        """T10.2a: CGPA 7.50 (750) < threshold 8.00 (800) → not eligible."""
        result = zkp_svc.generate_commitment_proof(750, 800)
        public = result["public_proof"]
        private = result["private_opening"]

        assert public["eligible"] is False

        verify = zkp_svc.verify_commitment_proof(public, private)
        assert verify["valid"] is True  # Proof is structurally valid
        assert verify["eligibility_verified"] is True  # Claim is honest

    def test_one_below(self, zkp_svc):
        """T10.2b: CGPA 799 < threshold 800 → not eligible."""
        result = zkp_svc.generate_commitment_proof(799, 800)
        assert result["public_proof"]["eligible"] is False


# ── T10.3: Altered Proof ─────────────────────────────────────────────────────

class TestAlteredProof:
    def test_altered_commitment(self, zkp_svc):
        """T10.3a: Altered commitment fails verification."""
        result = zkp_svc.generate_commitment_proof(950, 800)
        public = result["public_proof"].copy()
        private = result["private_opening"]

        public["commitment"] = "0" * 64  # Tamper

        verify = zkp_svc.verify_commitment_proof(public, private)
        assert verify["valid"] is False
        assert verify["commitment_verified"] is False

    def test_altered_eligibility(self, zkp_svc):
        """T10.3b: Altered eligibility claim fails verification."""
        result = zkp_svc.generate_commitment_proof(750, 800)
        public = result["public_proof"].copy()
        private = result["private_opening"]

        public["eligible"] = True  # Lie about eligibility

        verify = zkp_svc.verify_commitment_proof(public, private)
        assert verify["valid"] is False
        assert verify["eligibility_verified"] is False


# ── T10.4: Wrong Blinding ────────────────────────────────────────────────────

class TestWrongBlinding:
    def test_wrong_blinding_fails(self, zkp_svc):
        """T10.4: Wrong blinding factor fails commitment verification."""
        result = zkp_svc.generate_commitment_proof(950, 800)
        public = result["public_proof"]
        fake_opening = {
            "cgpa_scaled": 950,
            "blinding": "0" * 64,  # Wrong blinding
        }

        verify = zkp_svc.verify_commitment_proof(public, fake_opening)
        assert verify["valid"] is False
        assert verify["commitment_verified"] is False


# ── T10.5: Wrong CGPA in Opening ─────────────────────────────────────────────

class TestWrongCGPA:
    def test_wrong_cgpa_fails(self, zkp_svc):
        """T10.5: Opening with wrong CGPA fails."""
        result = zkp_svc.generate_commitment_proof(950, 800)
        public = result["public_proof"]
        fake_opening = {
            "cgpa_scaled": 800,  # Wrong CGPA
            "blinding": result["private_opening"]["blinding"],
        }

        verify = zkp_svc.verify_commitment_proof(public, fake_opening)
        assert verify["valid"] is False
        assert verify["commitment_verified"] is False


# ── T10.6: Input Validation ──────────────────────────────────────────────────

class TestInputValidation:
    def test_cgpa_too_high(self, zkp_svc):
        """T10.6a: CGPA > 1000 raises ValueError."""
        with pytest.raises(ValueError):
            zkp_svc.generate_commitment_proof(1001, 800)

    def test_cgpa_negative(self, zkp_svc):
        """T10.6b: Negative CGPA raises ValueError."""
        with pytest.raises(ValueError):
            zkp_svc.generate_commitment_proof(-1, 800)

    def test_threshold_too_high(self, zkp_svc):
        """T10.6c: Threshold > 1000 raises ValueError."""
        with pytest.raises(ValueError):
            zkp_svc.generate_commitment_proof(950, 1001)

    def test_float_cgpa(self, zkp_svc):
        """T10.6d: Float CGPA raises TypeError."""
        with pytest.raises(TypeError):
            zkp_svc.generate_commitment_proof(9.5, 800)

    def test_string_cgpa(self, zkp_svc):
        """T10.6e: String CGPA raises TypeError."""
        with pytest.raises(TypeError):
            zkp_svc.generate_commitment_proof("950", 800)


# ── T10.7: Scale Conversion ──────────────────────────────────────────────────

class TestScaleConversion:
    def test_cgpa_to_scaled(self):
        """T10.7a: 9.50 → 950."""
        assert ZKPService.cgpa_to_scaled("9.50") == 950

    def test_cgpa_to_scaled_integer(self):
        """T10.7b: 10.00 → 1000."""
        assert ZKPService.cgpa_to_scaled("10.00") == 1000

    def test_scaled_to_cgpa(self):
        """T10.7c: 950 → '9.50'."""
        result = ZKPService.scaled_to_cgpa(950)
        assert result == "9.50" or result == "9.5"

    def test_roundtrip(self):
        """T10.7d: Roundtrip conversion."""
        from decimal import Decimal
        original = Decimal("8.75")
        scaled = ZKPService.cgpa_to_scaled(original)
        assert scaled == 875


# ── T10.8: Privacy ───────────────────────────────────────────────────────────

class TestPrivacy:
    def test_cgpa_not_in_public_proof(self, zkp_svc):
        """T10.8a: Private CGPA is NOT in the public proof."""
        result = zkp_svc.generate_commitment_proof(950, 800)
        public = result["public_proof"]

        # Ensure private CGPA does not appear in keys or non-commitment values
        assert "cgpa_scaled" not in public
        assert 950 not in public.values()
        public_without_commitment = {k: v for k, v in public.items() if k != "commitment"}
        assert "950" not in str(public_without_commitment)
        assert "9.50" not in str(public)

    def test_blinding_not_in_public(self, zkp_svc):
        """T10.8b: Blinding factor is NOT in the public proof."""
        result = zkp_svc.generate_commitment_proof(950, 800)
        blinding = result["private_opening"]["blinding"]
        public_str = str(result["public_proof"])

        assert blinding not in public_str

    def test_verify_without_opening_fails(self, zkp_svc):
        """T10.8c: Verification without opening cannot confirm the claim."""
        result = zkp_svc.generate_commitment_proof(950, 800)
        verify = zkp_svc.verify_commitment_proof(result["public_proof"])
        assert verify["valid"] is False
        assert "Cannot verify without private opening" in verify["details"]


# ── Toolchain Status ─────────────────────────────────────────────────────────

class TestToolchainStatus:
    def test_status_fields(self, zkp_svc):
        """Toolchain status has expected fields."""
        status = zkp_svc.get_toolchain_status()
        assert "circom_available" in status
        assert "snarkjs_available" in status
        assert "genuine_zkp" in status
        assert "fallback_mode" in status
        assert "proof_type" in status
