-- ══════════════════════════════════════════════════════════════════════════════
-- ZK-TemporalDB  —  Views
-- Person 1: Database Design and SQL
-- Last revised: 2026-10-22
--
-- Run AFTER schema.sql and seed.sql.
-- All views are CREATE OR REPLACE — safe to re-run.
-- ══════════════════════════════════════════════════════════════════════════════


-- ─────────────────────────────────────────────────────────────────────────────
-- VIEW 1: vw_student_profile
-- Student academic profiles — identity, department, and program information.
-- Useful for displaying a student's full profile in reports and applications.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_student_profile AS
SELECT
    s.student_id,
    s.usn,
    s.first_name,
    s.last_name,
    s.first_name || ' ' || s.last_name   AS full_name,
    s.dob,
    s.email,
    s.program,
    s.admission_year,
    d.department_name,
    d.hod_name                            AS department_hod
FROM   student s
INNER  JOIN department d ON d.department_id = s.department_id;

COMMENT ON VIEW vw_student_profile IS
  'Full student identity and department information. '
  'Joins student → department. Safe read-only view.';


-- ─────────────────────────────────────────────────────────────────────────────
-- VIEW 2: vw_course_enrollment
-- Course enrollment details including marks and grades per student.
-- Shows both declared and pending (NULL) mark rows.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_course_enrollment AS
SELECT
    e.enrollment_id,
    s.usn,
    s.first_name || ' ' || s.last_name            AS full_name,
    c.course_code,
    c.course_name,
    c.credits,
    d.department_name                              AS course_department,
    e.academic_year,
    e.semester_number,
    e.internal_marks,
    e.external_marks,
    -- Derived total — not stored, computed here
    CASE
        WHEN e.internal_marks IS NOT NULL AND e.external_marks IS NOT NULL
        THEN ROUND(e.internal_marks + e.external_marks, 2)
        ELSE NULL
    END                                            AS total_marks,
    e.grade,
    e.grade_point,
    -- Weighted GPA contribution for this course (numerator of SGPA)
    CASE
        WHEN e.grade_point IS NOT NULL
        THEN ROUND(e.grade_point * c.credits, 2)
        ELSE NULL
    END                                            AS weighted_gp_contribution,
    CASE
        WHEN e.grade IS NULL THEN 'Pending'
        ELSE 'Declared'
    END                                            AS result_status
FROM   enrolled_in e
INNER  JOIN student    s ON s.student_id  = e.student_id
INNER  JOIN course     c ON c.course_id   = e.course_id
INNER  JOIN department d ON d.department_id = c.department_id;

COMMENT ON VIEW vw_course_enrollment IS
  'Per-course enrollment with marks, grades, and derived total marks. '
  'result_status = Pending when grade is NULL.';


-- ─────────────────────────────────────────────────────────────────────────────
-- VIEW 3: vw_semester_results
-- Semester-level academic results per student per semester.
-- Joins semester_result → student → department.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_semester_results AS
SELECT
    sr.student_id,
    s.usn,
    s.first_name || ' ' || s.last_name  AS full_name,
    d.department_name,
    sr.sem_no                            AS semester_number,
    sr.sgpa,
    sr.total_credits,
    sr.result_status
FROM   semester_result sr
INNER  JOIN student    s ON s.student_id    = sr.student_id
INNER  JOIN department d ON d.department_id = s.department_id
ORDER  BY s.usn, sr.sem_no;

COMMENT ON VIEW vw_semester_results IS
  'Semester results with SGPA, credits, and status for each student. '
  'Ordered by USN then semester number.';


-- ─────────────────────────────────────────────────────────────────────────────
-- VIEW 4: vw_student_performance_summary
-- Per-student academic performance summary:
--   - Semesters completed (those with a declared semester_result row)
--   - Total credits earned
--   - Computed CGPA (credits-weighted average of SGPA values)
--   - Number of course enrollments
--   - Number of pending (undeclared) course results
-- CGPA Convention: Σ(sgpa × total_credits) / Σtotal_credits
--   (weighted by credits per semester — standard approach)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_student_performance_summary AS
SELECT
    s.student_id,
    s.usn,
    s.first_name || ' ' || s.last_name     AS full_name,
    d.department_name,
    s.program,
    -- Semester-level aggregates
    COUNT(DISTINCT sr.sem_no)               AS semesters_completed,
    COALESCE(SUM(sr.total_credits), 0)      AS total_credits_earned,
    -- Derived CGPA: credits-weighted average of SGPA (NULL if no results yet)
    CASE
        WHEN SUM(sr.total_credits) > 0
        THEN ROUND(
                 SUM(sr.sgpa * sr.total_credits) / SUM(sr.total_credits),
             2)
        ELSE NULL
    END                                     AS cgpa,
    -- Course-level aggregates
    COUNT(DISTINCT e.enrollment_id)         AS total_enrollments,
    COUNT(DISTINCT CASE WHEN e.grade IS NULL THEN e.enrollment_id END)
                                            AS pending_result_count
FROM   student s
INNER  JOIN department     d  ON d.department_id  = s.department_id
LEFT   JOIN semester_result sr ON sr.student_id   = s.student_id
LEFT   JOIN enrolled_in     e  ON e.student_id    = s.student_id
GROUP  BY s.student_id, s.usn, s.first_name, s.last_name, d.department_name, s.program
ORDER  BY cgpa DESC NULLS LAST, s.usn;

COMMENT ON VIEW vw_student_performance_summary IS
  'Overall academic performance summary per student. '
  'CGPA is derived (credits-weighted average of semester SGPAs) — not stored. '
  'Students without any semester results show cgpa = NULL.';
