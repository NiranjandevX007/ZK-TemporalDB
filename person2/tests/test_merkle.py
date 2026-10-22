"""
ZK-TemporalDB — Unit Tests: Merkle Tree

These tests run WITHOUT any database connection.
They verify the Merkle tree construction, proof generation, and verification.

Test IDs:
    T6: Valid inclusion proof succeeds
    T7: Altered leaf/path/root fails verification
    T8: Edge cases: empty, single, two leaves, odd counts
"""

import pytest
import hashlib

from person2.merkle import MerkleTree, _leaf_hash, _node_hash


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_hash(data: str) -> str:
    """Create a SHA-256 hash for test data."""
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


# ── Edge Cases ────────────────────────────────────────────────────────────────

class TestMerkleEdgeCases:
    """Empty, single-leaf, two-leaf, and uneven leaf count trees."""

    def test_empty_tree(self):
        """T8.1: Empty batch → root is None."""
        tree = MerkleTree([])
        assert tree.root is None
        assert tree.leaf_count == 0

    def test_single_leaf(self):
        """T8.2: Single leaf → root equals the leaf hash."""
        h = make_hash("single")
        tree = MerkleTree([h])
        assert tree.root == _leaf_hash(h)
        assert tree.leaf_count == 1

    def test_single_leaf_proof_empty(self):
        """T8.3: Single leaf → proof is empty (root IS the leaf)."""
        h = make_hash("single")
        tree = MerkleTree([h])
        proof = tree.get_proof(0)
        assert proof == []

    def test_single_leaf_verify(self):
        """T8.4: Single leaf → verify with empty proof succeeds."""
        h = make_hash("single")
        tree = MerkleTree([h])
        assert MerkleTree.verify_proof(h, [], tree.root) is True

    def test_two_leaves(self):
        """T8.5: Two leaves produce a proper root."""
        h1 = make_hash("leaf1")
        h2 = make_hash("leaf2")
        tree = MerkleTree([h1, h2])
        expected_root = _node_hash(_leaf_hash(h1), _leaf_hash(h2))
        assert tree.root == expected_root

    def test_three_leaves_odd(self):
        """T8.6: Three leaves — odd count handled correctly."""
        h1, h2, h3 = [make_hash(f"leaf{i}") for i in range(3)]
        tree = MerkleTree([h1, h2, h3])
        assert tree.root is not None
        assert tree.leaf_count == 3

    def test_five_leaves_odd(self):
        """T8.7: Five leaves — multiple odd levels."""
        hashes = [make_hash(f"leaf{i}") for i in range(5)]
        tree = MerkleTree(hashes)
        assert tree.root is not None
        assert tree.leaf_count == 5


# ── Proof Generation & Verification ──────────────────────────────────────────

class TestMerkleProofs:
    """Inclusion proof generation and verification."""

    @pytest.fixture
    def four_leaf_tree(self):
        """Create a 4-leaf tree for testing."""
        hashes = [make_hash(f"record_{i}") for i in range(4)]
        return MerkleTree(hashes), hashes

    @pytest.fixture
    def seven_leaf_tree(self):
        """Create a 7-leaf tree for testing."""
        hashes = [make_hash(f"record_{i}") for i in range(7)]
        return MerkleTree(hashes), hashes

    def test_valid_proof_leaf_0(self, four_leaf_tree):
        """T6.1: Valid proof for leaf 0."""
        tree, hashes = four_leaf_tree
        proof = tree.get_proof(0)
        assert MerkleTree.verify_proof(hashes[0], proof, tree.root) is True

    def test_valid_proof_leaf_1(self, four_leaf_tree):
        """T6.2: Valid proof for leaf 1."""
        tree, hashes = four_leaf_tree
        proof = tree.get_proof(1)
        assert MerkleTree.verify_proof(hashes[1], proof, tree.root) is True

    def test_valid_proof_leaf_2(self, four_leaf_tree):
        """T6.3: Valid proof for leaf 2."""
        tree, hashes = four_leaf_tree
        proof = tree.get_proof(2)
        assert MerkleTree.verify_proof(hashes[2], proof, tree.root) is True

    def test_valid_proof_leaf_3(self, four_leaf_tree):
        """T6.4: Valid proof for leaf 3."""
        tree, hashes = four_leaf_tree
        proof = tree.get_proof(3)
        assert MerkleTree.verify_proof(hashes[3], proof, tree.root) is True

    def test_valid_proof_all_seven(self, seven_leaf_tree):
        """T6.5: All proofs valid in 7-leaf tree."""
        tree, hashes = seven_leaf_tree
        for i in range(7):
            proof = tree.get_proof(i)
            assert MerkleTree.verify_proof(hashes[i], proof, tree.root) is True

    def test_proof_out_of_range(self, four_leaf_tree):
        """T6.6: Out-of-range index raises IndexError."""
        tree, _ = four_leaf_tree
        with pytest.raises(IndexError):
            tree.get_proof(4)
        with pytest.raises(IndexError):
            tree.get_proof(-1)


# ── Failure Cases ─────────────────────────────────────────────────────────────

class TestMerkleFailures:
    """Altered leaves, paths, and roots must fail verification."""

    @pytest.fixture
    def tree_and_proof(self):
        hashes = [make_hash(f"record_{i}") for i in range(4)]
        tree = MerkleTree(hashes)
        proof = tree.get_proof(0)
        return tree, hashes, proof

    def test_altered_leaf_fails(self, tree_and_proof):
        """T7.1: Altered leaf hash fails verification."""
        tree, hashes, proof = tree_and_proof
        fake_hash = make_hash("tampered_record")
        assert MerkleTree.verify_proof(fake_hash, proof, tree.root) is False

    def test_altered_sibling_fails(self, tree_and_proof):
        """T7.2: Altered sibling hash in proof fails verification."""
        tree, hashes, proof = tree_and_proof
        if proof:
            tampered_proof = list(proof)
            tampered_proof[0] = (make_hash("fake_sibling"), proof[0][1])
            assert MerkleTree.verify_proof(
                hashes[0], tampered_proof, tree.root
            ) is False

    def test_altered_root_fails(self, tree_and_proof):
        """T7.3: Altered root fails verification."""
        tree, hashes, proof = tree_and_proof
        fake_root = make_hash("fake_root")
        assert MerkleTree.verify_proof(hashes[0], proof, fake_root) is False

    def test_wrong_direction_fails(self, tree_and_proof):
        """T7.4: Swapped direction in proof fails verification."""
        tree, hashes, proof = tree_and_proof
        if proof:
            tampered_proof = list(proof)
            h, d = proof[0]
            tampered_proof[0] = (h, 'L' if d == 'R' else 'R')
            assert MerkleTree.verify_proof(
                hashes[0], tampered_proof, tree.root
            ) is False

    def test_missing_step_fails(self, tree_and_proof):
        """T7.5: Proof with missing step fails."""
        tree, hashes, proof = tree_and_proof
        if len(proof) > 1:
            truncated = proof[:-1]
            assert MerkleTree.verify_proof(
                hashes[0], truncated, tree.root
            ) is False

    def test_extra_step_fails(self, tree_and_proof):
        """T7.6: Proof with extra step fails."""
        tree, hashes, proof = tree_and_proof
        extended = proof + [(make_hash("extra"), 'R')]
        assert MerkleTree.verify_proof(
            hashes[0], extended, tree.root
        ) is False

    def test_empty_proof_wrong_root(self):
        """T7.7: Empty proof against wrong root fails."""
        h = make_hash("leaf")
        tree = MerkleTree([h])
        fake_root = make_hash("fake")
        assert MerkleTree.verify_proof(h, [], fake_root) is False


# ── Domain Separation ────────────────────────────────────────────────────────

class TestDomainSeparation:
    """Leaf and node hashing use distinct domain prefixes."""

    def test_leaf_node_different(self):
        """Leaf hash ≠ node hash for same input."""
        data = make_hash("test")
        assert _leaf_hash(data) != _node_hash(data, data)

    def test_leaf_prefix(self):
        """Leaf hash uses 'leaf:' prefix."""
        data = "abc"
        expected = hashlib.sha256(f"leaf:{data}".encode('utf-8')).hexdigest()
        assert _leaf_hash(data) == expected

    def test_node_prefix(self):
        """Node hash uses 'node:' prefix."""
        a, b = "left", "right"
        expected = hashlib.sha256(f"node:{a}{b}".encode('utf-8')).hexdigest()
        assert _node_hash(a, b) == expected
