# ZK-TemporalDB — Person 1 Viva Notes
## DBMS Lab Viva Preparation Guide

---

## Q1. What problem does ZK-TemporalDB solve?

**Short answer:**
Academic records — grades, results, and transcripts — can be tampered with.
ZK-TemporalDB solves this by storing records in a versioned, verifiable database
so that any change is auditable and provable using cryptographic techniques.

**In simple words:**
Imagine a student's marksheet. Currently, if someone edits it in a database, it
is hard to detect. ZK-TemporalDB keeps a history of every version of the record
and uses cryptography (zero-knowledge proofs) to prove a record is authentic
without revealing its contents.

**My part (Person 1):** Design the relational database — the tables, relationships,
constraints, queries, and views that store the core academic data.

---

## Q2. What does each of the six tables do?

| Table | Purpose |
|-------|---------|
| `department` | Stores academic departments (e.g., Computer Science). Each department has a unique name and a Head of Department. |
| `student` | Stores student identity: USN, name (first + last), date of birth, email, program, admission year, and their department. |
| `course` | Stores subjects offered: course code, name, credits, and which department offers it. |
| `enrolled_in` | The association table: records which student is taking which course in which semester/year. Stores marks (internal 0–30, external 0–70), grade, and grade point. |
| `semester_result` | Stores the overall outcome for one student in one complete semester: SGPA, total credits, and result status (PASS/FAIL/DETAINED/WITHHELD). |
| `system_user` | Internal system accounts for Faculty, Registrar, and Admin roles. Not the same as students. |

---

## Q3. What are primary keys, foreign keys, candidate keys, and composite keys?

**Primary key:**
A column (or set of columns) that uniquely identifies every row in a table.
- Example: `student_id` in the `student` table — every student has a different `student_id`.

**Foreign key:**
A column in one table that references the primary key of another table, enforcing referential integrity.
- Example: `student.department_id` references `department.department_id`.
  This ensures a student cannot be assigned to a department that doesn't exist.

**Candidate key:**
Any column that *could* be the primary key because it is unique and not null.
- Example: In `student`, both `student_id` and `usn` are unique. Either could be the primary key — so both are candidate keys. We chose `student_id` as the primary key; `usn` is an alternate (unique) key.

**Composite key:**
A primary key made of two or more columns together.
- Example: In `semester_result`, the primary key is `(student_id, sem_no)`. Neither column alone is unique (a student has multiple semesters; many students can be in semester 1), but together they uniquely identify one semester result.

---

## Q4. Why is `semester_result` a weak entity?

A **weak entity** is one that cannot be uniquely identified by its own attributes alone — it depends on another (strong) entity.

- `semester_result` records one student's result for one semester.
- The `sem_no` column (partial key) alone is not unique — many students can have a sem_no = 1.
- It becomes unique only when combined with `student_id`, which comes from the `student` table (the identifying owner entity).
- If the student is deleted, their semester results lose meaning — hence the FOREIGN KEY `ON DELETE` relationship.

**Composite PK:** `PRIMARY KEY (student_id, sem_no)` — this is the weak entity's identifying key, combining its partial key with its owner's primary key.

---

## Q5. Why is `enrolled_in` a junction table?

A **junction table** (also called an associative entity or bridge table) is used to represent a **many-to-many relationship** between two tables.

- One student can enroll in many courses.
- One course can be taken by many students.
- A direct foreign key in either table cannot represent this relationship.

`enrolled_in` solves this by having:
- `student_id` → references `student`
- `course_id` → references `course`
- Plus extra attributes unique to the relationship: `internal_marks`, `external_marks`, `grade`, `grade_point`, `semester_number`, `academic_year`

Without `enrolled_in`, you couldn't store marks per student per course.

---

## Q6. How does this design support normalization?

**1NF (First Normal Form):**
All columns store atomic values. Name is split into `first_name` and `last_name` (composite ER attribute) rather than storing "Arjun Sharma" as one field.

**2NF (Second Normal Form):**
Every non-key column depends on the *whole* primary key, not just part of it.
- In `enrolled_in` (PK = `enrollment_id`): marks and grades depend on the specific enrollment.
- In `semester_result` (PK = `student_id, sem_no`): SGPA depends on the whole pair, not just `student_id`.

**3NF (Third Normal Form):**
No transitive dependencies — no non-key column depends on another non-key column.
- CGPA is not stored in `student` because it depends on `semester_result` rows, not directly on `student_id`. Storing it would create a transitive dependency and redundancy.
- `department_name` is not repeated in `student` — only `department_id` is stored (the FK); the name is in `department`.

---

## Q7. Why is CGPA derived instead of stored?

**CGPA = Σ(SGPA × total_credits) / Σtotal_credits** (credits-weighted average across semesters).

CGPA is **not stored** for three reasons:

1. **Redundancy:** It can always be computed from `semester_result` rows. Storing it would duplicate data.
2. **Update anomalies:** If any semester result is corrected, a stored CGPA would become stale unless explicitly updated.
3. **ER design principle:** Derived attributes are not stored in relations — they are computed when needed (same reason `total_marks = internal + external` is not stored in `enrolled_in`).

**In this project:** The function `fn_compute_cgpa(student_id)` and the view `vw_student_performance_summary` compute CGPA on demand.

---

## Q8. What do CHECK, UNIQUE, NOT NULL, and FOREIGN KEY constraints do?

| Constraint | What it does | Example in this project |
|-----------|-------------|------------------------|
| `CHECK` | Rejects rows where a condition is false | `internal_marks BETWEEN 0 AND 30` — marks above 30 are rejected |
| `UNIQUE` | Ensures no two rows have the same value in that column | `student.usn` — two students cannot have the same USN |
| `NOT NULL` | Ensures the column always has a value | `student.first_name NOT NULL` — every student must have a first name |
| `FOREIGN KEY` | Ensures a value references a valid row in another table | `enrolled_in.student_id` must exist in `student.student_id` |

---

## Q9. What is the difference between WHERE and HAVING?

| Clause | Filters | When applied |
|--------|---------|-------------|
| `WHERE` | Individual rows, before grouping | Before `GROUP BY` |
| `HAVING` | Groups (aggregated values), after grouping | After `GROUP BY` |

**Example:**
```sql
-- WHERE filters rows before grouping:
SELECT department_id, COUNT(*) FROM student
WHERE admission_year = 2022      -- only 2022 students
GROUP BY department_id;

-- HAVING filters groups after aggregation:
SELECT department_id, COUNT(*) FROM student
GROUP BY department_id
HAVING COUNT(*) > 2;             -- only departments with more than 2 students
```

You **cannot** use `HAVING` without `GROUP BY`, and you **cannot** filter on aggregate functions (`COUNT`, `AVG`, etc.) in `WHERE`.

---

## Q10. What is the difference between INNER JOIN and LEFT JOIN?

| Join type | What it returns |
|-----------|----------------|
| `INNER JOIN` | Only rows that have matching records in **both** tables |
| `LEFT JOIN` | All rows from the **left** table + matching rows from the right (NULLs if no match) |

**Example from this project:**

```sql
-- INNER JOIN: only students who ARE enrolled in a course appear
SELECT s.usn, c.course_code
FROM student s INNER JOIN enrolled_in e ON e.student_id = s.student_id
               INNER JOIN course c     ON c.course_id  = e.course_id;

-- LEFT JOIN: ALL departments appear, even Mathematics which has no enrolled students
SELECT d.department_name, s.usn
FROM department d LEFT JOIN student s ON s.department_id = d.department_id;
-- Mathematics row appears with s.usn = NULL
```

---

## Q11. What are views, functions, procedures, and triggers?

**View:** A saved SELECT query stored under a name. Acts like a virtual table.
- Example: `vw_student_performance_summary` — query it like a table; it joins student, semester_result, and enrolled_in automatically.
- Benefit: Simplifies complex queries; hides joins from the user; no data is duplicated.

**Function:** A named block of SQL/PL pgSQL that accepts inputs, runs logic, and returns a value.
- Example: `fn_compute_cgpa(student_id)` returns a single NUMERIC CGPA value.
- Can be used inside SELECT statements.

**Stored Procedure:** Like a function, but designed for actions (INSERT, UPDATE) rather than returning a value. Called with `CALL`.
- Example: `sp_declare_result(...)` inserts or updates a semester result row safely.

**Trigger:** Code that runs **automatically** when a specific event occurs on a table (INSERT, UPDATE, DELETE).
- Example: `trg_enrollment_sem_check` fires before every INSERT or UPDATE on `enrolled_in` and emits a NOTICE if a semester result already exists for that student+semester.
- Triggers enforce business rules automatically without relying on the application.

---

## Q12. What are transactions, COMMIT, and ROLLBACK?

A **transaction** is a group of SQL statements treated as a single unit. Either all succeed or none do.

```sql
BEGIN;           -- start transaction
  INSERT ...;    -- statement 1
  UPDATE ...;    -- statement 2
COMMIT;          -- save all changes permanently
```

If something goes wrong:
```sql
ROLLBACK;        -- undo everything since BEGIN
```

**SAVEPOINT** allows partial rollbacks:
```sql
BEGIN;
  SAVEPOINT sp1;
  INSERT INTO semester_result ... 'HONOURS' ...;  -- this will fail
ROLLBACK TO SAVEPOINT sp1;   -- undo only from sp1
COMMIT;                      -- outer transaction still commits cleanly
```

**ACID properties:** Transactions guarantee Atomicity (all or nothing), Consistency (constraints always satisfied), Isolation (concurrent transactions don't interfere), Durability (committed data survives crashes).

---

## Q13. Why do indexes help, and what trade-offs do they have?

**Why they help:**
Without an index, PostgreSQL scans every row of a table to find matches (full table scan — slow for large tables).
An index is like a book's index — it lets the database jump directly to the right rows.

**Example:** `idx_enrolled_in_student_id` on `enrolled_in(student_id)`:
```sql
-- Without index: scans all 10,000 enrollment rows
-- With index: jumps directly to Arjun's 5 rows
SELECT * FROM enrolled_in WHERE student_id = 1;
```

**Indexes in this project:**
- `idx_enrolled_in_student_id` — fast transcript lookups
- `idx_enrolled_in_course_id` — fast course statistics
- `idx_enrolled_in_sem_year` — fast semester filtering
- `idx_semester_result_student_id` — fast CGPA calculation
- `idx_student_department_id` — fast department reports
- `idx_course_department_id` — fast course-by-department queries
- `idx_enrolled_in_pending_grade` (partial) — fast pending-marks search

**Trade-offs:**
| Benefit | Cost |
|---------|------|
| Much faster SELECT queries | Extra disk storage for each index |
| Faster JOIN operations | Slower INSERT/UPDATE/DELETE (index must also be updated) |
| Enables efficient ORDER BY | Too many indexes can hurt write-heavy workloads |

PostgreSQL automatically creates indexes for PRIMARY KEY and UNIQUE constraints. Custom indexes are created for other common lookup patterns.

---

## Q14. How does the SQL component connect to the team's NoSQL and verification components?

**Person 1 (SQL/PostgreSQL):**
- Stores the core academic records in normalized relational tables.
- Provides functions (`fn_compute_sgpa`, `fn_compute_cgpa`) and views that any application can use.
- Defines the canonical data model: what a student, course, enrollment, and result look like.

**Person 2 (Cryptographic Versioning — NoSQL/SHA-256/Merkle Trees):**
- Uses `student_id` and `(student_id, sem_no)` as identifiers to hash and version records.
- Each time a semester result or marks change in the PostgreSQL tables, Person 2's component creates a new hash and stores it in a versioning system.
- This creates a tamper-evident audit trail — if someone changes `sgpa = 9.50` to `9.75` in PostgreSQL, the stored hash no longer matches.

**Person 3 (Application and AI Anomaly Detection):**
- The application reads data through Person 1's views and calls Person 1's functions.
- AI anomaly detection might flag, for example, sudden grade changes, unusually high marks for a student who previously scored low, or result_status changes — all based on querying the relational tables Person 1 designed.

**Together:** The relational layer (Person 1) is the authoritative data store. The cryptographic layer (Person 2) ensures its integrity. The application layer (Person 3) presents and analyses the data.

---

## Quick-Reference: Key Formulas

```
SGPA = Σ(grade_point × credits) / Σcredits        [per semester]
CGPA = Σ(sgpa × total_credits) / Σtotal_credits   [across all semesters]
total_marks = internal_marks + external_marks       [per course — derived, not stored]
```

---

## Key Constraint Summary

| Table | PK | Important constraints |
|-------|----|-----------------------|
| `department` | `department_id` | `department_name` UNIQUE |
| `student` | `student_id` | `usn` UNIQUE; `admission_year` 2000–2100 |
| `course` | `course_id` | `course_code` UNIQUE; `credits` 1–10 |
| `enrolled_in` | `enrollment_id` | `internal_marks` 0–30; `external_marks` 0–70; `grade_point` 0–10; UNIQUE(student, course, year, sem) |
| `semester_result` | `(student_id, sem_no)` | `sgpa` 0–10; `result_status` IN ('PASS','FAIL','DETAINED','WITHHELD') |
| `system_user` | `user_id` | `username` UNIQUE; `role` IN ('FACULTY','REGISTRAR','ADMIN') |

---

*Person 1 — Database Design and SQL | ZK-TemporalDB | DBMS Lab Viva Notes*
