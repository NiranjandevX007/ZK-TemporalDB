# ZK-TemporalDB — Person 1: Database Design and SQL
## Beginner's Setup and Run Guide

---

## What Is This Project?

**ZK-TemporalDB** is a college DBMS project that designs and implements a
Privacy-Preserving Versioning and Verification system for Academic Records using
PostgreSQL. Person 1 (you) is responsible for the relational database design,
schema, sample data, SQL queries, views, functions, and procedures.

---

## Prerequisites

- macOS with PostgreSQL installed and running.
- A database named `zk_temporaldb` already created.
- `psql` accessible from your terminal.

> **Verify PostgreSQL is running:**
> ```bash
> psql -d zk_temporaldb -c "SELECT version();"
> ```

---

## Files in This Project

| File | Purpose |
|------|---------|
| `schema.sql` | All table definitions — run first on a fresh database |
| `seed.sql` | Sample / test data — run after schema |
| `views.sql` | Four SQL views for academic reporting |
| `functions_triggers.sql` | Functions, stored procedures, and a trigger |
| `transactions_indexing.sql` | Indexes and transaction examples |
| `queries.sql` | Demonstration SELECT queries |
| `verify.sql` | Automated verification of schema, data, and logic |
| `migrate_v2.sql` | Historical migration script — **do not re-run** |
| `PERSON1_README.md` | This file |
| `PERSON1_VIVA_NOTES.md` | Viva question-and-answer notes |

---

## Run Order (Fresh Installation)

> ⚠️ **Only follow this section if the database is completely empty.**
> If data already exists, skip to the **Verify** step.

Run each file in this exact order from your terminal, inside the project folder:

```bash
cd /Users/niranjan/Downloads/ZK-TemporalDB

# Step 1 — Create all tables
psql -d zk_temporaldb -f schema.sql

# Step 2 — Load sample data
psql -d zk_temporaldb -f seed.sql

# Step 3 — Create views
psql -d zk_temporaldb -f views.sql

# Step 4 — Create functions, procedures, and the trigger
psql -d zk_temporaldb -f functions_triggers.sql

# Step 5 — Create indexes and run transaction examples
psql -d zk_temporaldb -f transactions_indexing.sql

# Step 6 — Run demonstration queries
psql -d zk_temporaldb -f queries.sql

# Step 7 — Verify everything is correct
psql -d zk_temporaldb -f verify.sql
```

---

## Current State (Already Loaded)

> ✅ As of 2026-10-22, this database is already populated.
> **Do not re-run `seed.sql`** unless you reset the database first.

Current row counts:

| Table | Rows |
|-------|------|
| `department` | 3 |
| `student` | 5 |
| `course` | 6 |
| `enrolled_in` | 13 |
| `semester_result` | 6 |
| `system_user` | 4 |

---

## How to Verify the Database

Run the verification script at any time — it is read-only except for the
constraint-rejection tests, which all roll back automatically:

```bash
psql -d zk_temporaldb -f verify.sql
```

**What it checks:**
- All 6 tables exist with correct primary and foreign keys
- All CHECK constraints are in place
- Row counts look sensible
- No broken foreign key references
- Invalid data (out-of-range marks, bad roles, duplicate USNs) is rejected
- All 4 views return rows
- `fn_compute_sgpa`, `fn_compute_cgpa`, `fn_grade_to_point` return expected values
- Stored SGPA in `semester_result` matches values computed from `enrolled_in`
- Pending-marks query shows only the expected rows
- The trigger is enabled
- All 7 custom indexes exist

> The V7 negative tests **intentionally print ERROR** before ROLLBACK.
> Each `ROLLBACK complete (error above = PASS)` line means the constraint worked correctly.

---

## Useful Quick Commands

```bash
# Check all tables
psql -d zk_temporaldb -c "\dt"

# Check row counts
psql -d zk_temporaldb -c "
SELECT 'department' AS t, COUNT(*) FROM department UNION ALL
SELECT 'student', COUNT(*) FROM student UNION ALL
SELECT 'course', COUNT(*) FROM course UNION ALL
SELECT 'enrolled_in', COUNT(*) FROM enrolled_in UNION ALL
SELECT 'semester_result', COUNT(*) FROM semester_result UNION ALL
SELECT 'system_user', COUNT(*) FROM \"system_user\";"

# View student performance summary
psql -d zk_temporaldb -c "SELECT * FROM vw_student_performance_summary;"

# Compute CGPA for student_id = 1 (Arjun Sharma)
psql -d zk_temporaldb -c "SELECT fn_compute_cgpa(1);"

# View pending marks
psql -d zk_temporaldb -c "
SELECT s.usn, c.course_code, e.semester_number
FROM enrolled_in e
JOIN student s ON s.student_id = e.student_id
JOIN course c ON c.course_id = e.course_id
WHERE e.grade IS NULL;"
```

---

## Resetting the Database (Development Only)

> ⚠️ **WARNING: This permanently deletes all data.**
> Only do this in a local development environment, never in production or shared labs.

```sql
-- Run this inside psql to drop and recreate all objects:
DROP TABLE IF EXISTS enrolled_in CASCADE;
DROP TABLE IF EXISTS semester_result CASCADE;
DROP TABLE IF EXISTS student CASCADE;
DROP TABLE IF EXISTS course CASCADE;
DROP TABLE IF EXISTS department CASCADE;
DROP TABLE IF EXISTS "system_user" CASCADE;
DROP VIEW  IF EXISTS vw_student_profile CASCADE;
DROP VIEW  IF EXISTS vw_course_enrollment CASCADE;
DROP VIEW  IF EXISTS vw_semester_results CASCADE;
DROP VIEW  IF EXISTS vw_student_performance_summary CASCADE;
```

After running the above, follow the **Run Order (Fresh Installation)** steps again.

---

## Notes for Person 2 and Person 3

- **Person 2** (cryptographic verification): The `student` and `semester_result`
  tables provide the records to be hashed/versioned. No schema changes to these
  tables should be needed — additional versioning tables can reference `student_id`
  and `(student_id, sem_no)` as foreign keys.

- **Person 3** (application and AI anomaly detection): All views
  (`vw_student_performance_summary`, etc.) expose clean, pre-joined data for
  the application layer. The stored functions `fn_compute_sgpa` and
  `fn_compute_cgpa` can be called directly from application code.

---

*Person 1 — Database Design and SQL | ZK-TemporalDB | DBMS Lab Project*
