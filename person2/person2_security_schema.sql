-- ══════════════════════════════════════════════════════════════════════════════
-- ZK-TemporalDB — Person 2: Security & Versioning Schema
-- Extends Person 1's schema with:
--   • record_version   — SHA-256 versioned academic record snapshots
--   • merkle_batch      — Merkle tree batch metadata (root hashes)
--   • merkle_batch_member — Associates record versions with Merkle batches
--   • Append-only triggers to prevent UPDATE/DELETE on immutable tables
--
-- IMPORTANT: This script is ADDITIVE. It does NOT modify Person 1's tables.
-- Run after Person 1's schema.sql and seed.sql are already loaded.
-- ══════════════════════════════════════════════════════════════════════════════

\set ON_ERROR_STOP on

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: record_version
-- Stores a versioned snapshot of a student's academic record.
-- Each row represents one immutable version with:
--   • version_number : monotonically increasing per student (1, 2, 3, …)
--   • snapshot_hash  : SHA-256 over the canonical JSON snapshot
--   • prev_hash      : SHA-256 hash of the previous version (NULL for v1)
--   • canonical_snapshot : the exact canonical JSON that was hashed
--   • snapshot_scope : what data is captured (e.g. 'full_academic_record')
--   • created_at     : UTC timestamp of version creation
--
-- Append-only: a trigger prevents UPDATE and DELETE.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS record_version (
    version_id        INTEGER       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id        INTEGER       NOT NULL,
    version_number    INTEGER       NOT NULL CHECK (version_number >= 1),
    snapshot_hash     VARCHAR(64)   NOT NULL,   -- SHA-256 hex digest
    prev_hash         VARCHAR(64),              -- NULL for first version
    canonical_snapshot TEXT         NOT NULL,    -- The exact canonical JSON
    snapshot_scope    VARCHAR(50)   NOT NULL DEFAULT 'full_academic_record',
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    -- Each student's version numbers must be unique and sequential
    CONSTRAINT uq_student_version UNIQUE (student_id, version_number),

    -- Reference Person 1's student table
    CONSTRAINT fk_rv_student
        FOREIGN KEY (student_id)
        REFERENCES student(student_id),

    -- First version must have NULL prev_hash; others must have non-NULL
    CONSTRAINT chk_prev_hash_consistency
        CHECK (
            (version_number = 1 AND prev_hash IS NULL)
            OR
            (version_number > 1 AND prev_hash IS NOT NULL)
        )
);

-- Index for fast lookups by student
CREATE INDEX IF NOT EXISTS idx_rv_student_id ON record_version(student_id);

-- Index for hash-based verification lookups
CREATE INDEX IF NOT EXISTS idx_rv_snapshot_hash ON record_version(snapshot_hash);


-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: merkle_batch
-- Stores metadata for a batch of record versions grouped into a Merkle tree.
-- The merkle_root is the root hash of the tree.
-- Append-only: a trigger prevents UPDATE and DELETE.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS merkle_batch (
    batch_id       INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    merkle_root    VARCHAR(64)  NOT NULL,   -- SHA-256 hex digest of tree root
    leaf_count     INTEGER      NOT NULL CHECK (leaf_count > 0),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    description    TEXT
);


-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: merkle_batch_member
-- Associates record_version entries with merkle_batch entries.
-- A record version can appear in multiple batches (e.g., incremental batches).
-- leaf_index records the position in the batch's leaf array.
-- This is a separate join table so that record_version rows are never updated.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS merkle_batch_member (
    batch_id       INTEGER NOT NULL,
    version_id     INTEGER NOT NULL,
    leaf_index     INTEGER NOT NULL CHECK (leaf_index >= 0),

    PRIMARY KEY (batch_id, version_id),

    CONSTRAINT fk_mbm_batch
        FOREIGN KEY (batch_id)
        REFERENCES merkle_batch(batch_id),

    CONSTRAINT fk_mbm_version
        FOREIGN KEY (version_id)
        REFERENCES record_version(version_id),

    -- Each leaf index must be unique within a batch
    CONSTRAINT uq_batch_leaf_index UNIQUE (batch_id, leaf_index)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- TRIGGER: Enforce append-only on record_version
-- Prevents any UPDATE or DELETE on existing record_version rows.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_deny_modify_record_version()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'record_version is append-only: UPDATE and DELETE are prohibited';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_deny_modify_record_version ON record_version;
CREATE TRIGGER trg_deny_modify_record_version
    BEFORE UPDATE OR DELETE ON record_version
    FOR EACH ROW
    EXECUTE FUNCTION fn_deny_modify_record_version();


-- ─────────────────────────────────────────────────────────────────────────────
-- TRIGGER: Enforce append-only on merkle_batch
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_deny_modify_merkle_batch()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'merkle_batch is append-only: UPDATE and DELETE are prohibited';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_deny_modify_merkle_batch ON merkle_batch;
CREATE TRIGGER trg_deny_modify_merkle_batch
    BEFORE UPDATE OR DELETE ON merkle_batch
    FOR EACH ROW
    EXECUTE FUNCTION fn_deny_modify_merkle_batch();


-- ─────────────────────────────────────────────────────────────────────────────
-- TRIGGER: Enforce append-only on merkle_batch_member
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_deny_modify_merkle_batch_member()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'merkle_batch_member is append-only: UPDATE and DELETE are prohibited';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_deny_modify_merkle_batch_member ON merkle_batch_member;
CREATE TRIGGER trg_deny_modify_merkle_batch_member
    BEFORE UPDATE OR DELETE ON merkle_batch_member
    FOR EACH ROW
    EXECUTE FUNCTION fn_deny_modify_merkle_batch_member();


COMMIT;

-- ─────────────────────────────────────────────────────────────────────────────
-- Verification: Confirm all Person 2 objects exist
-- ─────────────────────────────────────────────────────────────────────────────
SELECT '✓ record_version table'     AS check WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'record_version');
SELECT '✓ merkle_batch table'       AS check WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'merkle_batch');
SELECT '✓ merkle_batch_member table' AS check WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'merkle_batch_member');
SELECT '✓ append-only trigger on record_version' AS check WHERE EXISTS (SELECT 1 FROM information_schema.triggers WHERE trigger_name = 'trg_deny_modify_record_version');
SELECT '✓ append-only trigger on merkle_batch'    AS check WHERE EXISTS (SELECT 1 FROM information_schema.triggers WHERE trigger_name = 'trg_deny_modify_merkle_batch');
