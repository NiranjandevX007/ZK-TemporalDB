-- ══════════════════════════════════════════════════════════════════════════════
-- ZK-TemporalDB  —  Transactions and Indexing
-- Person 1: Database Design and SQL
-- Last revised: 2026-10-22
--
-- Run AFTER schema.sql, seed.sql, and functions_triggers.sql.
-- ══════════════════════════════════════════════════════════════════════════════


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 1 : INDEXES
-- ─────────────────────────────────────────────────────────────────────────────
-- Note: PostgreSQL automatically creates B-tree indexes for PRIMARY KEY and
-- UNIQUE constraints. The indexes below cover additional lookup and join patterns.

-- INDEX 1: enrolled_in(student_id)
-- Speeds up queries that fetch all courses for a given student.
-- Example use: viewing a student's transcript, computing SGPA.
CREATE INDEX IF NOT EXISTS idx_enrolled_in_student_id
    ON enrolled_in (student_id);

-- INDEX 2: enrolled_in(course_id)
-- Speeds up queries that fetch all students enrolled in a specific course.
-- Example use: course-level grade statistics, pending-marks search.
CREATE INDEX IF NOT EXISTS idx_enrolled_in_course_id
    ON enrolled_in (course_id);

-- INDEX 3: enrolled_in(semester_number, academic_year)
-- Composite index for filtering enrollments by semester and year.
-- Example use: listing all enrollments in Semester 1 of 2022.
CREATE INDEX IF NOT EXISTS idx_enrolled_in_sem_year
    ON enrolled_in (semester_number, academic_year);

-- INDEX 4: semester_result(student_id)
-- Speeds up CGPA calculation and transcript queries that scan semester_result by student.
-- (The composite PK covers (student_id, sem_no), but a separate index
--  on student_id alone helps queries that filter only on student_id.)
CREATE INDEX IF NOT EXISTS idx_semester_result_student_id
    ON semester_result (student_id);

-- INDEX 5: student(department_id)
-- Speeds up JOIN queries between student and department.
-- Example use: counting students per department.
CREATE INDEX IF NOT EXISTS idx_student_department_id
    ON student (department_id);

-- INDEX 6: course(department_id)
-- Speeds up JOIN queries between course and department.
-- Example use: listing all courses offered by a department.
CREATE INDEX IF NOT EXISTS idx_course_department_id
    ON course (department_id);

-- INDEX 7: enrolled_in(grade) — partial, where grade IS NULL
-- Targets the common query: "find all pending enrollments".
-- A partial index is smaller and faster than a full index for this use case.
CREATE INDEX IF NOT EXISTS idx_enrolled_in_pending_grade
    ON enrolled_in (student_id, course_id)
    WHERE grade IS NULL;

-- Verify indexes created
SELECT indexname, tablename, indexdef
FROM   pg_indexes
WHERE  schemaname = 'public'
  AND  indexname LIKE 'idx_%'
ORDER  BY tablename, indexname;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 2 : TRANSACTION EXAMPLES
--
-- Design note on permanence:
--   Examples A and C use SAVEPOINT + ROLLBACK TO SAVEPOINT so that the
--   demonstration logic executes in full (the SELECT inside shows live results)
--   but no permanent rows are added to the database when this file is re-run.
--   This keeps row counts stable and matches the documented seed dataset.
--   Examples B and D already roll back by design (constraint violation / full ROLLBACK).
-- ─────────────────────────────────────────────────────────────────────────────

-- ─────────────────────────────────────────────────────────────────────────────
-- TRANSACTION EXAMPLE A: Enrollment + marks update, then rolled back
-- Demonstrates BEGIN → INSERT → UPDATE → in-transaction SELECT → ROLLBACK.
-- Uses SAVEPOINT so the inner work is fully visible mid-transaction,
-- then ROLLBACK TO SAVEPOINT removes it — leaving no permanent side-effect.
-- ─────────────────────────────────────────────────────────────────────────────
BEGIN;

    -- Mark the clean state
    SAVEPOINT sp_before_demo_a;

    -- Step 1: Enroll Karthik Reddy (student_id=3) in CS201 (course_id=3) Sem 2, 2022
    INSERT INTO enrolled_in
        (student_id, course_id, academic_year, semester_number,
         internal_marks, external_marks, grade, grade_point)
    VALUES
        (3, 3, 2022, 2, NULL, NULL, NULL, NULL);

    -- Step 2: Record marks atomically in the same transaction
    UPDATE enrolled_in
    SET    internal_marks = 20.00,
           external_marks = 45.00,
           grade          = 'B',
           grade_point    = 7.00
    WHERE  student_id      = 3
      AND  course_id       = 3
      AND  academic_year   = 2022
      AND  semester_number = 2;

    -- Step 3: Verify the data is visible WITHIN the transaction
    SELECT e.student_id, c.course_code, e.internal_marks, e.external_marks, e.grade
    FROM   enrolled_in e
    JOIN   course c ON c.course_id = e.course_id
    WHERE  e.student_id = 3 AND e.semester_number = 2;
    -- ↑ Row IS visible here because we are still inside the transaction.

    -- Step 4: Roll back to savepoint — removes the INSERT+UPDATE
    ROLLBACK TO SAVEPOINT sp_before_demo_a;

    -- Step 5: Confirm the row is gone (within the still-open transaction)
    SELECT COUNT(*) AS should_be_zero_demo_a
    FROM enrolled_in
    WHERE student_id = 3 AND course_id = 3 AND semester_number = 2;

COMMIT;
-- ↑ Commits an empty transaction — no net change to the database.
-- Demonstrates: both INSERT and UPDATE are atomic; ROLLBACK TO SAVEPOINT reverts them.


-- ─────────────────────────────────────────────────────────────────────────────
-- TRANSACTION EXAMPLE B: Safe ROLLBACK demonstration
-- Attempts to declare a semester result with an INVALID status ('HONOURS').
-- The CHECK constraint will reject it; the entire transaction is rolled back.
-- After rollback, no changes are left in the database.
-- ─────────────────────────────────────────────────────────────────────────────
BEGIN;

    -- This INSERT will succeed:
    SAVEPOINT sp_before_invalid;

    -- This INSERT will FAIL — 'HONOURS' is not a valid result_status
    -- (The CHECK constraint enforces PASS / FAIL / DETAINED / WITHHELD)
    INSERT INTO semester_result (student_id, sem_no, sgpa, total_credits, result_status)
    VALUES (1, 99, 9.50, 8, 'HONOURS');   -- sem_no 99 also violates the sem_no CHECK

ROLLBACK TO SAVEPOINT sp_before_invalid;
-- ↑ ROLLBACK TO SAVEPOINT undoes only the failed statement.
-- The outer transaction is still open; we commit it cleanly.
COMMIT;

-- After this block, no row with sem_no=99 exists.
SELECT COUNT(*) AS should_be_zero
FROM   semester_result
WHERE  sem_no = 99;


-- ─────────────────────────────────────────────────────────────────────────────
-- TRANSACTION EXAMPLE C: Procedure call inside a transaction, then rolled back
-- Demonstrates calling sp_declare_result inside a BEGIN block.
-- Uses SAVEPOINT so the result is visible mid-transaction, then reverted.
-- ─────────────────────────────────────────────────────────────────────────────
BEGIN;

    SAVEPOINT sp_before_demo_c;

    CALL sp_declare_result(
        p_student_id    => 1,
        p_sem_no        => 2,
        p_sgpa          => 8.00,   -- illustrative value
        p_total_credits => 8,
        p_result_status => 'PASS'
    );

    -- Verify the result is visible WITHIN the transaction
    SELECT student_id, sem_no, sgpa, result_status
    FROM   semester_result
    WHERE  student_id = 1;
    -- ↑ Shows both sem_no=1 (from seed) and sem_no=2 (this transaction)

    -- Roll back — sp_declare_result's insert is undone
    ROLLBACK TO SAVEPOINT sp_before_demo_c;

    -- Confirm sem_no=2 is gone
    SELECT COUNT(*) AS should_be_one_demo_c
    FROM   semester_result
    WHERE  student_id = 1;
    -- ↑ Should be 1 (only sem_no=1 from seed remains)

COMMIT;
-- ↑ Commits an empty transaction — no net change.
-- Demonstrates: procedure calls are transactional; SAVEPOINT can revert them.


-- ─────────────────────────────────────────────────────────────────────────────
-- TRANSACTION EXAMPLE D: Full rollback — no data persisted
-- Shows that if we ROLLBACK (not ROLLBACK TO SAVEPOINT), all changes vanish.
-- A good negative test for demonstrations.
-- ─────────────────────────────────────────────────────────────────────────────
BEGIN;

    -- Try inserting a duplicate USN — will violate UNIQUE constraint
    INSERT INTO student
        (usn, first_name, last_name, dob, program, admission_year, department_id)
    VALUES
        ('1CS22001', 'Duplicate', 'User', '2004-01-01', 'B.E. CS', 2022, 1);

ROLLBACK;
-- ↑ Transaction is fully rolled back.
-- '1CS22001' still belongs only to Arjun Sharma — no duplicate inserted.

SELECT usn, first_name, last_name
FROM   student
WHERE  usn = '1CS22001';
-- Should return exactly 1 row: Arjun Sharma.
