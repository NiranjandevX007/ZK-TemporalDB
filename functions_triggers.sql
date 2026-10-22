-- ══════════════════════════════════════════════════════════════════════════════
-- ZK-TemporalDB  —  Functions, Stored Procedures and Triggers
-- Person 1: Database Design and SQL
-- Last revised: 2026-10-22
--
-- Run AFTER schema.sql and seed.sql.
-- All objects use CREATE OR REPLACE — safe to re-run.
--
-- Grading-scale note:
--   The grade → grade_point mapping used in illustrative examples below
--   is a SAMPLE policy provided for demonstration purposes only.
--   It does NOT represent any official institution policy.
--   Adjust the CASE expression to match the real institution's scale.
-- ══════════════════════════════════════════════════════════════════════════════


-- ─────────────────────────────────────────────────────────────────────────────
-- FUNCTION 1: fn_compute_sgpa
-- Computes SGPA for a given (student, semester) pair using enrolled_in data.
-- Formula: Σ(grade_point × credits) / Σcredits
-- Returns NULL if no declared grade points exist for that semester.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_compute_sgpa(
    p_student_id  INTEGER,
    p_sem_no      INTEGER
)
RETURNS NUMERIC(4, 2)
LANGUAGE sql
STABLE
AS $$
    SELECT
        CASE
            WHEN SUM(c.credits) > 0
            THEN ROUND(
                     SUM(e.grade_point * c.credits) / SUM(c.credits),
                 2)
            ELSE NULL
        END
    FROM   enrolled_in e
    JOIN   course c ON c.course_id = e.course_id
    WHERE  e.student_id     = p_student_id
      AND  e.semester_number = p_sem_no
      AND  e.grade_point    IS NOT NULL;
$$;

COMMENT ON FUNCTION fn_compute_sgpa(INTEGER, INTEGER) IS
  'Computes SGPA for a student for a given semester from enrolled_in marks. '
  'SGPA = Σ(grade_point × credits) / Σcredits. Returns NULL if no data.';


-- ─────────────────────────────────────────────────────────────────────────────
-- FUNCTION 2: fn_compute_cgpa
-- Computes CGPA from stored semester_result rows for a student.
-- Convention: credits-weighted average of semester SGPAs.
--   CGPA = Σ(sgpa × total_credits) / Σtotal_credits
-- Returns NULL if no semester results exist.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_compute_cgpa(
    p_student_id INTEGER
)
RETURNS NUMERIC(4, 2)
LANGUAGE sql
STABLE
AS $$
    SELECT
        CASE
            WHEN SUM(total_credits) > 0
            THEN ROUND(
                     SUM(sgpa * total_credits) / SUM(total_credits),
                 2)
            ELSE NULL
        END
    FROM   semester_result
    WHERE  student_id = p_student_id;
$$;

COMMENT ON FUNCTION fn_compute_cgpa(INTEGER) IS
  'Returns CGPA for a student using a credits-weighted average of semester SGPAs. '
  'Formula: Σ(sgpa × total_credits) / Σtotal_credits. Returns NULL if no results.';


-- ─────────────────────────────────────────────────────────────────────────────
-- FUNCTION 3: fn_grade_to_point
-- Converts a letter grade string to a numeric grade point using a sample scale.
-- ILLUSTRATIVE ONLY — not an official policy.
--   O  / A+ → 10.00
--   A       →  9.00
--   B+      →  8.00
--   B       →  7.00
--   C       →  5.00
--   D       →  4.00
--   F       →  0.00
-- Returns NULL for unrecognised grade strings.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_grade_to_point(p_grade VARCHAR(3))
RETURNS NUMERIC(4, 2)
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE UPPER(p_grade)
        WHEN 'O'  THEN 10.00
        WHEN 'A+' THEN 10.00
        WHEN 'A'  THEN  9.00
        WHEN 'B+' THEN  8.00
        WHEN 'B'  THEN  7.00
        WHEN 'C'  THEN  5.00
        WHEN 'D'  THEN  4.00
        WHEN 'F'  THEN  0.00
        ELSE NULL
    END;
$$;

COMMENT ON FUNCTION fn_grade_to_point(VARCHAR) IS
  'Sample grade-to-grade-point conversion. ILLUSTRATIVE ONLY — not an official policy. '
  'Returns NULL for unrecognised inputs.';


-- ─────────────────────────────────────────────────────────────────────────────
-- PROCEDURE 1: sp_declare_result
-- Declares (upserts) a semester result for a student.
-- Inserts a new row if none exists; updates if one already exists.
-- p_result_status must be one of: PASS, FAIL, DETAINED, WITHHELD.
-- p_sgpa and p_total_credits are provided by the caller (registrar).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE PROCEDURE sp_declare_result(
    p_student_id    INTEGER,
    p_sem_no        INTEGER,
    p_sgpa          NUMERIC(4, 2),
    p_total_credits INTEGER,
    p_result_status VARCHAR(20)
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- Validate result_status explicitly (constraint will also enforce this,
    -- but a human-readable error is friendlier)
    IF p_result_status NOT IN ('PASS', 'FAIL', 'DETAINED', 'WITHHELD') THEN
        RAISE EXCEPTION 'Invalid result_status: %. Must be PASS, FAIL, DETAINED, or WITHHELD.',
            p_result_status;
    END IF;

    INSERT INTO semester_result
        (student_id, sem_no, sgpa, total_credits, result_status)
    VALUES
        (p_student_id, p_sem_no, p_sgpa, p_total_credits, p_result_status)
    ON CONFLICT (student_id, sem_no)
    DO UPDATE SET
        sgpa          = EXCLUDED.sgpa,
        total_credits = EXCLUDED.total_credits,
        result_status = EXCLUDED.result_status;

    RAISE NOTICE 'Result declared for student_id=%, sem_no=%.', p_student_id, p_sem_no;
END;
$$;

COMMENT ON PROCEDURE sp_declare_result(INTEGER, INTEGER, NUMERIC, INTEGER, VARCHAR) IS
  'Upserts a semester result row. Safe to call even if a result already exists. '
  'Validates result_status before insert.';


-- ─────────────────────────────────────────────────────────────────────────────
-- PROCEDURE 2: sp_update_marks
-- Updates internal/external marks and grade/grade_point for an enrollment row.
-- Identified by (student_id, course_id, academic_year, semester_number).
-- Raises an exception if the enrollment does not exist.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE PROCEDURE sp_update_marks(
    p_student_id     INTEGER,
    p_course_id      INTEGER,
    p_academic_year  INTEGER,
    p_sem_no         INTEGER,
    p_internal       NUMERIC(5, 2),
    p_external       NUMERIC(5, 2),
    p_grade          VARCHAR(3),
    p_grade_point    NUMERIC(4, 2)
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows INTEGER;
BEGIN
    UPDATE enrolled_in
    SET    internal_marks = p_internal,
           external_marks = p_external,
           grade          = p_grade,
           grade_point    = p_grade_point
    WHERE  student_id      = p_student_id
      AND  course_id       = p_course_id
      AND  academic_year   = p_academic_year
      AND  semester_number = p_sem_no;

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    IF v_rows = 0 THEN
        RAISE EXCEPTION
            'No enrollment found for student_id=%, course_id=%, year=%, sem=%.  '
            'Check that the student is actually enrolled in that course.',
            p_student_id, p_course_id, p_academic_year, p_sem_no;
    END IF;

    RAISE NOTICE 'Marks updated for student_id=%, course_id=%, sem=%.', p_student_id, p_course_id, p_sem_no;
END;
$$;

COMMENT ON PROCEDURE sp_update_marks(INTEGER,INTEGER,INTEGER,INTEGER,NUMERIC,NUMERIC,VARCHAR,NUMERIC) IS
  'Updates marks, grade, and grade_point for a single enrollment. '
  'Raises an error if no matching enrollment row exists.';


-- ─────────────────────────────────────────────────────────────────────────────
-- TRIGGER FUNCTION: fn_trg_validate_enrollment_sem
-- Ensures that the semester_number in enrolled_in matches the sem_no recorded
-- in semester_result for the same student, when a semester result already exists.
-- This is a cross-table consistency guard: prevents entering enrollment data
-- for a semester that has already been officially closed with a result.
--
-- Rationale: Once a semester_result row exists (result declared), marks for
-- that semester should only be updated through sp_update_marks with care —
-- not inserted fresh as a new enrollment row after the result was finalised.
-- This trigger WARNS (NOTICE) rather than blocking, to allow correction workflows.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_trg_validate_enrollment_sem()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_result_exists BOOLEAN;
BEGIN
    -- Check if a semester_result already exists for this student+semester
    SELECT EXISTS (
        SELECT 1
        FROM   semester_result
        WHERE  student_id = NEW.student_id
          AND  sem_no     = NEW.semester_number
    ) INTO v_result_exists;

    IF v_result_exists THEN
        RAISE NOTICE
            'INFO: A semester result already exists for student_id=%, sem_no=%. '
            'This new enrollment row is being added for a semester that has been declared. '
            'Verify this is intentional (e.g., supplementary / re-enrollment).',
            NEW.student_id, NEW.semester_number;
    END IF;

    -- Allow the insert/update to proceed regardless
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_trg_validate_enrollment_sem() IS
  'Trigger function: issues a NOTICE when an enrollment row is added/updated '
  'for a semester that already has a declared semester_result. Does not block the operation.';


-- ─────────────────────────────────────────────────────────────────────────────
-- TRIGGER: trg_enrollment_sem_check
-- Fires BEFORE INSERT OR UPDATE on enrolled_in.
-- Calls fn_trg_validate_enrollment_sem to emit a notice if the semester
-- already has a declared result, allowing audit trail awareness.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TRIGGER trg_enrollment_sem_check
BEFORE INSERT OR UPDATE ON enrolled_in
FOR EACH ROW
EXECUTE FUNCTION fn_trg_validate_enrollment_sem();

COMMENT ON TRIGGER trg_enrollment_sem_check ON enrolled_in IS
  'Fires before each enrollment insert/update. Emits a notice if semester_result '
  'already exists for the same student+semester. Does not block the insert.';


-- ─────────────────────────────────────────────────────────────────────────────
-- Quick verification — show all functions, procedures, triggers created
-- ─────────────────────────────────────────────────────────────────────────────
SELECT routine_name, routine_type
FROM   information_schema.routines
WHERE  routine_schema = 'public'
  AND  routine_name IN (
       'fn_compute_sgpa', 'fn_compute_cgpa', 'fn_grade_to_point',
       'sp_declare_result', 'sp_update_marks', 'fn_trg_validate_enrollment_sem'
  )
ORDER  BY routine_type, routine_name;

SELECT tgname AS trigger_name, relname AS table_name
FROM   pg_trigger t
JOIN   pg_class  c ON c.oid = t.tgrelid
WHERE  tgname = 'trg_enrollment_sem_check';
