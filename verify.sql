-- ══════════════════════════════════════════════════════════════════════════════
-- ZK-TemporalDB  —  Verification Suite
-- Person 1: Database Design and SQL
-- Last revised: 2026-10-22
--
-- Run AFTER: schema.sql, seed.sql, views.sql, functions_triggers.sql,
--            transactions_indexing.sql
--
-- This script verifies schema correctness, constraint enforcement,
-- data integrity, function outputs, and view execution.
-- All negative tests use BEGIN / ROLLBACK so no bad data is retained.
-- ══════════════════════════════════════════════════════════════════════════════

\echo '═══════════════════════════════════════════════════════'
\echo ' ZK-TemporalDB  Verification Suite'
\echo '═══════════════════════════════════════════════════════'

-- ─────────────────────────────────────────────────────────────────────────────
-- V1 : All six tables exist
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '── V1: Table existence ──────────────────────────────────'
SELECT table_name,
       CASE WHEN table_name IN
            ('department','student','course','enrolled_in','semester_result','system_user')
            THEN 'EXPECTED ✓'
            ELSE 'UNEXPECTED'
       END AS check_result
FROM   information_schema.tables
WHERE  table_schema = 'public'
  AND  table_type   = 'BASE TABLE'
ORDER  BY table_name;

-- ─────────────────────────────────────────────────────────────────────────────
-- V2 : Primary key structure
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '── V2: Primary keys ─────────────────────────────────────'
SELECT tc.table_name, STRING_AGG(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS pk_columns
FROM   information_schema.table_constraints tc
JOIN   information_schema.key_column_usage  kcu
       ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema    = kcu.table_schema
WHERE  tc.constraint_type = 'PRIMARY KEY'
  AND  tc.table_schema    = 'public'
GROUP  BY tc.table_name
ORDER  BY tc.table_name;

-- ─────────────────────────────────────────────────────────────────────────────
-- V3 : Foreign keys
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '── V3: Foreign keys ─────────────────────────────────────'
SELECT tc.table_name       AS from_table,
       kcu.column_name     AS fk_column,
       ccu.table_name      AS to_table,
       ccu.column_name     AS to_column
FROM   information_schema.table_constraints tc
JOIN   information_schema.key_column_usage       kcu ON tc.constraint_name = kcu.constraint_name
JOIN   information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
WHERE  tc.constraint_type = 'FOREIGN KEY'
  AND  tc.table_schema    = 'public'
ORDER  BY tc.table_name, kcu.column_name;

-- ─────────────────────────────────────────────────────────────────────────────
-- V4 : CHECK constraints
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '── V4: CHECK constraints ────────────────────────────────'
SELECT conname AS constraint_name,
       conrelid::regclass AS table_name,
       pg_get_constraintdef(oid) AS definition
FROM   pg_constraint
WHERE  contype = 'c'
  AND  conrelid IN (
       SELECT oid FROM pg_class
       WHERE  relname IN ('department','student','course','enrolled_in','semester_result','system_user')
       )
ORDER  BY table_name, constraint_name;

-- ─────────────────────────────────────────────────────────────────────────────
-- V5 : Row counts
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '── V5: Row counts ───────────────────────────────────────'
SELECT 'department'      AS table_name, COUNT(*) AS rows FROM department       UNION ALL
SELECT 'student',                       COUNT(*) FROM student                   UNION ALL
SELECT 'course',                        COUNT(*) FROM course                    UNION ALL
SELECT 'enrolled_in',                   COUNT(*) FROM enrolled_in               UNION ALL
SELECT 'semester_result',               COUNT(*) FROM semester_result           UNION ALL
SELECT 'system_user',                   COUNT(*) FROM "system_user"
ORDER BY table_name;

-- ─────────────────────────────────────────────────────────────────────────────
-- V6 : Foreign key integrity — no broken references
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '── V6: Foreign key integrity ────────────────────────────'

-- student.department_id → department.department_id
SELECT 'student→department' AS check_name,
       COUNT(*) AS broken_refs
FROM   student s
WHERE  NOT EXISTS (SELECT 1 FROM department d WHERE d.department_id = s.department_id);

-- course.department_id → department.department_id
SELECT 'course→department' AS check_name,
       COUNT(*) AS broken_refs
FROM   course c
WHERE  NOT EXISTS (SELECT 1 FROM department d WHERE d.department_id = c.department_id);

-- enrolled_in.student_id → student.student_id
SELECT 'enrolled_in→student' AS check_name,
       COUNT(*) AS broken_refs
FROM   enrolled_in e
WHERE  NOT EXISTS (SELECT 1 FROM student s WHERE s.student_id = e.student_id);

-- enrolled_in.course_id → course.course_id
SELECT 'enrolled_in→course' AS check_name,
       COUNT(*) AS broken_refs
FROM   enrolled_in e
WHERE  NOT EXISTS (SELECT 1 FROM course c WHERE c.course_id = e.course_id);

-- semester_result.student_id → student.student_id
SELECT 'semester_result→student' AS check_name,
       COUNT(*) AS broken_refs
FROM   semester_result sr
WHERE  NOT EXISTS (SELECT 1 FROM student s WHERE s.student_id = sr.student_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- V7 : Constraint enforcement — negative tests (all inside ROLLBACK)
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '── V7: Constraint rejection tests ───────────────────────'

-- V7a: Internal marks > 30 must be rejected
\echo 'V7a: internal_marks=31 should be rejected...'
BEGIN;
    INSERT INTO enrolled_in (student_id, course_id, academic_year, semester_number, internal_marks)
    VALUES (1, 1, 2099, 1, 31.00);
ROLLBACK;
\echo 'V7a: ROLLBACK complete (error above = PASS)'

-- V7b: External marks > 70 must be rejected
\echo 'V7b: external_marks=71 should be rejected...'
BEGIN;
    INSERT INTO enrolled_in (student_id, course_id, academic_year, semester_number, external_marks)
    VALUES (1, 1, 2099, 1, 71.00);
ROLLBACK;
\echo 'V7b: ROLLBACK complete (error above = PASS)'

-- V7c: Invalid result_status must be rejected
\echo 'V7c: result_status=HONOURS should be rejected...'
BEGIN;
    INSERT INTO semester_result (student_id, sem_no, sgpa, total_credits, result_status)
    VALUES (1, 8, 9.00, 8, 'HONOURS');
ROLLBACK;
\echo 'V7c: ROLLBACK complete (error above = PASS)'

-- V7d: Invalid system_user role must be rejected
\echo 'V7d: role=STUDENT should be rejected...'
BEGIN;
    INSERT INTO "system_user" (username, role)
    VALUES ('test.student', 'STUDENT');
ROLLBACK;
\echo 'V7d: ROLLBACK complete (error above = PASS)'

-- V7e: Duplicate USN must be rejected
\echo 'V7e: Duplicate USN 1CS22001 should be rejected...'
BEGIN;
    INSERT INTO student (usn, first_name, last_name, dob, program, admission_year, department_id)
    VALUES ('1CS22001', 'Dup', 'User', '2000-01-01', 'B.E.', 2022, 1);
ROLLBACK;
\echo 'V7e: ROLLBACK complete (error above = PASS)'

-- V7f: Duplicate enrollment (same student, course, year, sem) must be rejected
\echo 'V7f: Duplicate enrollment should be rejected...'
BEGIN;
    INSERT INTO enrolled_in (student_id, course_id, academic_year, semester_number)
    VALUES (1, 1, 2022, 1);   -- already exists from seed
ROLLBACK;
\echo 'V7f: ROLLBACK complete (error above = PASS)'

-- ─────────────────────────────────────────────────────────────────────────────
-- V8 : Views execute and return data
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '── V8: Views ────────────────────────────────────────────'

SELECT 'vw_student_profile'          AS view_name, COUNT(*) AS rows FROM vw_student_profile         UNION ALL
SELECT 'vw_course_enrollment',                     COUNT(*) FROM vw_course_enrollment                UNION ALL
SELECT 'vw_semester_results',                      COUNT(*) FROM vw_semester_results                 UNION ALL
SELECT 'vw_student_performance_summary',           COUNT(*) FROM vw_student_performance_summary
ORDER  BY view_name;

-- ─────────────────────────────────────────────────────────────────────────────
-- V9 : Functions return expected values
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '── V9: Function outputs ─────────────────────────────────'

-- fn_compute_sgpa: Arjun Sharma (student_id=1) Sem 1 → expect 9.50
SELECT 'fn_compute_sgpa(1,1)' AS test,
       fn_compute_sgpa(1, 1)  AS result,
       '9.50'::NUMERIC(4,2)   AS expected,
       fn_compute_sgpa(1, 1) = 9.50 AS pass;

-- fn_compute_cgpa: Arjun (student_id=1) has only sem_no=1 (sgpa=9.50, 8 credits)
-- → CGPA = 9.50/8 × 8 = 9.50  (single semester; weighted average = that semester's SGPA)
SELECT 'fn_compute_cgpa(1)'  AS test,
       fn_compute_cgpa(1)    AS result,
       '9.50'::NUMERIC(4,2)  AS expected,
       fn_compute_cgpa(1) = 9.50 AS pass;

-- fn_grade_to_point
SELECT 'fn_grade_to_point(A+)' AS test, fn_grade_to_point('A+') AS result, 10.00::NUMERIC(4,2) AS expected UNION ALL
SELECT 'fn_grade_to_point(B)',          fn_grade_to_point('B'),  7.00::NUMERIC(4,2)             UNION ALL
SELECT 'fn_grade_to_point(F)',          fn_grade_to_point('F'),  0.00::NUMERIC(4,2);

-- ─────────────────────────────────────────────────────────────────────────────
-- V10 : SGPA consistency — computed SGPA matches stored SGPA in semester_result
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '── V10: SGPA consistency ────────────────────────────────'
SELECT s.usn,
       sr.sem_no,
       sr.sgpa                       AS stored_sgpa,
       fn_compute_sgpa(sr.student_id, sr.sem_no) AS computed_sgpa,
       sr.sgpa = fn_compute_sgpa(sr.student_id, sr.sem_no) AS match
FROM   semester_result sr
JOIN   student s ON s.student_id = sr.student_id
WHERE  sr.sem_no = 1        -- Sem 1 has complete grade data from seed
ORDER  BY s.usn;

-- ─────────────────────────────────────────────────────────────────────────────
-- V11 : Pending marks query returns expected rows
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '── V11: Pending marks ───────────────────────────────────'
SELECT s.usn, c.course_code, e.semester_number
FROM   enrolled_in e
JOIN   student s ON s.student_id = e.student_id
JOIN   course  c ON c.course_id  = e.course_id
WHERE  e.grade IS NULL
ORDER  BY s.usn;

-- ─────────────────────────────────────────────────────────────────────────────
-- V12 : Trigger exists and is active
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '── V12: Trigger status ──────────────────────────────────'
SELECT tgname AS trigger_name,
       relname AS table_name,
       CASE tgenabled WHEN 'O' THEN 'ENABLED' ELSE 'DISABLED' END AS status
FROM   pg_trigger t
JOIN   pg_class   c ON c.oid = t.tgrelid
WHERE  tgname = 'trg_enrollment_sem_check';

-- ─────────────────────────────────────────────────────────────────────────────
-- V13 : Indexes present
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '── V13: Custom indexes ──────────────────────────────────'
SELECT indexname, tablename
FROM   pg_indexes
WHERE  schemaname = 'public'
  AND  indexname  LIKE 'idx_%'
ORDER  BY tablename, indexname;

\echo ''
\echo '═══════════════════════════════════════════════════════'
\echo ' Verification complete.'
\echo ' All V7 tests should show ERROR above their ROLLBACK line.'
\echo ' All other tests should show sensible row counts / TRUE values.'
\echo '═══════════════════════════════════════════════════════'
