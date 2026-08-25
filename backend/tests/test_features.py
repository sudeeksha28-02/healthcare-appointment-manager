import pytest
import datetime
import json
import os
os.environ["TESTING"] = "1"

from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.main import app
from backend.app.database import Base, get_db
from backend.app.models import User, Doctor, DoctorLeave, Appointment, Medication, Notification, GoogleToken
from backend.app.auth.security import get_password_hash

# Setup engine with StaticPool so all sessions share the same connection
engine = create_engine(
    "sqlite:///:memory:", 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(name="db_session")
def fixture_db_session():
    # Create tables
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Seed default roles
    admin_pw = get_password_hash("adminpw")
    patient_pw = get_password_hash("patientpw")
    doctor_pw = get_password_hash("doctorpw")
    
    admin = User(email="admin@test.com", password_hash=admin_pw, role="admin", first_name="Admin", last_name="User")
    patient = User(email="patient@test.com", password_hash=patient_pw, role="patient", first_name="Patient", last_name="One")
    doc_user = User(email="doc@test.com", password_hash=doctor_pw, role="doctor", first_name="Doctor", last_name="House")
    
    db.add_all([admin, patient, doc_user])
    db.flush()
    
    # Create Doctor profile
    working_hours = {
        "monday": [{"start": "09:00", "end": "17:00"}],
        "tuesday": [{"start": "09:00", "end": "12:00"}]
    }
    doctor = Doctor(
        id=doc_user.id,
        specialization="Cardiology",
        working_hours=json.dumps(working_hours),
        slot_duration_minutes=30
    )
    db.add(doctor)
    db.commit()
    
    yield db
    
    # Drop tables
    db.close()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
def fixture_client():
    # Setup dependency overrides locally inside fixture
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    # Teardown dependency override
    app.dependency_overrides.pop(get_db, None)

# Helper to get JWT auth headers
def get_auth_headers(client, email, password):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# TEST CASES
# =========================================================================

def test_user_registration_and_auth_rules(client, db_session):
    res = client.post("/api/auth/register", json={
        "email": "newpatient@test.com",
        "password": "password123",
        "first_name": "New",
        "last_name": "Patient"
    })
    assert res.status_code == 201
    assert res.json()["role"] == "patient"
    
    res2 = client.post("/api/auth/register", json={
        "email": "NewPatient@test.com",
        "password": "password123",
        "first_name": "New",
        "last_name": "Patient"
    })
    assert res2.status_code == 400
    assert "Email already registered" in res2.json()["detail"]


def test_create_doctor_rbac(client, db_session):
    admin_headers = get_auth_headers(client, "admin@test.com", "adminpw")
    patient_headers = get_auth_headers(client, "patient@test.com", "patientpw")
    
    res = client.post("/api/admin/doctors", json={
        "email": "newdoctor@test.com",
        "password": "password123",
        "first_name": "John",
        "last_name": "Watson",
        "specialization": "Neurology",
        "working_hours": json.dumps({"monday": [{"start": "09:00", "end": "12:00"}]}),
        "slot_duration_minutes": 30
    }, headers=admin_headers)
    assert res.status_code == 201
    assert res.json()["email"] == "newdoctor@test.com"
    
    res_pat = client.post("/api/admin/doctors", json={
        "email": "anotherdoc@test.com",
        "password": "password123",
        "first_name": "A",
        "last_name": "Doc",
        "specialization": "Surgery",
        "working_hours": "{}",
        "slot_duration_minutes": 30
    }, headers=patient_headers)
    assert res_pat.status_code == 403


def test_slot_generation(client, db_session):
    doc_user = db_session.query(User).filter(User.email == "doc@test.com").first()
    
    res = client.get(f"/api/appointments/slots?doctor_id={doc_user.id}&date_str=2026-08-31")
    assert res.status_code == 200
    slots = res.json()
    assert len(slots) == 16
    assert slots[0]["start_time"].endswith("09:00:00+00:00")
    assert slots[-1]["end_time"].endswith("17:00:00+00:00")

    admin_headers = get_auth_headers(client, "admin@test.com", "adminpw")
    res_leave = client.post("/api/admin/leaves", json={
        "doctor_id": doc_user.id,
        "leave_date": "2026-09-01"
    }, headers=admin_headers)
    assert res_leave.status_code == 201
    
    res_slots_leave = client.get(f"/api/appointments/slots?doctor_id={doc_user.id}&date_str=2026-09-01")
    assert res_slots_leave.status_code == 200
    assert len(res_slots_leave.json()) == 0


def test_booking_holds_and_conflicts(client, db_session):
    doc_user = db_session.query(User).filter(User.email == "doc@test.com").first()
    patient_headers = get_auth_headers(client, "patient@test.com", "patientpw")
    
    patient2_pw = get_password_hash("patient2pw")
    patient2 = User(email="patient2@test.com", password_hash=patient2_pw, role="patient", first_name="Patient", last_name="Two")
    db_session.add(patient2)
    db_session.commit()
    patient2_headers = get_auth_headers(client, "patient2@test.com", "patient2pw")
    
    start_time = "2026-08-31T10:00:00+00:00"
    end_time = "2026-08-31T10:30:00+00:00"
    
    res = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": start_time,
        "end_time": end_time
    }, headers=patient_headers)
    assert res.status_code == 200
    appt_id = res.json()["id"]
    assert res.json()["status"] == "HELD"
    
    res_conflict = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": start_time,
        "end_time": end_time
    }, headers=patient2_headers)
    assert res_conflict.status_code == 409
    
    res_conf_p2 = client.post(f"/api/appointments/{appt_id}/confirm", json={
        "symptoms": "Headache"
    }, headers=patient2_headers)
    assert res_conf_p2.status_code == 403


def test_expired_hold_releases_slot(client, db_session):
    doc_user = db_session.query(User).filter(User.email == "doc@test.com").first()
    patient_headers = get_auth_headers(client, "patient@test.com", "patientpw")
    
    start_time = "2026-08-31T11:00:00+00:00"
    end_time = "2026-08-31T11:30:00+00:00"
    
    res = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": start_time,
        "end_time": end_time
    }, headers=patient_headers)
    assert res.status_code == 200
    appt_id = res.json()["id"]
    
    appt = db_session.query(Appointment).filter(Appointment.id == appt_id).first()
    appt.hold_expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)
    db_session.commit()
    
    patient2_pw = get_password_hash("patient2pw")
    patient2 = User(email="patient2@test.com", password_hash=patient2_pw, role="patient", first_name="Patient", last_name="Two")
    db_session.add(patient2)
    db_session.commit()
    patient2_headers = get_auth_headers(client, "patient2@test.com", "patient2pw")
    
    res_hold2 = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": start_time,
        "end_time": end_time
    }, headers=patient2_headers)
    assert res_hold2.status_code == 200
    assert res_hold2.json()["status"] == "HELD"
    
    db_session.refresh(appt)
    assert appt.status == "EXPIRED"


def test_cancellation_and_adjacent_slots(client, db_session):
    doc_user = db_session.query(User).filter(User.email == "doc@test.com").first()
    patient_headers = get_auth_headers(client, "patient@test.com", "patientpw")
    
    slot1_start, slot1_end = "2026-08-31T10:00:00+00:00", "2026-08-31T10:30:00+00:00"
    slot2_start, slot2_end = "2026-08-31T10:30:00+00:00", "2026-08-31T11:00:00+00:00"
    
    res1 = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": slot1_start,
        "end_time": slot1_end
    }, headers=patient_headers)
    assert res1.status_code == 200
    appt1_id = res1.json()["id"]
    
    res2 = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": slot2_start,
        "end_time": slot2_end
    }, headers=patient_headers)
    assert res2.status_code == 200
    
    res_cancel = client.post(f"/api/appointments/{appt1_id}/cancel", headers=patient_headers)
    assert res_cancel.status_code == 200
    
    res_rehold = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": slot1_start,
        "end_time": slot1_end
    }, headers=patient_headers)
    assert res_rehold.status_code == 200


def test_rescheduling_mechanisms(client, db_session):
    doc_user = db_session.query(User).filter(User.email == "doc@test.com").first()
    patient_headers = get_auth_headers(client, "patient@test.com", "patientpw")
    
    resA = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": "2026-08-31T10:00:00+00:00",
        "end_time": "2026-08-31T10:30:00+00:00"
    }, headers=patient_headers)
    apptA_id = resA.json()["id"]
    client.post(f"/api/appointments/{apptA_id}/confirm", json={"symptoms": "Flu"}, headers=patient_headers)
    
    p2 = User(email="p2@test.com", password_hash=get_password_hash("pw"), role="patient", first_name="P", last_name="Two")
    db_session.add(p2)
    db_session.commit()
    p2_headers = get_auth_headers(client, "p2@test.com", "pw")
    
    resB = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": "2026-08-31T10:30:00+00:00",
        "end_time": "2026-08-31T11:00:00+00:00"
    }, headers=p2_headers)
    apptB_id = resB.json()["id"]
    client.post(f"/api/appointments/{apptB_id}/confirm", json={"symptoms": "Cough"}, headers=p2_headers)
    
    res_resched_fail = client.post(f"/api/appointments/{apptA_id}/reschedule", json={
        "start_time": "2026-08-31T10:30:00+00:00",
        "end_time": "2026-08-31T11:00:00+00:00"
    }, headers=patient_headers)
    assert res_resched_fail.status_code == 409
    
    apptA = db_session.query(Appointment).filter(Appointment.id == apptA_id).first()
    assert apptA.start_time.isoformat().startswith("2026-08-31T10:00:00")
    
    res_resched_ok = client.post(f"/api/appointments/{apptA_id}/reschedule", json={
        "start_time": "2026-08-31T11:00:00+00:00",
        "end_time": "2026-08-31T11:30:00+00:00"
    }, headers=patient_headers)
    assert res_resched_ok.status_code == 200
    
    res_hold_orig = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": "2026-08-31T10:00:00+00:00",
        "end_time": "2026-08-31T10:30:00+00:00"
    }, headers=p2_headers)
    assert res_hold_orig.status_code == 200


def test_doctor_leave_cascades(client, db_session):
    doc_user = db_session.query(User).filter(User.email == "doc@test.com").first()
    patient_headers = get_auth_headers(client, "patient@test.com", "patientpw")
    admin_headers = get_auth_headers(client, "admin@test.com", "adminpw")
    
    res = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": "2026-08-31T09:00:00+00:00",
        "end_time": "2026-08-31T09:30:00+00:00"
    }, headers=patient_headers)
    appt_id = res.json()["id"]
    client.post(f"/api/appointments/{appt_id}/confirm", json={"symptoms": "Cold"}, headers=patient_headers)
    
    appt = db_session.query(Appointment).filter(Appointment.id == appt_id).first()
    assert appt.status == "CONFIRMED"
    
    res_leave = client.post("/api/admin/leaves", json={
        "doctor_id": doc_user.id,
        "leave_date": "2026-08-31"
    }, headers=admin_headers)
    assert res_leave.status_code == 201
    
    db_session.refresh(appt)
    assert appt.status == "CANCELLED"
    
    notification = db_session.query(Notification).filter(
        Notification.appointment_id == appt_id,
        Notification.type == "leave_cancellation"
    ).first()
    assert notification is not None
    assert notification.status == "PENDING"
    
    res_hold_new = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": "2026-08-31T10:00:00+00:00",
        "end_time": "2026-08-31T10:30:00+00:00"
    }, headers=patient_headers)
    assert res_hold_new.status_code == 400
    assert "on leave" in res_hold_new.json()["detail"]


@patch("backend.app.services.email_service.SendGridAPIClient")
@patch("backend.app.services.calendar_service.build")
def test_integrations_failures_and_retry(mock_build, mock_sg, client, db_session):
    doc_user = db_session.query(User).filter(User.email == "doc@test.com").first()
    patient_headers = get_auth_headers(client, "patient@test.com", "patientpw")
    
    from backend.app.database import settings
    settings.SENDGRID_API_KEY = "SG.testkey"
    settings.GOOGLE_CLIENT_ID = "gclient"
    settings.GOOGLE_CLIENT_SECRET = "gsecret"
    
    gtoken = GoogleToken(
        user_id=db_session.query(User).filter(User.email == "patient@test.com").first().id,
        access_token="encrypted_access",
        refresh_token="encrypted_refresh",
        expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    )
    db_session.add(gtoken)
    db_session.commit()
    
    mock_sg.return_value.send.side_effect = Exception("SendGrid connection timed out")
    mock_build.side_effect = Exception("Google API unavailable")
    
    res = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": "2026-08-31T14:00:00+00:00",
        "end_time": "2026-08-31T14:30:00+00:00"
    }, headers=patient_headers)
    appt_id = res.json()["id"]
    
    res_conf = client.post(f"/api/appointments/{appt_id}/confirm", json={"symptoms": "Allergies"}, headers=patient_headers)
    assert res_conf.status_code == 200
    assert res_conf.json()["status"] == "CONFIRMED"
    
    appt = db_session.query(Appointment).filter(Appointment.id == appt_id).first()
    assert appt.google_event_patient_id is None
    
    notif = db_session.query(Notification).filter(Notification.appointment_id == appt_id).first()
    assert notif is not None
    assert notif.status == "PENDING"
    assert notif.retry_count == 0
    
    from backend.app.services.notification_worker import process_pending_notifications
    import asyncio
    
    asyncio.run(process_pending_notifications(db=db_session))
    
    db_session.refresh(notif)
    assert notif.status == "PENDING"
    assert notif.retry_count == 1
    next_retry = notif.next_retry_at
    if next_retry.tzinfo is None:
        next_retry = next_retry.replace(tzinfo=datetime.timezone.utc)
    assert next_retry > datetime.datetime.now(datetime.timezone.utc)
    assert notif.last_error is not None
    
    settings.SENDGRID_API_KEY = ""
    settings.GOOGLE_CLIENT_ID = ""
    settings.GOOGLE_CLIENT_SECRET = ""


@patch("backend.app.services.gemini_service.genai.GenerativeModel")
def test_llm_failures_and_medications(mock_gen_model, client, db_session):
    doc_user = db_session.query(User).filter(User.email == "doc@test.com").first()
    patient_headers = get_auth_headers(client, "patient@test.com", "patientpw")
    doctor_headers = get_auth_headers(client, "doc@test.com", "doctorpw")
    
    from backend.app.database import settings
    settings.GEMINI_API_KEY = "fake-key"
    
    mock_model_instance = MagicMock()
    mock_gen_model.return_value = mock_model_instance
    mock_model_instance.generate_content.return_value.text = "This is not JSON at all!"
    
    res_hold = client.post("/api/appointments/hold", json={
        "doctor_id": doc_user.id,
        "start_time": "2026-08-31T15:00:00+00:00",
        "end_time": "2026-08-31T15:30:00+00:00"
    }, headers=patient_headers)
    appt_id = res_hold.json()["id"]
    
    res_conf = client.post(f"/api/appointments/{appt_id}/confirm", json={"symptoms": "Stomach Ache"}, headers=patient_headers)
    assert res_conf.status_code == 200
    assert res_conf.json()["ai_urgency_level"] == "Medium"
    
    res_comp = client.post(f"/api/clinical/appointments/{appt_id}/complete", json={
        "clinical_notes": "Patient has mild indigestion.",
        "prescription": "Antacid 10mg",
        "medications": [
            {
                "name": "Antacid",
                "dosage": "10mg",
                "frequency": "twice daily",
                "reminder_times": ["08:00", "20:00"],
                "start_date": "2026-08-31",
                "end_date": "2026-09-01"
            }
        ]
    }, headers=doctor_headers)
    assert res_comp.status_code == 200
    assert res_comp.json()["status"] == "COMPLETED"
    
    med = db_session.query(Medication).filter(Medication.appointment_id == appt_id).first()
    assert med is not None
    assert med.name == "Antacid"
    
    reminders = db_session.query(Notification).filter(
        Notification.appointment_id == appt_id,
        Notification.type == "medication_reminder"
    ).all()
    assert len(reminders) > 0
    for r in reminders:
        assert r.status == "PENDING"
        assert "Antacid" in r.subject
        
    settings.GEMINI_API_KEY = ""
