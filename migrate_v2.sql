-- ══════════════════════════════════════════════════════════════════════════════
-- ZK-TemporalDB Migration v2 (fixed: system_user quoted — reserved keyword)
-- Pre-conditions verified 2026-10-22: all 5 tables exist, all have 0 rows.
-- "system_user" does not exist.
-- Runs as a single transaction; any failure rolls back all changes.
-- No CASCADE used anywhere.
-- ══════════════════════════════════════════════════════════════════════════════

\set ON_ERROR_STOP on

BEGIN;

-- ── Step 1: department — add hod_name ────────────────────────────────────────
ALTER TABLE department
    ADD COLUMN hod_name VARCHAR(100) NOT NULL DEFAULT 'TBD';

ALTER TABLE department
    ALTER COLUMN hod_name DROP DEFAULT;

-- ── Step 2: student — rename, retype, add missing columns ────────────────────

-- 2a. Rename full_name → first_name
ALTER TABLE student
    RENAME COLUMN full_name TO first_name;

-- 2b. Narrow VARCHAR(100) → VARCHAR(60) to match schema; table is empty
ALTER TABLE student
    ALTER COLUMN first_name TYPE VARCHAR(60);

-- 2c. Add last_name, dob, program with temporary migration defaults
ALTER TABLE student
    ADD COLUMN last_name  VARCHAR(60) NOT NULL DEFAULT '',
    ADD COLUMN dob        DATE        NOT NULL DEFAULT '2000-01-01',
    ADD COLUMN program    VARCHAR(60) NOT NULL DEFAULT 'B.E.';

-- 2d. Drop temporary defaults immediately (table still empty)
ALTER TABLE student
    ALTER COLUMN last_name  DROP DEFAULT,
    ALTER COLUMN dob        DROP DEFAULT,
    ALTER COLUMN program    DROP DEFAULT;

-- ── Step 3: course — no changes ───────────────────────────────────────────────
-- course is fully ER-consistent. No DDL required.

-- ── Step 4: enrolled_in — add mark/grade columns ─────────────────────────────
-- Existing constraints survive ADD COLUMN untouched.
ALTER TABLE enrolled_in
    ADD COLUMN internal_marks NUMERIC(5,2) NULL
        CONSTRAINT chk_internal_marks
            CHECK (internal_marks IS NULL OR internal_marks BETWEEN 0 AND 30),
    ADD COLUMN external_marks NUMERIC(5,2) NULL
        CONSTRAINT chk_external_marks
            CHECK (external_marks IS NULL OR external_marks BETWEEN 0 AND 70),
    ADD COLUMN grade          VARCHAR(3)   NULL,
    ADD COLUMN grade_point    NUMERIC(4,2) NULL
        CONSTRAINT chk_grade_point
            CHECK (grade_point IS NULL OR grade_point BETWEEN 0 AND 10);

-- ── Step 5: semester_result — DROP and CREATE ─────────────────────────────────
-- No dependants; no CASCADE needed.
DROP TABLE semester_result;

CREATE TABLE semester_result (
    student_id    INTEGER      NOT NULL,
    sem_no        INTEGER      NOT NULL
                      CHECK (sem_no BETWEEN 1 AND 8),
    sgpa          NUMERIC(4,2) NOT NULL
                      CHECK (sgpa BETWEEN 0.00 AND 10.00),
    total_credits INTEGER      NOT NULL
                      CHECK (total_credits > 0),
    result_status VARCHAR(20)  NOT NULL
                      CHECK (result_status IN ('PASS', 'FAIL', 'DETAINED', 'WITHHELD')),

    CONSTRAINT semester_result_pkey
        PRIMARY KEY (student_id, sem_no),

    CONSTRAINT fk_result_student
        FOREIGN KEY (student_id)
        REFERENCES student(student_id)
);

-- ── Step 6: "system_user" — CREATE new table ──────────────────────────────────
-- NOTE: system_user is a reserved word in PostgreSQL; quoted throughout.
CREATE TABLE IF NOT EXISTS "system_user" (
    user_id    INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username   VARCHAR(60)  NOT NULL UNIQUE,
    role       VARCHAR(30)  NOT NULL
                   CHECK (role IN ('FACULTY', 'REGISTRAR', 'ADMIN')),
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMIT;
