"""
ZK-TemporalDB -- Genuine ZKP Tests (Groth16 / Circom + snarkjs)

Tests A: Exercise the actual Circom/snarkjs toolchain end-to-end.

These tests require:
  - circom2 or circom installed (system PATH or person2/node_modules/.bin/)
  - snarkjs installed (system PATH or person2/node_modules/.bin/)
  - A compiled circuit + trusted-setup artifacts in person2/circuits/build/

If the toolchain is not available, all genuine ZKP tests are skipped and
the test file reports the reason clearly.

Test IDs:
    ZKP-1: Toolchain discovery -- circom2 and snarkjs found locally
    ZKP-2: Eligible CGPA (9.50 >= 8.00) proof generates and verifies OK
    ZKP-3: Ineligible CGPA (7.50 < 8.00) proof generates; eligible=0
    ZKP-4: Exact threshold (8.00 == 8.00) treated as eligible
    ZKP-5: Tampered proof rejected by snarkjs verifier
    ZKP-6: Tampered public signals rejected (proof/signal mismatch)
    ZKP-7: generate_threshold_proof uses genuine path when available
    ZKP-8: verify_threshold_proof dispatches to genuine verifier
    ZKP-9: Private input (cgpa_scaled) is never included in proof output
"""

import pytest
from person2.zkp import ZKPService


# -- Availability check -------------------------------------------------------

_svc_probe = ZKPService()
GENUINE_AVAILABLE = _svc_probe.genuine_zkp
GENUINE_REASON = (
    "Circom/snarkjs available"
    if GENUINE_AVAILABLE
    else (
        f"circom={'found' if _svc_probe.has_circom else 'NOT FOUND'}, "
        f"snarkjs={'found' if _svc_probe.has_snarkjs else 'NOT FOUND'}. "
        f"Genuine ZKP tests skipped; commitment fallback used."
    )
)
# Also check if setup artifacts exist (verification_key.json)
from pathlib import Path
_build_dir = Path(__file__).parent.parent / "circuits" / "build"
SETUP_DONE = (_build_dir / "verification_key.json").exists()

genuine_skip = pytest.mark.skipif(
    not (GENUINE_AVAILABLE and SETUP_DONE),
    reason=(
        f"Genuine ZKP toolchain not available or setup not done. "
        f"Toolchain: {GENUINE_REASON}. "
        f"Setup artifacts present: {SETUP_DONE}"
    )
)


# -- ZKP-1: Toolchain discovery -----------------------------------------------

class TestToolchainDiscovery:
    """ZKP-1: Verify binary discovery resolves local node_modules."""

    def test_get_toolchain_status_has_required_keys(self):
        """ZKP-1.1: get_toolchain_status() contains all expected fields."""
        svc = ZKPService()
        status = svc.get_toolchain_status()
        assert "circom_available" in status
        assert "snarkjs_available" in status
        assert "genuine_zkp" in status
        assert "fallback_mode" in status
        assert "proof_type" in status
        assert "circom_path" in status
        assert "snarkjs_path" in status

    @genuine_skip
    def test_genuine_zkp_flag_is_true(self):
        """ZKP-1.2: genuine_zkp=True when both tools are available."""
        svc = ZKPService()
        status = svc.get_toolchain_status()
        assert status["genuine_zkp"] is True
        assert status["fallback_mode"] is False
        assert status["proof_type"] == "groth16_genuine"

    @genuine_skip
    def test_binary_paths_are_non_none(self):
        """ZKP-1.3: Resolved binary paths are non-None strings."""
        svc = ZKPService()
        status = svc.get_toolchain_status()
        assert status["circom_path"] is not None
        assert status["snarkjs_path"] is not None
        assert isinstance(status["circom_path"], str)
        assert isinstance(status["snarkjs_path"], str)

    @genuine_skip
    def test_binaries_are_executable(self):
        """ZKP-1.4: Resolved binaries pass os.access executable check."""
        import os
        svc = ZKPService()
        status = svc.get_toolchain_status()
        assert os.access(status["circom_path"], os.X_OK), (
            f"circom binary not executable: {status['circom_path']}"
        )
        assert os.access(status["snarkjs_path"], os.X_OK), (
            f"snarkjs binary not executable: {status['snarkjs_path']}"
        )


# -- ZKP-2: Eligible CGPA proof -----------------------------------------------

class TestEligibleCGPAGenuine:
    """ZKP-2: CGPA 9.50 >= threshold 8.00 -- eligible proof."""

    @genuine_skip
    def test_eligible_proof_generates(self):
        """ZKP-2.1: generate_genuine_proof returns proof with correct structure."""
        svc = ZKPService()
        result = svc.generate_genuine_proof(cgpa_scaled=950, threshold_scaled=800)
        assert result["proof_type"] == "groth16_genuine"
        assert "proof" in result
        assert "public_signals" in result
        # Groth16 proof has pi_a, pi_b, pi_c
        assert "pi_a" in result["proof"]
        assert "pi_b" in result["proof"]
        assert "pi_c" in result["proof"]

    @genuine_skip
    def test_eligible_public_signals(self):
        """ZKP-2.2: Public signals: [eligible=1, threshold=800]."""
        svc = ZKPService()
        result = svc.generate_genuine_proof(cgpa_scaled=950, threshold_scaled=800)
        # public_signals[0] == "1" means eligible
        assert result["public_signals"][0] == "1", (
            f"Expected eligible=1, got public_signals={result['public_signals']}"
        )
        # public_signals[1] == threshold scaled
        assert result["public_signals"][1] == "800"

    @genuine_skip
    def test_eligible_proof_verifies(self):
        """ZKP-2.3: snarkjs groth16 verify accepts the eligible proof."""
        svc = ZKPService()
        proof_data = svc.generate_genuine_proof(cgpa_scaled=950, threshold_scaled=800)
        result = svc.verify_genuine_proof(proof_data)
        assert result["valid"] is True, (
            f"Proof verification failed: {result.get('details')}"
        )
        assert result["eligible"] is True

    @genuine_skip
    def test_eligible_metadata(self):
        """ZKP-2.4: Proof metadata records circuit and curve correctly."""
        svc = ZKPService()
        result = svc.generate_genuine_proof(cgpa_scaled=950, threshold_scaled=800)
        meta = result["metadata"]
        assert meta["circuit"] == "cgpa_threshold.circom"
        assert meta["curve"] == "bn128"
        assert "TEST_ONLY" in meta["trusted_setup"]


# -- ZKP-3: Ineligible CGPA proof ---------------------------------------------

class TestIneligibleCGPAGenuine:
    """ZKP-3: CGPA 7.50 < threshold 8.00 -- ineligible proof."""

    @genuine_skip
    def test_ineligible_proof_generates(self):
        """ZKP-3.1: generate_genuine_proof works for ineligible CGPA."""
        svc = ZKPService()
        result = svc.generate_genuine_proof(cgpa_scaled=750, threshold_scaled=800)
        assert result["proof_type"] == "groth16_genuine"

    @genuine_skip
    def test_ineligible_public_signals(self):
        """ZKP-3.2: Public signals: [eligible=0, threshold=800]."""
        svc = ZKPService()
        result = svc.generate_genuine_proof(cgpa_scaled=750, threshold_scaled=800)
        assert result["public_signals"][0] == "0", (
            f"Expected eligible=0 for CGPA 7.50 < 8.00, "
            f"got public_signals={result['public_signals']}"
        )

    @genuine_skip
    def test_ineligible_proof_is_cryptographically_valid(self):
        """ZKP-3.3: The ineligible proof is a VALID proof (proves cgpa < threshold).

        The proof itself is cryptographically correct -- it proves that the
        student's CGPA does not meet the threshold (eligible=0).
        """
        svc = ZKPService()
        proof_data = svc.generate_genuine_proof(cgpa_scaled=750, threshold_scaled=800)
        result = svc.verify_genuine_proof(proof_data)
        assert result["valid"] is True, (
            "Ineligible proof should be cryptographically valid (just shows ineligible)"
        )
        assert result["eligible"] is False


# -- ZKP-4: Exact threshold ---------------------------------------------------

class TestExactThresholdGenuine:
    """ZKP-4: CGPA exactly at threshold (8.00 == 8.00)."""

    @genuine_skip
    def test_exact_threshold_is_eligible(self):
        """ZKP-4.1: cgpa == threshold satisfies cgpa >= threshold (eligible=1)."""
        svc = ZKPService()
        result = svc.generate_genuine_proof(cgpa_scaled=800, threshold_scaled=800)
        assert result["public_signals"][0] == "1", (
            "CGPA exactly at threshold should be eligible (>=)"
        )
        verify = svc.verify_genuine_proof(result)
        assert verify["valid"] is True
        assert verify["eligible"] is True


# -- ZKP-5: Tampered proof rejection ------------------------------------------

class TestTamperedProofGenuine:
    """ZKP-5: Tampered Groth16 proof is rejected by the verifier."""

    @genuine_skip
    def test_tampered_pi_a_rejected(self):
        """ZKP-5.1: Modifying pi_a[0] causes snarkjs to reject the proof."""
        svc = ZKPService()
        proof_data = svc.generate_genuine_proof(cgpa_scaled=950, threshold_scaled=800)

        # Tamper: replace pi_a[0] with a different field element
        tampered = dict(proof_data)
        tampered["proof"] = dict(proof_data["proof"])
        tampered["proof"]["pi_a"] = list(proof_data["proof"]["pi_a"])
        tampered["proof"]["pi_a"][0] = "12345678901234567890"

        result = svc.verify_genuine_proof(tampered)
        assert result["valid"] is False, (
            "Tampered proof (modified pi_a[0]) should be rejected by snarkjs"
        )

    @genuine_skip
    def test_tampered_pi_c_rejected(self):
        """ZKP-5.2: Modifying pi_c[1] causes snarkjs to reject the proof."""
        svc = ZKPService()
        proof_data = svc.generate_genuine_proof(cgpa_scaled=950, threshold_scaled=800)

        tampered = dict(proof_data)
        tampered["proof"] = dict(proof_data["proof"])
        tampered["proof"]["pi_c"] = list(proof_data["proof"]["pi_c"])
        tampered["proof"]["pi_c"][1] = "99999999999999999999"

        result = svc.verify_genuine_proof(tampered)
        assert result["valid"] is False, (
            "Tampered proof (modified pi_c[1]) should be rejected"
        )


# -- ZKP-6: Tampered public signals -------------------------------------------

class TestTamperedPublicSignalsGenuine:
    """ZKP-6: Proof verified against wrong public signals is rejected."""

    @genuine_skip
    def test_eligible_proof_vs_ineligible_signals_rejected(self):
        """ZKP-6.1: Eligible proof fails if public signals claim ineligible.

        The cryptographic binding: proof is tied to specific public signals.
        Swapping signals breaks the pairing check.
        """
        svc = ZKPService()
        eligible_proof = svc.generate_genuine_proof(cgpa_scaled=950, threshold_scaled=800)

        # Try to verify the eligible proof with signals claiming ineligible
        tampered = dict(eligible_proof)
        tampered["public_signals"] = ["0", "800"]  # Lie: claim not eligible

        result = svc.verify_genuine_proof(tampered)
        assert result["valid"] is False, (
            "Eligible proof should fail if public signals are tampered to show ineligible"
        )


# -- ZKP-7: generate_threshold_proof dispatches to genuine --------------------

class TestDispatchGenuine:
    """ZKP-7: generate_threshold_proof routes to genuine path when available."""

    @genuine_skip
    def test_threshold_proof_is_genuine_type(self):
        """ZKP-7.1: generate_threshold_proof returns groth16_genuine type."""
        svc = ZKPService()
        proof = svc.generate_threshold_proof(cgpa_scaled=950, threshold_scaled=800)
        assert proof.get("proof_type") == "groth16_genuine", (
            f"Expected groth16_genuine, got: {proof.get('proof_type')}"
        )

    @genuine_skip
    def test_verify_threshold_dispatches_to_genuine(self):
        """ZKP-8: verify_threshold_proof uses genuine verifier for groth16_genuine."""
        svc = ZKPService()
        proof = svc.generate_threshold_proof(cgpa_scaled=950, threshold_scaled=800)
        result = svc.verify_threshold_proof(proof)
        assert result["valid"] is True


# -- ZKP-9: Privacy -- CGPA not in proof output -------------------------------

class TestPrivacyGenuine:
    """ZKP-9: Private input (cgpa_scaled) is never exposed in genuine proof output."""

    @genuine_skip
    def test_cgpa_not_in_response_structure(self):
        """ZKP-9.1: Private cgpa_scaled is absent from all observable response fields.

        The Groth16 proof consists of BN128 elliptic-curve coordinates, which are
        ~77-digit decimal strings chosen by the zkSNARK prover.  Any 3-digit
        substring (like "950") can appear by coincidence in those numbers, so
        scanning str(proof) for "950" is not a reliable privacy test.

        Instead we check the surfaces that *could* actually leak the CGPA:
          - The top-level response dict must not have a "cgpa_scaled" key.
          - The public signals list must contain exactly [eligible, threshold];
            the private CGPA must not appear as a signal value.
          - The metadata dict must not contain the raw CGPA value.
        """
        svc = ZKPService()
        result = svc.generate_genuine_proof(cgpa_scaled=950, threshold_scaled=800)

        # 1. No explicit CGPA key anywhere in the top-level response
        assert "cgpa_scaled" not in result, (
            "Private cgpa_scaled must not be a top-level key in the proof response"
        )
        assert "cgpa" not in result, (
            "Private cgpa must not be a top-level key in the proof response"
        )

        # 2. Public signals must not expose the private CGPA (950).
        #    Signals are [eligible (0 or 1), threshold_scaled (800)].
        #    Neither should equal the private input.
        for i, sig in enumerate(result["public_signals"]):
            assert str(sig) != "950", (
                f"Private cgpa_scaled=950 appeared as public_signals[{i}]={sig!r}"
            )

        # 3. Metadata must not carry the raw CGPA
        meta = result.get("metadata", {})
        assert "cgpa_scaled" not in meta, (
            "Private cgpa_scaled must not appear in proof metadata"
        )

        # 4. The top-level "eligible" flag is a boolean — not the raw CGPA
        eligible_val = result.get("eligible")
        assert eligible_val in (0, 1, True, False), (
            f"Unexpected eligible value: {eligible_val!r}"
        )

        # The signals should only contain [eligible, threshold] -- not cgpa
        signals_str = str(result["public_signals"])
        assert "950" not in signals_str, (
            "Private cgpa_scaled=950 appeared in public signals"
        )

    @genuine_skip
    def test_only_two_public_signals(self):
        """ZKP-9.2: Exactly 2 public signals: [eligible, threshold]."""
        svc = ZKPService()
        result = svc.generate_genuine_proof(cgpa_scaled=950, threshold_scaled=800)
        assert len(result["public_signals"]) == 2, (
            f"Expected 2 public signals, got {len(result['public_signals'])}: "
            f"{result['public_signals']}"
        )

    @genuine_skip
    def test_witness_file_deleted_after_proof(self):
        """ZKP-9.3: Witness file (.wtns) is cleaned up after proof generation."""
        svc = ZKPService()
        witness_path = svc.work_dir / "witness.wtns"
        svc.generate_genuine_proof(cgpa_scaled=950, threshold_scaled=800)
        assert not witness_path.exists(), (
            "Witness file should be deleted after proof generation (contains private CGPA)"
        )

    @genuine_skip
    def test_input_json_deleted_after_proof(self):
        """ZKP-9.4: Private input.json is cleaned up after proof generation."""
        svc = ZKPService()
        input_path = svc.work_dir / "input.json"
        svc.generate_genuine_proof(cgpa_scaled=950, threshold_scaled=800)
        assert not input_path.exists(), (
            "input.json (contains private CGPA) should be deleted after proof generation"
        )
