"""
ZK-TemporalDB — Merkle Tree Construction and Inclusion Proofs

Implements a binary Merkle tree over SHA-256 hashes for batch verification
of record versions.

Conventions:
    - Leaf hashing: leaf_hash = SHA-256("leaf:" || data_hash)
      The "leaf:" prefix prevents second-preimage attacks where an internal
      node could be confused with a leaf.
    - Internal node: SHA-256("node:" || left_hash || right_hash)
    - Leaf ordering: leaves are ordered by their position in the input list.
      The caller must sort (e.g., by version_id) before calling.
    - Odd-numbered nodes: the last unpaired node is promoted (carried up)
      to the next level without hashing — NOT duplicated.
    - Empty batch: root is None.
    - Single leaf: root equals the leaf hash.

Proof format:
    A list of (sibling_hash, direction) tuples, where direction is
    'L' (sibling is on the left) or 'R' (sibling is on the right).

Usage:
    from person2.merkle import MerkleTree
    tree = MerkleTree(["hash1", "hash2", "hash3"])
    root = tree.root
    proof = tree.get_proof(0)
    valid = MerkleTree.verify_proof("hash1", proof, root)
"""

import hashlib
from typing import Optional


def _sha256(data: str) -> str:
    """Compute SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def _leaf_hash(data_hash: str) -> str:
    """Hash a leaf with domain separation prefix."""
    return _sha256("leaf:" + data_hash)


def _node_hash(left: str, right: str) -> str:
    """Hash an internal node with domain separation prefix."""
    return _sha256("node:" + left + right)


class MerkleTree:
    """
    Binary Merkle tree over SHA-256 hashes.

    Attributes:
        leaves: List of leaf hashes (after applying leaf domain prefix).
        root: The Merkle root hash, or None for empty trees.
        leaf_count: Number of leaves.
    """

    def __init__(self, data_hashes: list[str]):
        """
        Build a Merkle tree from a list of data hashes.

        Args:
            data_hashes: List of hex SHA-256 hashes to include as leaves.
                         Order matters — leaves are indexed 0..N-1.
        """
        self.data_hashes = list(data_hashes)
        self.leaf_count = len(data_hashes)

        # Compute leaf hashes with domain separation
        self.leaves = [_leaf_hash(h) for h in data_hashes]

        # Build the tree bottom-up, storing all levels
        self._levels = self._build_tree(self.leaves)
        self.root = self._levels[-1][0] if self._levels else None

    @staticmethod
    def _build_tree(leaves: list[str]) -> list[list[str]]:
        """
        Build all levels of the Merkle tree.

        Returns:
            List of levels, from leaves (index 0) to root (last index).
            Each level is a list of hashes.
        """
        if not leaves:
            return []

        levels = [list(leaves)]
        current = list(leaves)

        while len(current) > 1:
            next_level = []
            i = 0
            while i < len(current):
                if i + 1 < len(current):
                    # Pair exists — hash them together
                    next_level.append(_node_hash(current[i], current[i + 1]))
                    i += 2
                else:
                    # Odd node out — promote without rehashing
                    next_level.append(current[i])
                    i += 1
            levels.append(next_level)
            current = next_level

        return levels

    def get_proof(self, leaf_index: int) -> list[tuple[str, str]]:
        """
        Generate an inclusion proof for the leaf at the given index.

        Args:
            leaf_index: 0-based index of the leaf.

        Returns:
            List of (sibling_hash, direction) tuples.
            direction is 'L' if sibling is on the left, 'R' if on the right.

        Raises:
            IndexError: If leaf_index is out of range.
        """
        if leaf_index < 0 or leaf_index >= self.leaf_count:
            raise IndexError(
                f"Leaf index {leaf_index} out of range [0, {self.leaf_count})"
            )

        if self.leaf_count <= 1:
            return []  # Root equals the single leaf — no proof needed

        proof = []
        idx = leaf_index

        for level in self._levels[:-1]:  # Exclude root level
            if len(level) == 1:
                # Only one node at this level — promoted, no sibling
                break

            if idx % 2 == 0:
                # Current node is on the left
                if idx + 1 < len(level):
                    proof.append((level[idx + 1], 'R'))
                # else: odd node, promoted — no sibling at this level
            else:
                # Current node is on the right
                proof.append((level[idx - 1], 'L'))

            idx //= 2

        return proof

    @staticmethod
    def verify_proof(
        data_hash: str,
        proof: list[tuple[str, str]],
        expected_root: str
    ) -> bool:
        """
        Verify a Merkle inclusion proof.

        Args:
            data_hash: The original data hash (before leaf hashing).
            proof: The inclusion proof path.
            expected_root: The expected Merkle root.

        Returns:
            True if the proof is valid, False otherwise.
        """
        current = _leaf_hash(data_hash)

        for sibling_hash, direction in proof:
            if direction == 'L':
                current = _node_hash(sibling_hash, current)
            elif direction == 'R':
                current = _node_hash(current, sibling_hash)
            else:
                return False  # Invalid direction

        return current == expected_root

    def __repr__(self):
        return (
            f"MerkleTree(leaf_count={self.leaf_count}, "
            f"root={self.root[:16]}…)" if self.root else
            "MerkleTree(empty)"
        )


class MerkleBatchService:
    """
    Service for creating and verifying Merkle batches in PostgreSQL.
    Associates record versions with Merkle trees.
    """

    def __init__(self, pg_conn, mongo_db=None, auto_commit: bool = True):
        self.pg_conn = pg_conn
        self.mongo_db = mongo_db
        self.auto_commit = auto_commit

    def create_batch(
        self,
        version_ids: list[int],
        description: str = None
    ) -> dict:
        """
        Create a Merkle batch from a list of record version IDs.

        Steps:
            1. Fetch snapshot_hash for each version_id from PostgreSQL.
            2. Build a Merkle tree from those hashes (ordered by version_id).
            3. Store batch metadata in merkle_batch.
            4. Store leaf associations in merkle_batch_member.
            5. Optionally store in MongoDB.

        Args:
            version_ids: List of version_id values to include.
            description: Optional human-readable batch description.

        Returns:
            Dict with batch_id, merkle_root, leaf_count, and proofs.
        """
        import psycopg2.extras

        if not version_ids:
            raise ValueError("Cannot create a Merkle batch with no versions")

        cur = self.pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            # Fetch hashes in version_id order for deterministic leaf ordering
            placeholders = ','.join(['%s'] * len(version_ids))
            cur.execute(f"""
                SELECT version_id, snapshot_hash
                FROM record_version
                WHERE version_id IN ({placeholders})
                ORDER BY version_id
            """, version_ids)
            rows = cur.fetchall()

            if len(rows) != len(version_ids):
                found = {r["version_id"] for r in rows}
                missing = set(version_ids) - found
                raise ValueError(f"Version IDs not found: {missing}")

            # Build tree
            hashes = [r["snapshot_hash"] for r in rows]
            tree = MerkleTree(hashes)

            # Store batch
            cur.execute("""
                INSERT INTO merkle_batch (merkle_root, leaf_count, description)
                VALUES (%s, %s, %s)
                RETURNING batch_id, merkle_root, leaf_count, created_at
            """, (tree.root, tree.leaf_count, description))
            batch_row = dict(cur.fetchone())

            # Store member associations
            for idx, row in enumerate(rows):
                cur.execute("""
                    INSERT INTO merkle_batch_member (batch_id, version_id, leaf_index)
                    VALUES (%s, %s, %s)
                """, (batch_row["batch_id"], row["version_id"], idx))

            # Store in MongoDB if available
            if self.mongo_db is not None:
                try:
                    proofs = {}
                    for idx, row in enumerate(rows):
                        proofs[str(row["version_id"])] = [
                            {"hash": h, "direction": d}
                            for h, d in tree.get_proof(idx)
                        ]

                    self.mongo_db.merkle_batches.insert_one({
                        "batch_id": batch_row["batch_id"],
                        "merkle_root": tree.root,
                        "leaf_count": tree.leaf_count,
                        "description": description,
                        "leaves": [
                            {"version_id": r["version_id"],
                             "snapshot_hash": r["snapshot_hash"],
                             "leaf_index": idx}
                            for idx, r in enumerate(rows)
                        ],
                        "proofs": proofs,
                    })
                except Exception as e:
                    self.pg_conn.rollback()
                    raise RuntimeError(
                        f"MongoDB batch write failed, PG rolled back: {e}"
                    ) from e

            if self.auto_commit:
                self.pg_conn.commit()

            # Generate proofs for the return value
            result_proofs = {}
            for idx, row in enumerate(rows):
                result_proofs[row["version_id"]] = tree.get_proof(idx)

            batch_row["proofs"] = result_proofs
            if batch_row.get("created_at"):
                batch_row["created_at"] = batch_row["created_at"].isoformat()
            return batch_row

        except Exception:
            self.pg_conn.rollback()
            raise
        finally:
            cur.close()

    def verify_inclusion(
        self,
        batch_id: int,
        version_id: int
    ) -> dict:
        """
        Verify that a record version is included in a Merkle batch.

        Steps:
            1. Fetch the batch's merkle_root.
            2. Fetch the version's snapshot_hash.
            3. Reconstruct the proof from the stored tree or recompute.
            4. Verify the inclusion proof.

        Returns:
            { "valid": bool, "details": str }
        """
        import psycopg2.extras

        cur = self.pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get batch info
        cur.execute("""
            SELECT merkle_root, leaf_count FROM merkle_batch
            WHERE batch_id = %s
        """, (batch_id,))
        batch = cur.fetchone()
        if not batch:
            return {"valid": False, "details": f"Batch {batch_id} not found"}

        # Check membership
        cur.execute("""
            SELECT leaf_index FROM merkle_batch_member
            WHERE batch_id = %s AND version_id = %s
        """, (batch_id, version_id))
        member = cur.fetchone()
        if not member:
            return {
                "valid": False,
                "details": f"Version {version_id} is not a member of batch {batch_id}"
            }

        # Get all hashes in this batch to rebuild the tree
        cur.execute("""
            SELECT rv.snapshot_hash, mbm.leaf_index
            FROM merkle_batch_member mbm
            JOIN record_version rv ON rv.version_id = mbm.version_id
            WHERE mbm.batch_id = %s
            ORDER BY mbm.leaf_index
        """, (batch_id,))
        all_members = cur.fetchall()
        cur.close()

        # Rebuild tree
        hashes = [m["snapshot_hash"] for m in all_members]
        tree = MerkleTree(hashes)

        # Verify root matches
        if tree.root != batch["merkle_root"]:
            return {
                "valid": False,
                "details": (
                    f"Rebuilt root {tree.root[:16]}… does not match "
                    f"stored root {batch['merkle_root'][:16]}…"
                )
            }

        # Get the target version's hash and proof
        target_hash = hashes[member["leaf_index"]]
        proof = tree.get_proof(member["leaf_index"])
        valid = MerkleTree.verify_proof(target_hash, proof, batch["merkle_root"])

        return {
            "valid": valid,
            "details": "Inclusion proof verified" if valid else "Proof verification failed",
        }
