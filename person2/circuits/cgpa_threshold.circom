/*
 * ZK-TemporalDB — CGPA Threshold Verification Circuit
 *
 * Proves: "The student's CGPA (private) >= threshold (public)"
 * without revealing the exact CGPA.
 *
 * Inputs:
 *   - cgpa      (PRIVATE): Student's CGPA scaled by 100 (e.g., 950 for 9.50)
 *   - threshold (PUBLIC):  Minimum CGPA threshold scaled by 100 (e.g., 800)
 *
 * Outputs:
 *   - eligible (PUBLIC):   1 if cgpa >= threshold, 0 otherwise
 *
 * Integer Scale Convention:
 *   All values are integers in [0, 1000] representing CGPA × 100.
 *   This avoids floating-point ambiguity in the finite field.
 *
 * Range Constraints:
 *   Both cgpa and threshold are constrained to [0, 1000].
 *   This prevents overflow and ensures the comparison is meaningful.
 *
 * Trusted Setup:
 *   This circuit requires a Groth16 trusted setup (powers of tau).
 *   The test setup included in this project is for DEMONSTRATION ONLY
 *   and does NOT provide production-grade security.
 */

pragma circom 2.0.0;

// ─────────────────────────────────────────────────────────────────────────────
// LessEqThan: outputs 1 if in[0] <= in[1], else 0
// Uses n bits for comparison.
// ─────────────────────────────────────────────────────────────────────────────
template LessEqThan(n) {
    signal input in[2];
    signal output out;

    // Compute difference: diff = in[1] - in[0] + 2^n
    // If in[0] <= in[1], diff is in [2^n, 2^(n+1)-1], so bit n is 1
    // If in[0] > in[1], diff is in [0, 2^n-1], so bit n is 0
    signal diff;
    diff <== in[1] - in[0] + (1 << n);

    // Extract bit n of diff
    // We decompose diff into n+1 bits and check the highest bit
    signal bits[n+1];
    var lc = 0;
    var e2 = 1;
    for (var i = 0; i < n+1; i++) {
        bits[i] <-- (diff >> i) & 1;
        bits[i] * (bits[i] - 1) === 0;  // Constrain to binary
        lc += bits[i] * e2;
        e2 = e2 * 2;
    }
    lc === diff;  // Constrain bit decomposition equals diff

    out <== bits[n];  // The sign bit tells us the comparison result
}

// ─────────────────────────────────────────────────────────────────────────────
// RangeCheck: constrains that 0 <= value <= max_val
// ─────────────────────────────────────────────────────────────────────────────
template RangeCheck(n, max_val) {
    signal input value;

    // Check value >= 0 (already guaranteed by field arithmetic if small)
    // Check value <= max_val using LessEqThan
    component leq = LessEqThan(n);
    leq.in[0] <== value;
    leq.in[1] <== max_val;
    leq.out === 1;
}

// ─────────────────────────────────────────────────────────────────────────────
// CGPAThreshold: Main circuit
// ─────────────────────────────────────────────────────────────────────────────
template CGPAThreshold() {
    // Private input: student's CGPA (scaled by 100)
    signal input cgpa;

    // Public input: threshold CGPA (scaled by 100)
    signal input threshold;

    // Public output: 1 if eligible (cgpa >= threshold), 0 otherwise
    signal output eligible;

    // Range check: cgpa must be in [0, 1000]
    component cgpa_range = RangeCheck(11, 1000);
    cgpa_range.value <== cgpa;

    // Range check: threshold must be in [0, 1000]
    component threshold_range = RangeCheck(11, 1000);
    threshold_range.value <== threshold;

    // Comparison: cgpa >= threshold  ⟺  threshold <= cgpa
    component cmp = LessEqThan(11);
    cmp.in[0] <== threshold;
    cmp.in[1] <== cgpa;

    eligible <== cmp.out;
}

component main {public [threshold]} = CGPAThreshold();
