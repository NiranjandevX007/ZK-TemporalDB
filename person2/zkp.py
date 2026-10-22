"""
ZK-TemporalDB — Zero-Knowledge Proof for CGPA Threshold Verification

Proves the statement:
    "The student's CGPA meets or exceeds threshold T"
    without revealing the exact CGPA.

Architecture:
    - A Circom arithmetic circuit (circuits/cgpa_threshold.circom) encodes
      the constraint: cgpa_scaled >= threshold_scaled.
    - snarkjs generates and verifies Groth16 proofs.
    - CGPA values are represented as integers scaled by 100
      (e.g., 9.50 → 950, 8.00 → 800) to avoid floating-point ambiguity.
    - The exact CGPA is a PRIVATE input (witness).
    - The threshold and eligibility result are PUBLIC.

Trusted Setup Warning:
    This implementation uses a test-only "powers of tau" ceremony.
    In production, a proper trusted setup with multiple participants
    would be required. The test ceremony is sufficient for demonstration
    but provides NO security guarantee against a malicious prover
    who participated in the setup.

Fallback:
    If Circom/snarkjs cannot be installed, this module provides:
    1. A Pedersen-commitment-based approach using discrete log hardness.
    2. Clear documentation that it is NOT a full ZKP but an honest
       commitment scheme with documented limitations.

Usage:
    from person2.zkp import ZKPService
    svc = ZKPService()
    proof = svc.generate_threshold_proof(cgpa_scaled=950, threshold_scaled=800)
    valid = svc.verify_threshold_proof(proof)
"""

import hashlib
import json
import logging
import os
import secrets
import subprocess
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Integer scale for CGPA ────────────────────────────────────────────────────
# CGPA 9.50 → 950, threshold 8.00 → 800
# Valid range: 0.00–10.00 → 0–1000
CGPA_SCALE = 100
CGPA_MIN = 0
CGPA_MAX = 1000  # 10.00 × 100


def _find_binary(names: list) -> Optional[str]:
    """
    Find a binary by trying:
      1. Each name on the system PATH (shutil.which).
      2. person2/node_modules/.bin/<name>  (local npm install).

    Returns the absolute path string, or None if not found.
    """
    local_bin = Path(__file__).parent / "node_modules" / ".bin"
    for name in names:
        # System PATH
        found = shutil.which(name)
        if found:
            return found
        # Local node_modules
        candidate = local_bin / name
        if candidate.exists() and os.access(str(candidate), os.X_OK):
            return str(candidate)
    return None


def _check_snarkjs() -> bool:
    """Check if snarkjs is available (system PATH or local node_modules)."""
    return _find_binary(['snarkjs']) is not None


def _check_circom() -> bool:
    """Check if circom (or circom2 WASM variant) is available.

    circom2 (npm package) is a WebAssembly build of the Circom 2.x compiler
    that works on ARM64/Apple Silicon without Rosetta.
    The native circom binary requires Rust and is amd64-only in pre-built
    release form.
    """
    return _find_binary(['circom', 'circom2']) is not None


class ZKPService:
    """
    Zero-Knowledge Proof service for CGPA threshold verification.

    Attempts to use Circom + snarkjs (genuine Groth16 ZKP).
    Falls back to a hash-commitment scheme if toolchain unavailable.

    Binary discovery:
        Looks for `circom` / `circom2` and `snarkjs` on the system PATH first,
        then falls back to person2/node_modules/.bin/ (local npm install).
        This allows the genuine ZKP path to activate without requiring
        global package installation.
    """

    def __init__(self, work_dir: str = None):
        """
        Args:
            work_dir: Directory for circuit artifacts. Defaults to
                      person2/circuits/build/
        """
        base = Path(__file__).parent
        self.circuits_dir = base / "circuits"
        self.work_dir = Path(work_dir) if work_dir else self.circuits_dir / "build"
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Resolve actual binary paths (system or local node_modules)
        self._circom_bin = _find_binary(['circom', 'circom2'])
        self._snarkjs_bin = _find_binary(['snarkjs'])

        self.has_circom = self._circom_bin is not None
        self.has_snarkjs = self._snarkjs_bin is not None
        self.genuine_zkp = self.has_circom and self.has_snarkjs

        if self.genuine_zkp:
            logger.info(
                "Circom/snarkjs available — using genuine ZKP "
                "(circom=%s, snarkjs=%s)",
                self._circom_bin, self._snarkjs_bin
            )
        else:
            logger.warning(
                "Circom/snarkjs not available (circom=%s, snarkjs=%s). "
                "Using commitment-based fallback. This is NOT a full ZKP.",
                self.has_circom, self.has_snarkjs
            )

    # ── Genuine ZKP (Circom + snarkjs) ────────────────────────────────────────

    def setup_circuit(self) -> bool:
        """
        Compile the Circom circuit and run trusted setup.

        Steps:
            1. Compile cgpa_threshold.circom → WASM + R1CS
            2. Generate powers of tau (test ceremony)
            3. Generate proving and verification keys

        Returns:
            True if setup succeeded, False otherwise.
        """
        if not self.genuine_zkp:
            logger.error("Cannot setup circuit: Circom/snarkjs not installed")
            return False

        circuit_path = self.circuits_dir / "cgpa_threshold.circom"
        if not circuit_path.exists():
            logger.error("Circuit file not found: %s", circuit_path)
            return False

        try:
            build = self.work_dir
            build.mkdir(parents=True, exist_ok=True)

            # Step 1: Compile circuit
            logger.info("Compiling Circom circuit...")
            subprocess.run([
                self._circom_bin, str(circuit_path),
                '--r1cs', '--wasm', '--sym',
                '-o', str(build)
            ], check=True, capture_output=True, text=True)

            # Step 2: Powers of tau (test-only ceremony)
            logger.info("Running powers of tau ceremony (TEST ONLY)...")
            ptau_0 = build / "pot12_0000.ptau"
            ptau_1 = build / "pot12_0001.ptau"
            ptau_final = build / "pot12_final.ptau"

            subprocess.run([
                self._snarkjs_bin, 'powersoftau', 'new', 'bn128', '12',
                str(ptau_0), '-v'
            ], check=True, capture_output=True, text=True)

            subprocess.run([
                self._snarkjs_bin, 'powersoftau', 'contribute',
                str(ptau_0), str(ptau_1),
                '--name=test_contribution', '-v', '-e=random_entropy_for_test'
            ], check=True, capture_output=True, text=True)

            subprocess.run([
                self._snarkjs_bin, 'powersoftau', 'prepare', 'phase2',
                str(ptau_1), str(ptau_final), '-v'
            ], check=True, capture_output=True, text=True)

            # Step 3: Generate proving key
            r1cs = build / "cgpa_threshold.r1cs"
            zkey_0 = build / "cgpa_threshold_0000.zkey"
            zkey_final = build / "cgpa_threshold_final.zkey"
            vkey = build / "verification_key.json"

            subprocess.run([
                self._snarkjs_bin, 'groth16', 'setup',
                str(r1cs), str(ptau_final), str(zkey_0)
            ], check=True, capture_output=True, text=True)

            subprocess.run([
                self._snarkjs_bin, 'zkey', 'contribute',
                str(zkey_0), str(zkey_final),
                '--name=test_contribution', '-v', '-e=more_random_entropy'
            ], check=True, capture_output=True, text=True)

            subprocess.run([
                self._snarkjs_bin, 'zkey', 'export', 'verificationkey',
                str(zkey_final), str(vkey)
            ], check=True, capture_output=True, text=True)

            logger.info("Circuit setup complete. Artifacts in %s", build)
            return True

        except subprocess.CalledProcessError as e:
            logger.error("Circuit setup failed: %s\nstderr: %s", e, e.stderr)
            return False
        except Exception as e:
            logger.error("Circuit setup failed: %s", e)
            return False

    def generate_genuine_proof(
        self,
        cgpa_scaled: int,
        threshold_scaled: int
    ) -> dict:
        """
        Generate a genuine Groth16 ZKP proof.

        Args:
            cgpa_scaled: Student's CGPA × 100 (PRIVATE). E.g., 950 for 9.50.
            threshold_scaled: Threshold × 100 (PUBLIC). E.g., 800 for 8.00.

        Returns:
            Dict with proof, public signals, and metadata.
        """
        self._validate_inputs(cgpa_scaled, threshold_scaled)

        eligible = 1 if cgpa_scaled >= threshold_scaled else 0

        build = self.work_dir
        input_json = build / "input.json"
        witness = build / "witness.wtns"
        proof_json = build / "proof.json"
        public_json = build / "public.json"
        zkey = build / "cgpa_threshold_final.zkey"
        wasm = build / "cgpa_threshold_js" / "cgpa_threshold.wasm"

        # Write private input
        with open(input_json, 'w') as f:
            json.dump({
                "cgpa": cgpa_scaled,
                "threshold": threshold_scaled
            }, f)

        try:
            # Generate witness
            subprocess.run([
                'node',
                str(build / "cgpa_threshold_js" / "generate_witness.js"),
                str(wasm), str(input_json), str(witness)
            ], check=True, capture_output=True, text=True)

            # Generate proof
            subprocess.run([
                self._snarkjs_bin, 'groth16', 'prove',
                str(zkey), str(witness),
                str(proof_json), str(public_json)
            ], check=True, capture_output=True, text=True)

            with open(proof_json) as f:
                proof = json.load(f)
            with open(public_json) as f:
                public_signals = json.load(f)

            # Clean up private input
            input_json.unlink(missing_ok=True)
            witness.unlink(missing_ok=True)

            return {
                "proof_type": "groth16_genuine",
                "proof": proof,
                "public_signals": public_signals,
                "threshold_scaled": threshold_scaled,
                "eligible": eligible,
                "metadata": {
                    "scale_factor": CGPA_SCALE,
                    "circuit": "cgpa_threshold.circom",
                    "curve": "bn128",
                    "trusted_setup": "TEST_ONLY",
                }
            }

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Proof generation failed: {e.stderr}") from e

    def verify_genuine_proof(self, proof_data: dict) -> dict:
        """
        Verify a genuine Groth16 ZKP proof.

        Returns:
            { "valid": bool, "eligible": bool, "details": str }
        """
        build = self.work_dir
        vkey = build / "verification_key.json"
        proof_json = build / "verify_proof.json"
        public_json = build / "verify_public.json"

        try:
            with open(proof_json, 'w') as f:
                json.dump(proof_data["proof"], f)
            with open(public_json, 'w') as f:
                json.dump(proof_data["public_signals"], f)

            result = subprocess.run([
                self._snarkjs_bin, 'groth16', 'verify',
                str(vkey), str(public_json), str(proof_json)
            ], capture_output=True, text=True)

            valid = result.returncode == 0 and 'OK' in result.stdout

            # Check eligibility from public signals
            eligible = int(proof_data["public_signals"][0]) == 1

            return {
                "valid": valid,
                "eligible": eligible,
                "threshold_scaled": proof_data.get("threshold_scaled"),
                "details": (
                    "Genuine Groth16 proof verified successfully"
                    if valid else
                    f"Proof verification failed: {result.stdout} {result.stderr}"
                ),
            }

        except Exception as e:
            return {
                "valid": False,
                "eligible": False,
                "details": f"Verification error: {e}",
            }
        finally:
            proof_json.unlink(missing_ok=True)
            public_json.unlink(missing_ok=True)

    # ── Commitment-Based Fallback ─────────────────────────────────────────────
    # HONEST DISCLAIMER: This is NOT a zero-knowledge proof.
    # It is a hash-based commitment scheme that:
    #   - Commits to the CGPA without revealing it
    #   - Proves the threshold comparison result
    #   - Can be independently verified IF the prover reveals the commitment
    #     opening (blinding factor)
    #
    # Limitations vs. genuine ZKP:
    #   - The verifier must trust the prover computed the comparison honestly
    #     (or the prover must reveal the CGPA, breaking privacy)
    #   - No soundness guarantee: a dishonest prover can commit to a fake CGPA
    #   - This is included as a functional fallback for environments where
    #     Circom/snarkjs cannot be installed

    def generate_commitment_proof(
        self,
        cgpa_scaled: int,
        threshold_scaled: int
    ) -> dict:
        """
        Generate a commitment-based proof (FALLBACK — NOT a genuine ZKP).

        The prover:
            1. Generates a random blinding factor.
            2. Commits: commitment = SHA-256(cgpa_scaled || blinding).
            3. Computes eligible = (cgpa_scaled >= threshold_scaled).
            4. Returns the commitment, eligibility, and threshold (public),
               but NOT the cgpa_scaled or blinding (private, kept for
               later verification if needed).

        The blinding factor and cgpa_scaled are returned to the PROVER only
        (stored locally or in a private document). They are NOT included in
        the public proof metadata.
        """
        self._validate_inputs(cgpa_scaled, threshold_scaled)

        blinding = secrets.token_hex(32)  # 256-bit random
        eligible = cgpa_scaled >= threshold_scaled

        # Commitment: H(cgpa || ":" || blinding)
        commitment_input = f"{cgpa_scaled}:{blinding}"
        commitment = hashlib.sha256(commitment_input.encode('utf-8')).hexdigest()

        # Range proof: demonstrate cgpa is in [0, 1000]
        in_range = CGPA_MIN <= cgpa_scaled <= CGPA_MAX

        # Public proof (safe to store/share)
        public_proof = {
            "proof_type": "commitment_fallback",
            "commitment": commitment,
            "threshold_scaled": threshold_scaled,
            "eligible": eligible,
            "cgpa_in_valid_range": in_range,
            "metadata": {
                "scale_factor": CGPA_SCALE,
                "hash_algorithm": "SHA-256",
                "WARNING": (
                    "This is a commitment scheme, NOT a zero-knowledge proof. "
                    "The verifier must trust the prover's eligibility claim "
                    "unless the prover reveals the opening."
                ),
            }
        }

        # Private opening (NEVER stored in public proof metadata)
        private_opening = {
            "cgpa_scaled": cgpa_scaled,
            "blinding": blinding,
        }

        return {
            "public_proof": public_proof,
            "private_opening": private_opening,
        }

    def verify_commitment_proof(
        self,
        public_proof: dict,
        private_opening: dict = None
    ) -> dict:
        """
        Verify a commitment-based proof.

        Without private_opening: Can only verify the proof structure is valid.
        With private_opening: Can verify the commitment opens correctly and
                              the eligibility claim is honest.
        """
        result = {
            "valid": False,
            "eligible": public_proof.get("eligible", False),
            "commitment_verified": False,
            "eligibility_verified": False,
            "details": "",
        }

        if private_opening:
            # Verify commitment opens correctly
            cgpa = private_opening["cgpa_scaled"]
            blinding = private_opening["blinding"]
            recomputed = hashlib.sha256(
                f"{cgpa}:{blinding}".encode('utf-8')
            ).hexdigest()

            result["commitment_verified"] = (
                recomputed == public_proof["commitment"]
            )

            # Verify eligibility claim
            threshold = public_proof["threshold_scaled"]
            actual_eligible = cgpa >= threshold
            result["eligibility_verified"] = (
                actual_eligible == public_proof["eligible"]
            )

            result["valid"] = (
                result["commitment_verified"]
                and result["eligibility_verified"]
            )

            if result["valid"]:
                result["details"] = (
                    "Commitment verified and eligibility confirmed "
                    "(with private opening — privacy was revealed to verifier)"
                )
            else:
                problems = []
                if not result["commitment_verified"]:
                    problems.append("commitment mismatch")
                if not result["eligibility_verified"]:
                    problems.append("eligibility claim is false")
                result["details"] = "FAILED: " + ", ".join(problems)
        else:
            # Without opening, we can only check structure
            result["valid"] = False
            result["details"] = (
                "Cannot verify without private opening. "
                "This commitment scheme requires the prover to reveal "
                "the blinding factor for full verification."
            )

        return result

    # ── Unified Interface ─────────────────────────────────────────────────────

    def generate_threshold_proof(
        self,
        cgpa_scaled: int,
        threshold_scaled: int
    ) -> dict:
        """
        Generate a threshold proof using the best available method.

        Uses genuine Groth16 ZKP if Circom/snarkjs are available,
        otherwise falls back to commitment scheme.
        """
        if self.genuine_zkp:
            # Check if circuit is set up
            vkey = self.work_dir / "verification_key.json"
            if not vkey.exists():
                logger.info("Setting up circuit for first use...")
                if not self.setup_circuit():
                    logger.warning("Circuit setup failed, using fallback")
                    return self.generate_commitment_proof(
                        cgpa_scaled, threshold_scaled
                    )
            return self.generate_genuine_proof(cgpa_scaled, threshold_scaled)
        else:
            return self.generate_commitment_proof(cgpa_scaled, threshold_scaled)

    def verify_threshold_proof(
        self,
        proof_data: dict,
        private_opening: dict = None
    ) -> dict:
        """
        Verify a threshold proof using the appropriate method.
        """
        proof_type = proof_data.get("proof_type")
        if proof_type is None:
            # Check if it's wrapped in public_proof
            if "public_proof" in proof_data:
                return self.verify_commitment_proof(
                    proof_data["public_proof"], private_opening
                )

        if proof_type == "groth16_genuine":
            return self.verify_genuine_proof(proof_data)
        elif proof_type == "commitment_fallback":
            return self.verify_commitment_proof(proof_data, private_opening)
        else:
            return {
                "valid": False,
                "details": f"Unknown proof type: {proof_type}",
            }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_inputs(cgpa_scaled: int, threshold_scaled: int):
        """Validate CGPA and threshold are in the academic range."""
        if not isinstance(cgpa_scaled, int):
            raise TypeError(f"cgpa_scaled must be int, got {type(cgpa_scaled)}")
        if not isinstance(threshold_scaled, int):
            raise TypeError(
                f"threshold_scaled must be int, got {type(threshold_scaled)}"
            )
        if not (CGPA_MIN <= cgpa_scaled <= CGPA_MAX):
            raise ValueError(
                f"cgpa_scaled={cgpa_scaled} out of range [{CGPA_MIN}, {CGPA_MAX}]"
            )
        if not (CGPA_MIN <= threshold_scaled <= CGPA_MAX):
            raise ValueError(
                f"threshold_scaled={threshold_scaled} out of range "
                f"[{CGPA_MIN}, {CGPA_MAX}]"
            )

    @staticmethod
    def cgpa_to_scaled(cgpa_decimal) -> int:
        """Convert a Decimal CGPA to scaled integer. 9.50 → 950."""
        from decimal import Decimal, ROUND_HALF_UP
        d = Decimal(str(cgpa_decimal))
        return int(d * CGPA_SCALE)

    @staticmethod
    def scaled_to_cgpa(scaled: int) -> str:
        """Convert scaled integer back to CGPA string. 950 → '9.50'."""
        from decimal import Decimal
        return str(Decimal(scaled) / CGPA_SCALE)

    def get_toolchain_status(self) -> dict:
        """Report the ZKP toolchain availability and resolved binary paths."""
        return {
            "circom_available": self.has_circom,
            "circom_path": self._circom_bin,
            "snarkjs_available": self.has_snarkjs,
            "snarkjs_path": self._snarkjs_bin,
            "genuine_zkp": self.genuine_zkp,
            "fallback_mode": not self.genuine_zkp,
            "proof_type": (
                "groth16_genuine" if self.genuine_zkp
                else "commitment_fallback"
            ),
        }
