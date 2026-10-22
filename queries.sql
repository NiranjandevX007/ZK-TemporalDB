-- ══════════════════════════════════════════════════════════════════════════════
-- ZK-TemporalDB  —  Demonstration Queries
-- Person 1: Database Design and SQL
-- Last revised: 2026-10-22
--
-- Run after seed.sql has been loaded.
-- All queries read-only (SELECT only); safe to run repeatedly.
-- ══════════════════════════════════════════════════════════════════════════════


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 1 : Basic SELECT, WHERE, ORDER BY, DISTINCT
-- ─────────────────────────────────────────────────────────────────────────────

-- Q1.1 — All departments
SELECT department_id, department_name, hod_name
FROM   department
ORDER  BY department_name;

-- Q1.2 — All students, ordered by USN
SELECT student_id, usn, first_name, last_name, program, admission_year
FROM   student
ORDER  BY usn;

-- Q1.3 — Students admitted in 2022
SELECT usn, first_name, last_name, program
FROM   student
WHERE  admission_year = 2022
ORDER  BY last_name;

-- Q1.4 — Courses with 4 or more credits
SELECT course_code, course_name, credits
FROM   course
WHERE  credits >= 4
ORDER  BY credits DESC, course_code;

-- Q1.5 — DISTINCT programs offered across all students
SELECT DISTINCT program
FROM   student
ORDER  BY program;

-- Q1.6 — Students without a registered email (NULL email)
SELECT usn, first_name, last_name
FROM   student
WHERE  email IS NULL;

-- Q1.7 — System users of role FACULTY
SELECT username, role, created_at
FROM   system_user
WHERE  role = 'FACULTY'
ORDER  BY username;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 2 : Aggregate Functions — COUNT, SUM, AVG, MIN, MAX
-- ─────────────────────────────────────────────────────────────────────────────

-- Q2.1 — Total number of students
SELECT COUNT(*) AS total_students
FROM   student;

-- Q2.2 — Average, minimum and maximum credits across all courses
SELECT AVG(credits) AS avg_credits,
       MIN(credits) AS min_credits,
       MAX(credits) AS max_credits
FROM   course;

-- Q2.3 — Total, average and count of internal marks declared so far
--        (NULL rows represent pending marks and are excluded by aggregate functions)
SELECT COUNT(internal_marks) AS declared_count,
       SUM(internal_marks)   AS total_internal,
       AVG(internal_marks)   AS avg_internal,
       MIN(internal_marks)   AS min_internal,
       MAX(internal_marks)   AS max_internal
FROM   enrolled_in;

-- Q2.4 — Total and average external marks
SELECT COUNT(external_marks) AS declared_count,
       AVG(external_marks)   AS avg_external,
       MIN(external_marks)   AS min_external,
       MAX(external_marks)   AS max_external
FROM   enrolled_in;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 3 : GROUP BY and HAVING
-- ─────────────────────────────────────────────────────────────────────────────

-- Q3.1 — Number of students per department
SELECT d.department_name,
       COUNT(s.student_id) AS student_count
FROM   department d
LEFT   JOIN student s ON s.department_id = d.department_id
GROUP  BY d.department_name
ORDER  BY student_count DESC;

-- Q3.2 — Number of courses per department
SELECT d.department_name,
       COUNT(c.course_id) AS course_count
FROM   department d
LEFT   JOIN course c ON c.department_id = d.department_id
GROUP  BY d.department_name
ORDER  BY course_count DESC;

-- Q3.3 — Average grade point per course (only courses with declared grades)
SELECT c.course_code,
       c.course_name,
       ROUND(AVG(e.grade_point), 2) AS avg_grade_point
FROM   enrolled_in e
JOIN   course c ON c.course_id = e.course_id
WHERE  e.grade_point IS NOT NULL
GROUP  BY c.course_id, c.course_code, c.course_name
ORDER  BY avg_grade_point DESC;

-- Q3.4 — Courses with average grade point below 7 (HAVING filters groups)
SELECT c.course_code,
       c.course_name,
       ROUND(AVG(e.grade_point), 2) AS avg_grade_point
FROM   enrolled_in e
JOIN   course c ON c.course_id = e.course_id
WHERE  e.grade_point IS NOT NULL
GROUP  BY c.course_id, c.course_code, c.course_name
HAVING AVG(e.grade_point) < 7
ORDER  BY avg_grade_point;

-- Q3.5 — System users grouped by role
SELECT role, COUNT(*) AS user_count
FROM   system_user
GROUP  BY role
ORDER  BY role;

-- Q3.6 — Semester result counts by result_status
SELECT result_status, COUNT(*) AS count
FROM   semester_result
GROUP  BY result_status
ORDER  BY count DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 4 : INNER JOIN and LEFT JOIN
-- ─────────────────────────────────────────────────────────────────────────────

-- Q4.1 — INNER JOIN: students with their department names
SELECT s.usn,
       s.first_name || ' ' || s.last_name AS full_name,
       d.department_name,
       s.program
FROM   student s
INNER  JOIN department d ON d.department_id = s.department_id
ORDER  BY s.usn;

-- Q4.2 — INNER JOIN: enrollment details — who took which course
SELECT s.usn,
       s.first_name || ' ' || s.last_name AS full_name,
       c.course_code,
       c.course_name,
       e.semester_number,
       e.academic_year
FROM   enrolled_in e
INNER  JOIN student s ON s.student_id = e.student_id
INNER  JOIN course  c ON c.course_id  = e.course_id
ORDER  BY s.usn, e.semester_number, c.course_code;

-- Q4.3 — INNER JOIN: marks and grades per student per course
SELECT s.usn,
       s.first_name || ' ' || s.last_name AS full_name,
       c.course_code,
       e.internal_marks,
       e.external_marks,
       -- Derived total (not stored)
       (COALESCE(e.internal_marks, 0) + COALESCE(e.external_marks, 0)) AS total_marks,
       e.grade,
       e.grade_point
FROM   enrolled_in e
INNER  JOIN student s ON s.student_id = e.student_id
INNER  JOIN course  c ON c.course_id  = e.course_id
WHERE  e.grade IS NOT NULL          -- only declared results
ORDER  BY s.usn, c.course_code;

-- Q4.4 — LEFT JOIN: all departments and their students (departments with no students appear)
SELECT d.department_name,
       s.usn,
       s.first_name || ' ' || s.last_name AS full_name
FROM   department d
LEFT   JOIN student s ON s.department_id = d.department_id
ORDER  BY d.department_name, s.usn;

-- Q4.5 — LEFT JOIN: all students and their semester-1 result (students without a result show NULL)
SELECT s.usn,
       s.first_name || ' ' || s.last_name AS full_name,
       sr.sem_no,
       sr.sgpa,
       sr.result_status
FROM   student s
LEFT   JOIN semester_result sr
         ON sr.student_id = s.student_id AND sr.sem_no = 1
ORDER  BY s.usn;

-- Q4.6 — Three-way join: course details with department names
SELECT c.course_code,
       c.course_name,
       c.credits,
       d.department_name
FROM   course c
INNER  JOIN department d ON d.department_id = c.department_id
ORDER  BY d.department_name, c.course_code;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 5 : Subqueries
-- ─────────────────────────────────────────────────────────────────────────────

-- Q5.1 — Students whose Semester 1 SGPA is above the cohort average
--         (subquery computes the average SGPA for sem_no = 1)
SELECT s.usn,
       s.first_name || ' ' || s.last_name AS full_name,
       sr.sgpa
FROM   semester_result sr
INNER  JOIN student s ON s.student_id = sr.student_id
WHERE  sr.sem_no = 1
  AND  sr.sgpa > (
           SELECT AVG(sgpa)
           FROM   semester_result
           WHERE  sem_no = 1
       )
ORDER  BY sr.sgpa DESC;

-- Q5.2 — Students who are enrolled in at least one course with pending marks
SELECT DISTINCT s.usn,
       s.first_name || ' ' || s.last_name AS full_name
FROM   student s
WHERE  s.student_id IN (
           SELECT student_id
           FROM   enrolled_in
           WHERE  internal_marks IS NULL
              OR  external_marks IS NULL
       )
ORDER  BY s.usn;

-- Q5.3 — Courses that no student is currently enrolled in
SELECT c.course_code, c.course_name
FROM   course c
WHERE  c.course_id NOT IN (
           SELECT DISTINCT course_id
           FROM   enrolled_in
       );

-- Q5.4 — Students whose grade point in any course is below the overall course average
SELECT s.usn,
       s.first_name || ' ' || s.last_name AS full_name,
       c.course_code,
       e.grade_point,
       ROUND((SELECT AVG(e2.grade_point)
              FROM   enrolled_in e2
              WHERE  e2.course_id = e.course_id
                AND  e2.grade_point IS NOT NULL), 2) AS course_avg_gp
FROM   enrolled_in e
INNER  JOIN student s ON s.student_id = e.student_id
INNER  JOIN course  c ON c.course_id  = e.course_id
WHERE  e.grade_point IS NOT NULL
  AND  e.grade_point < (
           SELECT AVG(e2.grade_point)
           FROM   enrolled_in e2
           WHERE  e2.course_id = e.course_id
             AND  e2.grade_point IS NOT NULL
       )
ORDER  BY s.usn, c.course_code;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 6 : Pending Marks
-- ─────────────────────────────────────────────────────────────────────────────

-- Q6.1 — All enrollments where internal or external marks are still pending
SELECT s.usn,
       s.first_name || ' ' || s.last_name AS full_name,
       c.course_code,
       e.semester_number,
       e.academic_year,
       e.internal_marks,
       e.external_marks
FROM   enrolled_in e
INNER  JOIN student s ON s.student_id = e.student_id
INNER  JOIN course  c ON c.course_id  = e.course_id
WHERE  e.internal_marks IS NULL
   OR  e.external_marks IS NULL
ORDER  BY s.usn, c.course_code;

-- Q6.2 — Count of pending enrollments per student
SELECT s.usn,
       s.first_name || ' ' || s.last_name AS full_name,
       COUNT(*) AS pending_enrollments
FROM   enrolled_in e
INNER  JOIN student s ON s.student_id = e.student_id
WHERE  e.grade IS NULL
GROUP  BY s.student_id, s.usn, s.first_name, s.last_name
ORDER  BY pending_enrollments DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 7 : Derived Calculations
-- ─────────────────────────────────────────────────────────────────────────────

-- Q7.1 — Total marks per enrollment (internal + external) — derived, not stored
SELECT s.usn,
       c.course_code,
       e.internal_marks,
       e.external_marks,
       ROUND(COALESCE(e.internal_marks, 0) + COALESCE(e.external_marks, 0), 2) AS total_marks
FROM   enrolled_in e
INNER  JOIN student s ON s.student_id = e.student_id
INNER  JOIN course  c ON c.course_id  = e.course_id
ORDER  BY s.usn, c.course_code;

-- Q7.2 — Course-level weighted GPA contribution  (grade_point × credits)
--         This is the numerator component for SGPA computation.
SELECT s.usn,
       c.course_code,
       c.credits,
       e.grade_point,
       ROUND(e.grade_point * c.credits, 2) AS weighted_gp_contribution
FROM   enrolled_in e
INNER  JOIN student s ON s.student_id = e.student_id
INNER  JOIN course  c ON c.course_id  = e.course_id
WHERE  e.grade_point IS NOT NULL
ORDER  BY s.usn, c.course_code;

-- Q7.3 — Semester SGPA calculated on-the-fly from grade points and credits
--         SGPA = Σ(grade_point × credits) / Σcredits
--         (Verify these match the stored sgpa in semester_result)
SELECT s.usn,
       s.first_name || ' ' || s.last_name AS full_name,
       e.semester_number,
       ROUND(
           SUM(e.grade_point * c.credits) / SUM(c.credits),
       2) AS computed_sgpa,
       SUM(c.credits) AS credits_attempted
FROM   enrolled_in e
INNER  JOIN student s ON s.student_id = e.student_id
INNER  JOIN course  c ON c.course_id  = e.course_id
WHERE  e.grade_point IS NOT NULL
GROUP  BY s.student_id, s.usn, s.first_name, s.last_name, e.semester_number
ORDER  BY s.usn, e.semester_number;

-- Q7.4 — CGPA calculated from stored semester SGPA values
--         Convention: CGPA = Σ(sgpa × total_credits) / Σtotal_credits
--         (weighted average across semesters by total credits each semester)
--         NOTE: This is a conventional weighted-average formula; the actual
--         institution may use a simple average. Adjust the formula if required.
SELECT s.usn,
       s.first_name || ' ' || s.last_name AS full_name,
       COUNT(sr.sem_no)   AS semesters_completed,
       SUM(sr.total_credits) AS total_credits_earned,
       ROUND(
           SUM(sr.sgpa * sr.total_credits) / SUM(sr.total_credits),
       2) AS computed_cgpa
FROM   semester_result sr
INNER  JOIN student s ON s.student_id = sr.student_id
GROUP  BY s.student_id, s.usn, s.first_name, s.last_name
ORDER  BY computed_cgpa DESC;

-- Q7.5 — Simple (unweighted) average SGPA as an alternative CGPA formula
--         Some institutions use a plain average of semester SGPAs.
SELECT s.usn,
       s.first_name || ' ' || s.last_name AS full_name,
       ROUND(AVG(sr.sgpa), 2)             AS simple_avg_cgpa
FROM   semester_result sr
INNER  JOIN student s ON s.student_id = sr.student_id
GROUP  BY s.student_id, s.usn, s.first_name, s.last_name
ORDER  BY simple_avg_cgpa DESC;
