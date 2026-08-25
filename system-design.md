# CareSync System Architecture & Reliability Design

## 1. Concurrency & Double-Booking Prevention
CareSync enforces strict double-booking protection at the PostgreSQL database engine level using half-open timestamp intervals `[start_time, end_time)`. This guarantees that contiguous slots (e.g. 10:00–10:30 and 10:30–11:00) do not collide.

### PostgreSQL Exclusion Constraint
On PostgreSQL, double-booking is prevented using the `btree_gist` extension and an ORM-managed `ExcludeConstraint`:
```python
ExcludeConstraint(
    ("doctor_id", "="),
    (func.tsrange(target.c.start_time, target.c.end_time, '[)'), "&&"),
    name="prevent_doctor_double_booking",
    where=text("status IN ('HELD', 'CONFIRMED', 'COMPLETED')")
)
```
Generates DDL:
```sql
CREATE TABLE appointments (
    ...
    CONSTRAINT prevent_doctor_double_booking 
    EXCLUDE USING gist (
        doctor_id WITH =, 
        tsrange(start_time, end_time, '[)') WITH &&
    ) WHERE (status IN ('HELD', 'CONFIRMED', 'COMPLETED'))
);
```
This partial exclusion index ensures:
- Only active slots (`HELD`, `CONFIRMED`, `COMPLETED`) block new bookings.
- `CANCELLED` and `EXPIRED` slots are excluded from the index, immediately freeing the slot for other patients.
- Concurrent database transactions that attempt to insert or confirm overlapping slots are aborted by PostgreSQL with a `23P01` exclusion violation, which the application catches and converts into an HTTP `409 Conflict`.

---

## 2. Temporary Slot Hold Mechanism (5-Minute Locks)
To prevent race conditions while patients fill out pre-visit symptom forms, CareSync implements a 5-minute atomic slot hold:
1. **Hold Creation**: When a patient selects a slot, an appointment is inserted with `status = 'HELD'` and `hold_expires_at = now() + 5 minutes`.
2. **Hold Expiration Cleanup**: Before querying available slots or attempting new holds, the application executes `clean_expired_holds()`, which transitions all `HELD` rows where `hold_expires_at < now()` to `EXPIRED`.
3. **Confirmation Validation**: When confirming, the backend verifies that `current_user.id == appointment.patient_id` and `appointment.hold_expires_at > now()`. If valid, the status transitions to `CONFIRMED`.

---

## 3. Transactional Doctor Leave Resolution
When an administrator registers a doctor leave for a future date (`doctor_id` + `leave_date` enforced by a database uniqueness constraint):
1. **Slot Invalidation**: All existing `HELD` and `CONFIRMED` appointments on that date for the target doctor are immediately marked `CANCELLED`.
2. **Notification Queueing**: Email cancellation notifications (`leave_cancellation`) are transactionally enqueued into the `notifications` database table within the same database transaction.
3. **Google Calendar Cleanup**: Asynchronous background tasks attempt to delete associated Google Calendar event IDs (`google_event_patient_id` and `google_event_doctor_id`). Calendar deletion errors are logged but do not block database commits.

---

## 4. Notification Queue & Retry Resilience
CareSync uses a DB-backed persistent notification queue to ensure third-party email delivery failures (e.g., SendGrid rate limits, network timeouts) never roll back core clinical transactions.

### Queue Architecture
- Notifications are created with `status = 'PENDING'`, `retry_count = 0`, and `next_retry_at = now()`.
- An asynchronous background worker (`notification_worker.py`) polls pending jobs where `next_retry_at <= now()`.
- **Exponential Backoff**: Upon failure, `retry_count` is incremented and `next_retry_at` is set to `now() + (2 ^ retry_count * 60 seconds)`.
- **Terminal State**: After 3 failed attempts, the notification transitions to `FAILED` and logs the error details for administrative review.

---

## 5. LLM Fault Tolerance & Fallback Strategy
Gemini API integrations (pre-visit symptom analysis and post-visit patient summary generation) are wrapped in fallback handlers:
- **Pre-Visit Symptom Analysis**: If Gemini API times out, returns malformed JSON, or lacks an API key, the system falls back to a safe default JSON payload (`urgency_level = "Medium"`, `chief_complaint = symptoms[:100]`, and standard clinical review questions).
- **Post-Visit Patient Summaries**: If Gemini summary generation fails during appointment completion, the system synthesizes a fallback summary directly from the doctor's clinical notes and prescription text.
- **Transaction Safety**: LLM generation errors never roll back appointment completions, medication records, or prescription storage.
