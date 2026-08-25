# CareSync - Healthcare Appointment & Follow-up Manager

CareSync is a full-stack, enterprise-grade healthcare management application featuring role-based access (Patient, Doctor, Admin), robust double-booking prevention, 5-minute atomic slot holds, transactional doctor leave handling, asynchronous notification queues with exponential backoff, explicit medication reminder scheduling, and Gemini AI pre-visit symptom analysis and post-visit patient summary generation.

---

## 🛠️ Technology Stack

- **Frontend**: React 18, Vite, Tailwind CSS, React Router v6, Axios, Lucide Icons
- **Backend**: Python FastAPI, SQLAlchemy ORM, Alembic Migrations, PostgreSQL / SQLite
- **Security**: JWT Authentication (HS256), bcrypt Password Hashing, Fernet Token Encryption
- **AI Integration**: Google Gemini API (`google-generativeai` / `google.genai`)
- **Email Service**: SendGrid API
- **Calendar Sync**: Google Calendar API with OAuth 2.0 consent flow

---

## 🚀 Getting Started & Setup

### Prerequisites
- Python 3.10+
- Node.js 18+ and npm

### 1. Environment Setup

Copy `.env.example` to `.env` in the root directory:
```bash
cp .env.example .env
```

### 2. Backend Installation & Server Startup

```bash
# Create and activate Python virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install backend dependencies
pip install -r backend/requirements.txt

# Run Database Migrations / Table Creation & Seed Admin
python -m backend.app.main

# Start FastAPI development server
uvicorn backend.app.main:app --reload --port 8000
```
Backend API will be live at `http://127.0.0.1:8000`. API Documentation (Swagger UI) is available at `http://127.0.0.1:8000/docs`.

### 3. Frontend Installation & Startup

```bash
cd frontend
npm install
npm run dev
```
Frontend Web App will be live at `http://localhost:5173`.

---

## 🔐 Default Seed Credentials

Upon initial startup, the backend automatically seeds a default super-admin account:
- **Admin Email**: `admin@healthcare.com`
- **Admin Password**: `adminpassword123`

---

## 🧪 Automated Testing

The repository includes comprehensive integration and concurrency unit tests covering double-booking prevention, expired slot holds, doctor leave cancellations, SendGrid retries, and Gemini LLM fallbacks.

### 1. SQLite Fast Development Tests
Run default fast in-memory SQLite tests:
```bash
venv\Scripts\python.exe -m pytest backend/tests/
```

### 2. PostgreSQL Full Integration Test Suite
To run the dedicated PostgreSQL exclusion constraint integration test suite (covering concurrent identical bookings, overlapping intervals with different start times, adjacent slots, cancelled/expired slot releases, HELD vs CONFIRMED, and COMPLETED blocks):

Start a PostgreSQL container with Docker:
```bash
docker run -d --name postgres-test -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=healthcare_test postgres:15
```

Execute the test suite pointing to PostgreSQL:
```bash
$env:POSTGRES_TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/healthcare_test"
venv\Scripts\python.exe -m pytest backend/tests/test_postgres_concurrency.py
```

---

## 📐 Database Schema & Architecture

### Key Models & Constraints

1. **User (`users`)**:
   - `email`: Case-insensitive unique string (`lower(email)`).
   - `role`: Enum (`patient`, `doctor`, `admin`).
2. **Doctor (`doctors`)**:
   - `specialization`, `working_hours` (JSON string), `slot_duration_minutes`.
3. **DoctorLeave (`doctor_leaves`)**:
   - Uniqueness constraint on `(doctor_id, leave_date)` preventing double leave entries.
4. **Appointment (`appointments`)**:
   - `status`: Enum (`HELD`, `CONFIRMED`, `COMPLETED`, `CANCELLED`, `EXPIRED`).
   - `hold_expires_at`: UTC timestamp.
   - **PostgreSQL Exclusion Constraint**:
     `EXCLUDE USING gist (doctor_id WITH =, tsrange(start_time, end_time) WITH &&) WHERE (status IN ('HELD', 'CONFIRMED', 'COMPLETED'))`
5. **Medication (`medications`)**:
   - `reminder_times`: JSON array of explicit `HH:MM` UTC string times (e.g. `["08:00", "20:00"]`). If not provided by the doctor, no schedule is auto-invented.
6. **Notification (`notifications`)**:
   - Persistent email delivery queue with `retry_count`, `next_retry_at`, and exponential backoff tracking.

---

## 🤖 Gemini AI Prompts

### Pre-Visit Symptom Analysis Prompt
```text
System: You are an expert medical triage assistant. Analyze patient reported symptoms and output valid JSON with:
1. "urgency_level": "Low", "Medium", or "High"
2. "chief_complaint": Short 1-sentence summary
3. "suggested_questions": List of 3 relevant diagnostic questions for the doctor to ask.
```

### Post-Visit Summary Prompt
```text
System: You are a compassionate medical communicator. Convert doctor's clinical notes and prescription into a patient-friendly summary:
1. "patient_summary": Clear, jargon-free explanation of diagnosis and plan.
2. "medication_schedule": Formatted dosage instructions.
3. "follow_up_steps": Bulleted list of care instructions and warning signs.
```

---

## 📅 Google Calendar OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Enable **Google Calendar API**.
3. Create OAuth 2.0 Client ID Credentials (Web Application).
4. Set Authorized Redirect URI: `http://localhost:8000/api/auth/google/callback`.
5. Add `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to `.env`.

---

## 📧 SendGrid Email Setup

1. Create a SendGrid account at [SendGrid.com](https://sendgrid.com/).
2. Generate an API Key under **Settings > API Keys**.
3. Add `SENDGRID_API_KEY` and `SENDGRID_FROM_EMAIL` to `.env`.
4. If SendGrid is not configured, CareSync safely logs email notifications to the backend console without disrupting core application flows.

---

## 🚀 Production Deployment Guidelines

1. Set `DATABASE_URL` to a production PostgreSQL instance (`postgresql://user:pass@host:5432/dbname`).
2. Run database migrations: `alembic upgrade head`.
3. Set `SECRET_KEY` and `FERNET_KEY` to secure 32-byte randomly generated keys.
4. Build frontend production assets: `cd frontend && npm run build`.
5. Deploy FastAPI backend using `gunicorn -w 4 -k uvicorn.workers.UvicornWorker backend.app.main:app`.
