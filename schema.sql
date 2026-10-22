-- ZK-TemporalDB: Database Schema
-- Person 1: Database Design and SQL
-- Last revised: 2026-10-22

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: department
-- Stores the academic departments in the institution.
-- Each department has a unique auto-generated ID, a unique name,
-- and the name of the current Head of Department (hod_name).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS department (
    department_id   INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL UNIQUE,
    hod_name        VARCHAR(100) NOT NULL
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: student
-- Stores core identity information for every registered student.
-- USN uniquely identifies a student institution-wide.
-- Name is stored as first_name + last_name (ER composite attribute).
-- admission_year validated 2000–2100.
-- current_cgpa is DERIVED (ER Design Note 4) — never stored here.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS student (
    student_id     INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usn            VARCHAR(20)  NOT NULL UNIQUE,
    first_name     VARCHAR(60)  NOT NULL,
    last_name      VARCHAR(60)  NOT NULL,
    dob            DATE         NOT NULL,
    email          VARCHAR(150) UNIQUE,
    program        VARCHAR(60)  NOT NULL,
    admission_year INTEGER      NOT NULL
                       CHECK (admission_year BETWEEN 2000 AND 2100),
    department_id  INTEGER      NOT NULL,

    -- current_cgpa is DERIVED per ER Design Note 4 — never stored here

    CONSTRAINT fk_student_department
        FOREIGN KEY (department_id)
        REFERENCES department(department_id)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: course
-- Represents subjects/courses offered by the institution.
-- course_code is the natural key (e.g. 'CS401').
-- credits 1–10; department_id links to the owning department.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS course (
    course_id      INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course_code    VARCHAR(20)  NOT NULL UNIQUE,
    course_name    VARCHAR(150) NOT NULL,
    credits        INTEGER      NOT NULL
                       CHECK (credits > 0 AND credits <= 10),
    department_id  INTEGER      NOT NULL,

    CONSTRAINT fk_course_department
        FOREIGN KEY (department_id)
        REFERENCES department(department_id)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: enrolled_in
-- Associative entity: one row = one student enrolled in one course
-- for one academic_year + semester_number.
--   academic_year   : INTEGER — starting calendar year (e.g. 2024 = 2024-25).
--   semester_number : 1–8 for a 4-year UG programme.
--   internal_marks  : 0–30  (ER: "carries marks" — confirmed 0–30).
--   external_marks  : 0–70  (ER: "carries marks" — confirmed 0–70).
--   grade           : letter grade, nullable until declared.
--   grade_point     : 0–10 scale, nullable until declared.
-- Marks/grade are nullable: enrollment precedes result declaration.
-- total_marks is DERIVED (internal + external) — not stored.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS enrolled_in (
    enrollment_id   INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id      INTEGER      NOT NULL,
    course_id       INTEGER      NOT NULL,
    academic_year   INTEGER      NOT NULL
                        CHECK (academic_year BETWEEN 2000 AND 2100),
    semester_number INTEGER      NOT NULL
                        CHECK (semester_number BETWEEN 1 AND 8),

    -- ER: "ENROLLED_IN carries marks, grade, grade point"
    internal_marks  NUMERIC(5,2) NULL
                        CONSTRAINT chk_internal_marks
                        CHECK (internal_marks IS NULL OR internal_marks BETWEEN 0 AND 30),
    external_marks  NUMERIC(5,2) NULL
                        CONSTRAINT chk_external_marks
                        CHECK (external_marks IS NULL OR external_marks BETWEEN 0 AND 70),
    grade           VARCHAR(3)   NULL,
    grade_point     NUMERIC(4,2) NULL
                        CONSTRAINT chk_grade_point
                        CHECK (grade_point IS NULL OR grade_point BETWEEN 0 AND 10),

    CONSTRAINT fk_enrollment_student
        FOREIGN KEY (student_id)
        REFERENCES student(student_id),

    CONSTRAINT fk_enrollment_course
        FOREIGN KEY (course_id)
        REFERENCES course(course_id),

    -- A student cannot enroll in the same course twice in the same semester/year
    CONSTRAINT uq_enrollment_unique
        UNIQUE (student_id, course_id, academic_year, semester_number)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: semester_result  (WEAK ENTITY identified by student + sem_no)
-- Records the academic outcome for one student for one complete semester.
-- Per-course details (marks, grade, grade_point) are in enrolled_in.
-- Identifying relationship: HAS_RESULT — STUDENT 1:N SEMESTER_RESULT.
-- Composite PK (student_id, sem_no) is the weak entity's identifying key.
--   sem_no        : partial key — semester number 1–8.
--   sgpa          : semester GPA on 0.00–10.00 scale.
--   total_credits : credits attempted this semester (must be > 0).
--   result_status : PASS, FAIL, DETAINED, or WITHHELD (confirmed).
-- cumulative_cgpa is DERIVED (ER Design Note 4) — not stored.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS semester_result (
    student_id    INTEGER      NOT NULL,
    sem_no        INTEGER      NOT NULL
                      CHECK (sem_no BETWEEN 1 AND 8),
    sgpa          NUMERIC(4,2) NOT NULL
                      CHECK (sgpa BETWEEN 0.00 AND 10.00),
    total_credits INTEGER      NOT NULL
                      CHECK (total_credits > 0),
    result_status VARCHAR(20)  NOT NULL
                      CHECK (result_status IN ('PASS', 'FAIL', 'DETAINED', 'WITHHELD')),

    -- Composite PK: weak entity identified by (student_id, sem_no)
    CONSTRAINT semester_result_pkey
        PRIMARY KEY (student_id, sem_no),

    CONSTRAINT fk_result_student
        FOREIGN KEY (student_id)
        REFERENCES student(student_id)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: system_user
-- Internal users of the system only: Faculty, Registrar, Admin.
-- VERIFIER is a separate ER entity (Person 2 scope) — not here.
-- STUDENT is a separate entity — students live in the student table.
-- NOTE: "system_user" is quoted because it is a reserved word in PostgreSQL.
--   username   : unique login handle.
--   role       : one of FACULTY, REGISTRAR, ADMIN (confirmed).
--   created_at : UTC audit timestamp.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "system_user" (
    user_id    INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username   VARCHAR(60)  NOT NULL UNIQUE,
    role       VARCHAR(30)  NOT NULL
                   CHECK (role IN ('FACULTY', 'REGISTRAR', 'ADMIN')),
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);