# ZK-TemporalDB — Person 2 API Contract

## Overview

This document defines the integration interface for **Person 3** (Application
Layer) to consume Person 2's cryptographic verification services.

Person 2 provides a **Python service layer** (`person2.services.AcademicRecordService`)
that wraps all cryptographic operations. Person 3 should instantiate this service
and call its methods rather than importing lower-level modules directly.

If Person 3 builds a REST API, the endpoint suggestions below map directly to
service methods.

---

## Quick Start

```python
from person2.services import AcademicRecordService

# Initialize (reads connection strings from environment)
svc = AcademicRecordService.from_env()

# Retrieve a record
record = svc.get_record(student_id=1)

# Create a new version
version = svc.create_version(student_id=1)

# Verify integrity
result = svc.verify_version(version_id=version["version_id"])

# Create Merkle batch
batch = svc.create_merkle_batch([1, 2, 3], description="Semester 1 batch")

# Verify Merkle inclusion
inclusion = svc.verify_merkle_inclusion(batch_id=1, version_id=1)

# Generate ZKP (threshold proof)
proof = svc.generate_zkp(student_id=1, threshold=8.00)

# Verify ZKP
valid = svc.verify_zkp(proof["public_proof"], proof["private_opening"])

# Cleanup
svc.close()
```

---

## Endpoints

### 1. Health Check

**Method:** `svc.health_check()`
**REST:** `GET /api/health`

**Response:**
```json
{
    "postgresql": { "status": "ok", "version": "PostgreSQL 17.x ..." },
    "mongodb": { "status": "ok", "version": "7.x" },
    "zkp_toolchain": {
        "genuine_zkp": false,
        "fallback_mode": true,
        "proof_type": "commitment_fallback"
    }
}
```

---

### 2. Get Academic Record

**Method:** `svc.get_record(student_id, version_number=None)`
**REST:** `GET /api/records/{student_id}?version={version_number}`

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `student_id` | int | Yes | Student's database ID |
| `version_number` | int | No | Version number (None=latest, 0=live from PG) |

**Response (versioned):**
```json
{
    "version_id": 1,
    "student_id": 1,
    "version_number": 1,
    "snapshot_hash": "a1b2c3...64chars",
    "prev_hash": null,
    "snapshot_scope": "full_academic_record",
    "created_at": "2026-10-22T10:00:00+00:00",
    "record": {
        "student": { "usn": "1CS22001", "first_name": "Arjun", ... },
        "enrollments": [ ... ],
        "semester_results": [ ... ],
        "record_timestamp": "2026-10-22T10:00:00Z"
    }
}
```

**Errors:**
| Code | Condition |
|------|-----------|
| 404 | Student not found or no versions exist |

---

### 3. Create Record Version

**Method:** `svc.create_version(student_id)`
**REST:** `POST /api/records/{student_id}/versions`

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `student_id` | int | Yes | Student's database ID |

**Response:**
```json
{
    "version_id": 2,
    "student_id": 1,
    "version_number": 2,
    "snapshot_hash": "d4e5f6...64chars",
    "prev_hash": "a1b2c3...64chars",
    "snapshot_scope": "full_academic_record",
    "created_at": "2026-10-22T10:30:00+00:00"
}
```

**Errors:**
| Code | Condition |
|------|-----------|
| 404 | Student not found |
| 500 | Database error (PG or MongoDB) |

**Side effects:**
- Inserts row into `record_version` (PostgreSQL)
- Inserts document into `record_snapshots` (MongoDB, if available)

---

### 4. Verify Record Version

**Method:** `svc.verify_version(version_id)`
**REST:** `GET /api/versions/{version_id}/verify`

**Response:**
```json
{
    "valid": true,
    "checks": {
        "hash_matches": true,
        "prev_hash_valid": true,
        "mongo_consistent": true
    },
    "details": "All checks passed"
}
```

If tampered:
```json
{
    "valid": false,
    "checks": {
        "hash_matches": false,
        "prev_hash_valid": true,
        "mongo_consistent": null
    },
    "details": "HASH MISMATCH: stored=abc..., recomputed=def..."
}
```

---

### 5. Verify Version Chain

**Method:** `svc.verify_chain(student_id)`
**REST:** `GET /api/records/{student_id}/verify-chain`

**Response:**
```json
{
    "valid": true,
    "versions_checked": 3,
    "first_failure": null,
    "details": "All 3 versions verified successfully"
}
```

---

### 6. Create Merkle Batch

**Method:** `svc.create_merkle_batch(version_ids, description=None)`
**REST:** `POST /api/merkle/batches`

**Request body:**
```json
{
    "version_ids": [1, 2, 3],
    "description": "End-of-semester batch"
}
```

**Response:**
```json
{
    "batch_id": 1,
    "merkle_root": "g7h8i9...64chars",
    "leaf_count": 3,
    "created_at": "2026-10-22T11:00:00+00:00",
    "proofs": {
        "1": [["sibling_hash", "R"], ["sibling_hash", "L"]],
        "2": [["sibling_hash", "L"], ["sibling_hash", "L"]],
        "3": [["sibling_hash", "R"]]
    }
}
```

**Errors:**
| Code | Condition |
|------|-----------|
| 400 | Empty version_ids or missing version IDs |
| 500 | Database error |

---

### 7. Verify Merkle Inclusion

**Method:** `svc.verify_merkle_inclusion(batch_id, version_id)`
**REST:** `GET /api/merkle/batches/{batch_id}/verify/{version_id}`

**Response:**
```json
{
    "valid": true,
    "details": "Inclusion proof verified"
}
```

---

### 8. Generate ZKP (Threshold Proof)

**Method:** `svc.generate_zkp(student_id, threshold=8.00)`
**REST:** `POST /api/zkp/generate`

**Request body:**
```json
{
    "student_id": 1,
    "threshold": 8.00
}
```

**Response:**
```json
{
    "public_proof": {
        "proof_type": "commitment_fallback",
        "commitment": "j0k1l2...64chars",
        "threshold_scaled": 800,
        "eligible": true,
        "cgpa_in_valid_range": true,
        "student_id": 1,
        "metadata": {
            "scale_factor": 100,
            "hash_algorithm": "SHA-256",
            "WARNING": "This is a commitment scheme, NOT a zero-knowledge proof..."
        }
    },
    "private_opening": {
        "cgpa_scaled": 950,
        "blinding": "random_256bit_hex"
    }
}
```

> **PRIVACY:** The `private_opening` contains the student's exact CGPA.
> It must be stored securely and NEVER shared with third parties unless
> the student explicitly consents. The `public_proof` alone does NOT
> reveal the CGPA.

**Errors:**
| Code | Condition |
|------|-----------|
| 404 | Student not found or no semester results |
| 400 | Threshold out of range [0, 10.00] |

---

### 9. Verify ZKP

**Method:** `svc.verify_zkp(proof_data, private_opening=None)`
**REST:** `POST /api/zkp/verify`

**Request body:**
```json
{
    "proof": { "proof_type": "...", "commitment": "...", ... },
    "private_opening": { "cgpa_scaled": 950, "blinding": "..." }
}
```

**Response:**
```json
{
    "valid": true,
    "eligible": true,
    "commitment_verified": true,
    "eligibility_verified": true,
    "details": "Commitment verified and eligibility confirmed"
}
```

> Without `private_opening`, verification returns `valid: false` with
> a message explaining that the commitment requires the opening for
> full verification.

---

## Data Model

### PostgreSQL Tables (Person 2)

| Table | Purpose |
|-------|---------|
| `record_version` | Append-only versioned snapshots with SHA-256 hash chain |
| `merkle_batch` | Merkle tree root hashes for batch verification |
| `merkle_batch_member` | Links record versions to Merkle batches |

### MongoDB Collections (Person 2)

| Collection | Purpose |
|------------|---------|
| `record_snapshots` | Full canonical JSON snapshots with parsed record |
| `merkle_batches` | Merkle tree metadata with precomputed proofs |

### Identifiers

| ID | Source | Description |
|----|--------|-------------|
| `student_id` | PostgreSQL `student.student_id` | Primary student identifier |
| `version_id` | PostgreSQL `record_version.version_id` | Unique version ID |
| `batch_id` | PostgreSQL `merkle_batch.batch_id` | Unique batch ID |

---

## Privacy Restrictions

1. **Never expose CGPA** in public proof metadata or API responses (except to the student themselves).
2. **Private openings** must be stored encrypted or in a student-accessible-only location.
3. **Canonical snapshots** contain full academic records — access should be role-restricted.
4. **ZKP public proofs** only reveal: threshold, eligibility (yes/no), proof type.

---

## Error Handling

All methods raise Python exceptions on failure:
- `ValueError`: Invalid input (student not found, empty batch, out of range)
- `RuntimeError`: Cross-database consistency failure (MongoDB write failed)
- `psycopg2.*Error`: PostgreSQL constraint violations
- `pymongo.errors.*`: MongoDB connectivity issues

Person 3 should catch these and map to appropriate HTTP status codes.
