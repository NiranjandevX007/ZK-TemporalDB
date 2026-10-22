# ZK-TemporalDB

**Privacy-Preserving Versioning and Verification System for Academic Records**
DBMS Lab Project — PostgreSQL · SQL · PL/pgSQL

---

## Problem Statement and Objectives

Academic records (grades, results, transcripts) can be silently modified in a
traditional database with no audit trail. **ZK-TemporalDB** builds a clean,
constraint-enforced relational core designed to integrate with a cryptographic
versioning layer and an application-layer anomaly detector.

**Objectives:**
- Design a 3NF-normalized schema for departments, students, courses,
  enrollments, semester results, and internal users.
- Enforce integrity with `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL`,
  and `CHECK` constraints.
- Keep derived values (`total_marks`, `SGPA`, `CGPA`) computed on demand —
  never stored redundantly.
- Provide stored functions, procedures, views, and a trigger for safe
  programmatic access.
- Ship a 13-section automated verification suite.

---

## Key Features — Implementation Status

| Feature | Status |
|---------|--------|
| 6-table normalized schema with all constraints | ✅ Done |
| Transactional seed dataset (5 students, 6 courses) | ✅ Done |
| 4 SQL views for reporting and application use | ✅ Done |
| 3 functions (`fn_compute_sgpa/cgpa/grade_to_point`) | ✅ Done |
| 2 stored procedures (`sp_declare_result`, `sp_update_marks`) | ✅ Done |
| 1 trigger (`trg_enrollment_sem_check`) | ✅ Done |
| 7 custom indexes | ✅ Done |
| 4 transaction examples with savepoints | ✅ Done |
| 25+ demonstration SELECT queries | ✅ Done |
| 13-section verification suite (`verify.sql`) | ✅ Done |
| Cryptographic versioning layer (Person 2) | ✅ Implemented — validation in progress |
| Application + AI anomaly detection (Person 3) | ⏳ Planned |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Database | PostgreSQL (macOS / Linux) |
| Query language | SQL + PL/pgSQL |
| Client | `psql` |
| Version control | Git / GitHub |
| Cryptographic versioning | Python · psycopg2 · pymongo · SHA-256 · Merkle trees |
| Zero-knowledge proofs | Circom 2 · snarkjs · Groth16 (BN128) |

No frameworks or external libraries — pure SQL and PL/pgSQL throughout.

---

## Architecture and Six Core Tables

```
schema.sql → seed.sql → views.sql → functions_triggers.sql
                                          → transactions_indexing.sql
                                          → queries.sql → verify.sql
```

**Tables and relationships:**

| Table | Role | Key Constraints |
|-------|------|-----------------|
| `department` | Academic departments | `department_name` UNIQUE |
| `student` | Student identity (USN, name, DOB, program) | `usn` UNIQUE; `admission_year` 2000–2100 |
| `course` | Subjects with credits | `course_code` UNIQUE; `credits` 1–10 |
| `enrolled_in` | Junction: student ↔ course per semester | `internal_marks` 0–30; `external_marks` 0–70; UNIQUE(student, course, year, sem) |
| `semester_result` | Weak entity — SGPA + status per semester | Composite PK `(student_id, sem_no)`; `result_status` IN (PASS/FAIL/DETAINED/WITHHELD) |
| `system_user` | Faculty / Registrar / Admin accounts | `username` UNIQUE; `role` IN (FACULTY/REGISTRAR/ADMIN) |

`enrolled_in` resolves the many-to-many relationship between `student` and
`course`. `semester_result` is a weak entity identified by `(student_id, sem_no)`.
CGPA and total_marks are derived — never stored.

---

## Project Structure

```
ZK-TemporalDB/
├── schema.sql                  # Tables and constraints — run first
├── seed.sql                    # Sample data (transactional)
├── views.sql                   # 4 SQL views
├── functions_triggers.sql      # 3 functions, 2 procedures, 1 trigger
├── transactions_indexing.sql   # 7 indexes + 4 transaction examples
├── queries.sql                 # 25+ demonstration SELECT queries
├── verify.sql                  # 13-section automated test suite
├── migrate_v2.sql              # Historical migration — do NOT re-run
├── PERSON1_README.md           # Full setup guide and quick-reference commands
├── PERSON1_VIVA_NOTES.md       # Design rationale and viva Q&A
└── person2/                    # Cryptographic versioning layer
    ├── services.py             # AcademicRecordService — integration facade for Person 3
    ├── versioning.py           # SHA-256 hash-chain versioning
    ├── merkle.py               # Merkle tree batch verification
    ├── zkp.py                  # Zero-knowledge proof service (Groth16 + fallback)
    ├── canonical.py            # Deterministic JSON canonicalization
    ├── circuits/               # Circom circuit + build artifacts
    ├── requirements.txt        # Python dependencies
    ├── package.json            # Node.js circuit toolchain (circom2 + snarkjs)
    ├── API_CONTRACT.md         # Integration interface for Person 3
    └── tests/                  # 86+ tests (unit + integration)
```

---

## Setup and Execution

> Full setup guide with reset instructions: [PERSON1_README.md](PERSON1_README.md)

**Prerequisites:** PostgreSQL installed and running; database `zk_temporaldb` created.

```bash
# Run in this exact order on a fresh database:
psql -d zk_temporaldb -f schema.sql
psql -d zk_temporaldb -f seed.sql
psql -d zk_temporaldb -f views.sql
psql -d zk_temporaldb -f functions_triggers.sql
psql -d zk_temporaldb -f transactions_indexing.sql
psql -d zk_temporaldb -f queries.sql
psql -d zk_temporaldb -f verify.sql
```

`queries.sql` and `verify.sql` are read-only and safe to re-run at any time.

### Person 2 — Python dependencies

```bash
pip install -r person2/requirements.txt
```

Copy `person2/.env.example` to `person2/.env` and fill in your PostgreSQL
(and optionally MongoDB) connection strings before running tests.

### Person 2 — Local Node.js circuit toolchain (optional)

Required only for genuine Groth16 ZKP proofs.  If this step is skipped, the
service automatically uses the commitment-based fallback.

```bash
# Install circom2 and snarkjs into person2/node_modules
cd person2 && npm install

# Compile the circuit and run the trusted setup (test-only ceremony)
python3 -c "from person2.zkp import ZKPService; ZKPService().setup_circuit()"
```

---

## Testing and Verification

Run the full suite:

```bash
psql -d zk_temporaldb -f verify.sql
```

| Section | Checks |
|---------|--------|
| V1–V4 | All 6 tables exist; primary keys, foreign keys, and CHECK constraints are in place |
| V5–V6 | Row counts match seed data; zero orphaned foreign-key references |
| V7 | 6 negative tests: invalid marks, bad result status, bad role, duplicate USN, duplicate enrollment — all rejected and rolled back |
| V8 | All 4 views execute and return rows |
| V9–V10 | Functions return expected values; stored SGPA matches values computed live from `enrolled_in` |
| V11–V13 | Pending-marks query correct; trigger enabled; all 7 custom indexes present |

> V7 intentionally prints `ERROR` before each `ROLLBACK` — this is the expected
> pass condition for constraint rejection tests.

---

## Team Responsibilities

### Person 1 — Database Design and SQL ✅ Complete
All schema, data, views, functions, procedures, trigger, indexes, queries, and
verification listed above. See [PERSON1_README.md](PERSON1_README.md) and
[PERSON1_VIVA_NOTES.md](PERSON1_VIVA_NOTES.md) for full detail.

### Person 2 — Cryptographic Versioning ✅ Implemented

SHA-256 hash-chain versioning of academic records, Merkle-tree batch proofs,
and a zero-knowledge proof layer (Groth16 via Circom + snarkjs, with an
honest commitment-based fallback when the toolchain is absent).  References
`student_id` and `(student_id, sem_no)` as identifiers — no changes were made
to Person 1's tables.  See [`person2/API_CONTRACT.md`](person2/API_CONTRACT.md)
for the integration interface.

> **Validation status:** The core cryptographic modules pass 86+ automated tests.
> End-to-end snarkjs verification and a live PostgreSQL integration have been
> tested locally.  Review is ongoing.

### Person 3 — Application and AI Anomaly Detection ⏳ Planned
Application layer reading through Person 1's views (`vw_student_performance_summary`,
etc.) and calling `fn_compute_sgpa` / `fn_compute_cgpa`. AI anomaly detection
to flag suspicious grade or result changes.

---

## Limitations and Future Work

- Sample dataset is small (5 students, 6 courses) — sufficient for lab
  demonstration, not load testing.
- `system_user` stores roles only; no password hashing or session management.
- `fn_grade_to_point` uses an illustrative grading scale, not an official policy.
- Foreign keys have no `ON DELETE` rule; child rows must be removed manually
  before deleting a parent.
- The Groth16 trusted setup uses a single test-only "powers of tau" ceremony;
  production use would require a multi-party ceremony.

---

*ZK-TemporalDB | DBMS Lab Project*
