import pytest
import concurrent.futures
import threading
import os
os.environ["TESTING"] = "1"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.main import app
from backend.app.database import Base, get_db
from backend.app.models import User, Doctor
from backend.app.auth.security import get_password_hash

CONCURRENCY_DATABASE_URL = "sqlite:///file:concurrency_db?mode=memory&cache=shared"
engine = create_engine(
    CONCURRENCY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db_concurrency():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(name="setup_db")
def fixture_setup_db():
    app.dependency_overrides[get_db] = override_get_db_concurrency
    
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Create doctor
    doc_pw = get_password_hash("doctorpw")
    doc_user = User(email="concur_doc@test.com", password_hash=doc_pw, role="doctor", first_name="Doctor", last_name="Who")
    db.add(doc_user)
    db.flush()
    
    # Working hours: Monday 09:00 - 17:00
    doctor = Doctor(
        id=doc_user.id,
        specialization="General",
        working_hours='{"monday": [{"start": "09:00", "end": "17:00"}]}',
        slot_duration_minutes=30
    )
    db.add(doctor)
    
    # Create 10 patients
    for i in range(1, 11):
        email = f"c_patient{i}@test.com"
        pat_pw = get_password_hash("patpw")
        pat_user = User(email=email, password_hash=pat_pw, role="patient", first_name="P", last_name=str(i))
        db.add(pat_user)
    
    db.commit()
    db.close()
    
    yield
    
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)

def test_concurrent_booking_attempts(setup_db):
    client = TestClient(app)
    
    # Login all 10 patients and get auth headers
    headers_list = []
    for i in range(1, 11):
        res = client.post("/api/auth/login", json={"email": f"c_patient{i}@test.com", "password": "patpw"})
        assert res.status_code == 200
        token = res.json()["access_token"]
        headers_list.append({"Authorization": f"Bearer {token}"})
        
    doc = TestingSessionLocal().query(Doctor).first()
    doctor_id = doc.id
    
    # Slot details: 2026-08-31 is a Monday
    start_time = "2026-08-31T10:00:00+00:00"
    end_time = "2026-08-31T10:30:00+00:00"
    
    payload = {
        "doctor_id": doctor_id,
        "start_time": start_time,
        "end_time": end_time
    }
    
    lock = threading.Lock()
    def attempt_booking(headers):
        with lock:
            return client.post("/api/appointments/hold", json=payload, headers=headers)
        
    # Execute booking attempts using ThreadPoolExecutor
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(attempt_booking, headers) for headers in headers_list]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    # Verify results: Exactly 1 request must return 200 OK (holding slot)
    # The other 9 requests must return 409 Conflict
    success_count = 0
    conflict_count = 0
    other_count = 0
    
    for r in results:
        if r.status_code == 200:
            success_count += 1
        elif r.status_code == 409:
            conflict_count += 1
        else:
            other_count += 1
            print(f"Unexpected response: {r.status_code} - {r.text}")
            
    assert success_count == 1, f"Expected exactly 1 booking to succeed, but {success_count} succeeded."
    assert conflict_count == 9, f"Expected exactly 9 booking attempts to conflict, but got {conflict_count}."
    assert other_count == 0, f"Expected 0 other errors, but got {other_count}."
