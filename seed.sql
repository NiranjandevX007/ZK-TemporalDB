-- ══════════════════════════════════════════════════════════════════════════════
-- ZK-TemporalDB  —  Sample / Seed Data
-- Person 1: Database Design and SQL
-- Created : 2026-10-22
--
-- Dataset summary
--   • 3 departments
--   • 5 students  (spread across two departments; 1 in a third)
--   • 6 courses   (2–3 per department)
--   • 12 enrollments across Semester 1 and Semester 2
--   • 5 semester_result rows  (one per student for Semester 1)
--   • 4 system_user rows      (2 Faculty, 1 Registrar, 1 Admin)
--
-- All inserts use explicit column lists.
-- Runs inside a single transaction; rolls back fully on any error.
-- ══════════════════════════════════════════════════════════════════════════════

\set ON_ERROR_STOP on

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. DEPARTMENT  (3 rows)
--    department_id is GENERATED ALWAYS — never listed in INSERT.
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO department (department_name, hod_name) VALUES
    ('Computer Science and Engineering', 'Dr. Ramesh Kulkarni'),  -- id = 1
    ('Electronics and Communication',   'Dr. Priya Nair'),        -- id = 2
    ('Mathematics',                     'Dr. Suresh Iyer');       -- id = 3


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. STUDENT  (5 rows)
--    USN format: <branch-code><year><serial>, e.g. 1CS22001.
--    admission_year ∈ [2000, 2100]  ✓
--    department_id references department  ✓
--    email is nullable; one student has no email on record.
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO student
    (usn,        first_name, last_name, dob,          email,                          program,                            admission_year, department_id)
VALUES
    ('1CS22001', 'Arjun',    'Sharma',  '2004-03-15', 'arjun.sharma@college.edu',     'B.E. Computer Science',            2022,           1),
    ('1CS22002', 'Meera',    'Pillai',  '2003-11-28', 'meera.pillai@college.edu',     'B.E. Computer Science',            2022,           1),
    ('1CS22003', 'Karthik',  'Reddy',   '2004-07-04', 'karthik.reddy@college.edu',    'B.E. Computer Science',            2022,           1),
    ('1EC22001', 'Sneha',    'Joshi',   '2004-01-19', 'sneha.joshi@college.edu',      'B.E. Electronics & Communication', 2022,           2),
    ('1EC22002', 'Rohan',    'Menon',   '2003-09-30', NULL,                           'B.E. Electronics & Communication', 2022,           2);
-- Note: Rohan Menon has no email on record (nullable column).


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. COURSE  (6 rows)
--    credits ∈ [1, 10]  ✓
--    department_id references department  ✓
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO course (course_code, course_name, credits, department_id) VALUES
    -- CS department courses
    ('CS101', 'Introduction to Programming',          4, 1),  -- course_id = 1
    ('CS102', 'Data Structures and Algorithms',       4, 1),  -- course_id = 2
    ('CS201', 'Database Management Systems',          3, 1),  -- course_id = 3
    -- EC department courses
    ('EC101', 'Basic Electronics',                    4, 2),  -- course_id = 4
    ('EC102', 'Digital Logic Design',                 4, 2),  -- course_id = 5
    -- Mathematics (service course, used by both branches)
    ('MA101', 'Engineering Mathematics I',            4, 3);  -- course_id = 6


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. ENROLLED_IN  (12 rows)
--
--    Semester 1  (academic_year = 2022, semester_number = 1)
--      CS students: CS101, MA101               — marks & grades declared
--      EC students: EC101, MA101               — marks & grades declared
--
--    Semester 2  (academic_year = 2022, semester_number = 2)
--      CS students: CS102, CS201               — enrolled; results pending (NULL)
--      EC students: EC102                      — enrolled; results pending (NULL)
--
--    Mark limits  ✓
--      internal_marks : 0–30
--      external_marks : 0–70
--      grade_point    : 0–10
--
--    Unique constraint: (student_id, course_id, academic_year, semester_number) ✓
-- ─────────────────────────────────────────────────────────────────────────────

-- ── Semester 1 — CS students ──────────────────────────────────────────────────
INSERT INTO enrolled_in
    (student_id, course_id, academic_year, semester_number, internal_marks, external_marks, grade, grade_point)
VALUES
    -- Arjun Sharma  (student_id = 1)
    (1, 1, 2022, 1, 28.00, 62.00, 'A+',  10.00),   -- CS101
    (1, 6, 2022, 1, 25.00, 58.00, 'A',    9.00),   -- MA101

    -- Meera Pillai  (student_id = 2)
    (2, 1, 2022, 1, 22.00, 50.00, 'B+',   8.00),   -- CS101
    (2, 6, 2022, 1, 20.00, 45.00, 'B',    7.00),   -- MA101

    -- Karthik Reddy (student_id = 3)
    (3, 1, 2022, 1, 15.00, 30.00, 'C',    5.00),   -- CS101  (borderline pass)
    (3, 6, 2022, 1, 12.00, 25.00, 'D',    4.00);   -- MA101  (borderline pass)

-- ── Semester 1 — EC students ──────────────────────────────────────────────────
INSERT INTO enrolled_in
    (student_id, course_id, academic_year, semester_number, internal_marks, external_marks, grade, grade_point)
VALUES
    -- Sneha Joshi   (student_id = 4)
    (4, 4, 2022, 1, 27.00, 60.00, 'A+', 10.00),    -- EC101
    (4, 6, 2022, 1, 26.00, 55.00, 'A',   9.00),    -- MA101

    -- Rohan Menon   (student_id = 5)
    (5, 4, 2022, 1, 18.00, 35.00, 'C',   5.00),    -- EC101
    (5, 6, 2022, 1, 14.00, 28.00, 'D',   4.00);    -- MA101

-- ── Semester 2 — results not yet declared (NULLs) ─────────────────────────────
INSERT INTO enrolled_in
    (student_id, course_id, academic_year, semester_number, internal_marks, external_marks, grade, grade_point)
VALUES
    -- Arjun Sharma  — CS102
    (1, 2, 2022, 2, NULL, NULL, NULL, NULL),
    -- Meera Pillai  — CS102
    (2, 2, 2022, 2, NULL, NULL, NULL, NULL);


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. SEMESTER_RESULT  (5 rows — one per student, Semester 1 only)
--
--    Composite PK (student_id, sem_no); must not duplicate  ✓
--    sgpa    : 0.00–10.00   ✓
--    total_credits > 0       ✓
--    result_status IN ('PASS','FAIL','DETAINED','WITHHELD')  ✓
--
--    SGPA calculation note (for viva):
--      SGPA = Σ(grade_point × credits) / Σcredits
--      Arjun:   (10×4 + 9×4) / 8 = 76/8 = 9.50
--      Meera:   (8×4  + 7×4) / 8 = 60/8 = 7.50
--      Karthik: (5×4  + 4×4) / 8 = 36/8 = 4.50  — PASS (passes both)
--      Sneha:   (10×4 + 9×4) / 8 = 76/8 = 9.50
--      Rohan:   (5×4  + 4×4) / 8 = 36/8 = 4.50  — PASS (passes both)
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO semester_result (student_id, sem_no, sgpa, total_credits, result_status) VALUES
    (1, 1,  9.50, 8, 'PASS'),   -- Arjun  Sharma
    (2, 1,  7.50, 8, 'PASS'),   -- Meera  Pillai
    (3, 1,  4.50, 8, 'PASS'),   -- Karthik Reddy  (both courses passed — C/D)
    (4, 1,  9.50, 8, 'PASS'),   -- Sneha  Joshi
    (5, 1,  4.50, 8, 'PASS');   -- Rohan  Menon


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. SYSTEM_USER  (4 rows)
--    role IN ('FACULTY', 'REGISTRAR', 'ADMIN')  ✓
--    username must be UNIQUE  ✓
--    created_at defaults to NOW() — not overridden here.
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO "system_user" (username, role) VALUES
    ('faculty.ramesh',     'FACULTY'),    -- HOD / Faculty, CS dept
    ('faculty.priya',      'FACULTY'),    -- HOD / Faculty, EC dept
    ('registrar.office',   'REGISTRAR'),  -- Academic registrar
    ('admin.superuser',    'ADMIN');      -- System administrator


COMMIT;

-- ─────────────────────────────────────────────────────────────────────────────
-- Quick sanity check — run after seeding to confirm row counts
-- ─────────────────────────────────────────────────────────────────────────────
SELECT 'department'      AS table_name, COUNT(*) AS rows FROM department
UNION ALL
SELECT 'student',                        COUNT(*) FROM student
UNION ALL
SELECT 'course',                         COUNT(*) FROM course
UNION ALL
SELECT 'enrolled_in',                    COUNT(*) FROM enrolled_in
UNION ALL
SELECT 'semester_result',                COUNT(*) FROM semester_result
UNION ALL
SELECT 'system_user',                    COUNT(*) FROM "system_user"
ORDER BY table_name;
