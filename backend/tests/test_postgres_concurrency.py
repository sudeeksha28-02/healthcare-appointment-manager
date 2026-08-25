import pytest
import os
import datetime
import concurrent.futures
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

POSTGRES_TEST_URL = os.environ.get(
    "POSTGRES_TEST_DATABASE_URL", 
    "postgresql://postgres:postgres@localhost:5432/healthcare_test"
)

def is_postgres_available():
    try:
        engine = create_engine(POSTGRES_TEST_URL, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

# Skip entire file if PostgreSQL database is not reachable
pytestmark = pytest.mark.skipif(
    not is_postgres_available(),
    reason="PostgreSQL database not available on localhost:5432. Start PostgreSQL/Docker to run this integration test."
)

@pytest.fixture(scope="module")
def pg_engine():
    engine = create_engine(POSTGRES_TEST_URL)
    from backend.app.database import Base
    from backend.app.models import User, Doctor, Appointment, DoctorLeave, Medication, Notification, GoogleToken
    
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def pg_session(pg_engine):
    Session = sessionmaker(bind=pg_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

def test_pg_schema_and_exclusion_constraint(pg_engine):
    """
    Verifies that btree_gist extension and prevent_doctor_double_booking exclusion constraint exist in PostgreSQL.
    """
    with pg_engine.connect() as conn:
        res = conn.execute(text("""
            SELECT conname 
            FROM pg_constraint 
            WHERE conname = 'prevent_doctor_double_booking'
        """)).fetchone()
        assert res is not None, "PostgreSQL exclusion constraint 'prevent_doctor_double_booking' was not created."

def test_pg_concurrent_identical_booking(pg_engine):
    """
    Scenario A: Concurrent identical booking attempt on PostgreSQL.
    Exactly 1 transaction succeeds; others fail safely with exclusion constraint error.
    """
    from backend.app.models import User, Doctor, Appointment
    from backend.app.auth.security import get_password_hash
    
    Session = sessionmaker(bind=pg_engine)
    s_init = Session()
    
    # Create test doctor and 5 patients
    doc_user = User(email="pg_doc1@test.com", password_hash=get_password_hash("pw"), role="doctor", first_name="PG", last_name="Doc1")
    s_init.add(doc_user)
    s_init.flush()
    doctor = Doctor(id=doc_user.id, specialization="General", working_hours="{}", slot_duration_minutes=30)
    s_init.add(doctor)
    
    patients = []
    for i in range(5):
        p = User(email=f"pg_pat{i}@test.com", password_hash=get_password_hash("pw"), role="patient", first_name="P", last_name=str(i))
        s_init.add(p)
        patients.append(p)
    s_init.commit()
    doc_id = doctor.id
    patient_ids = [p.id for p in patients]
    s_init.close()
    
    start_dt = datetime.datetime(2026, 9, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)
    end_dt = datetime.datetime(2026, 9, 1, 10, 30, 0, tzinfo=datetime.timezone.utc)
    
    def book_slot(pid):
        sess = Session()
        try:
            appt = Appointment(
                patient_id=pid,
                doctor_id=doc_id,
                start_time=start_dt,
                end_time=end_dt,
                status="HELD",
                hold_expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
            )
            sess.add(appt)
            sess.commit()
            sess.close()
            return True
        except Exception:
            sess.rollback()
            sess.close()
            return False
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(book_slot, patient_ids))
        
    assert results.count(True) == 1, f"Expected exactly 1 booking success on PG, got {results.count(True)}"
    assert results.count(False) == 4, f"Expected 4 failures on PG, got {results.count(False)}"

def test_pg_overlapping_different_start_times(pg_session):
    """
    Scenario B: Overlapping appointments with different start times (10:00-10:30 vs 10:15-10:45).
    PostgreSQL tsrange && operator must reject the overlapping attempt.
    """
    from backend.app.models import User, Doctor, Appointment
    from backend.app.auth.security import get_password_hash
    from sqlalchemy.exc import IntegrityError
    
    doc_user = User(email="pg_doc2@test.com", password_hash=get_password_hash("pw"), role="doctor", first_name="PG", last_name="Doc2")
    pg_session.add(doc_user)
    pg_session.flush()
    doctor = Doctor(id=doc_user.id, specialization="Cardiology", working_hours="{}", slot_duration_minutes=30)
    pg_session.add(doctor)
    
    p1 = User(email="pg_p1@test.com", password_hash=get_password_hash("pw"), role="patient", first_name="P", last_name="1")
    p2 = User(email="pg_p2@test.com", password_hash=get_password_hash("pw"), role="patient", first_name="P", last_name="2")
    pg_session.add_all([p1, p2])
    pg_session.commit()
    
    # Appt 1: 10:00 - 10:30
    a1 = Appointment(
        patient_id=p1.id, doctor_id=doctor.id,
        start_time=datetime.datetime(2026, 9, 2, 10, 0, 0, tzinfo=datetime.timezone.utc),
        end_time=datetime.datetime(2026, 9, 2, 10, 30, 0, tzinfo=datetime.timezone.utc),
        status="CONFIRMED"
    )
    pg_session.add(a1)
    pg_session.commit()
    
    # Attempt Appt 2: 10:15 - 10:45 (Overlaps 10:00-10:30)
    a2 = Appointment(
        patient_id=p2.id, doctor_id=doctor.id,
        start_time=datetime.datetime(2026, 9, 2, 10, 15, 0, tzinfo=datetime.timezone.utc),
        end_time=datetime.datetime(2026, 9, 2, 10, 45, 0, tzinfo=datetime.timezone.utc),
        status="HELD"
    )
    pg_session.add(a2)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_pg_adjacent_intervals(pg_session):
    """
    Scenario C: Adjacent intervals [10:00, 10:30) and [10:30, 11:00) must succeed on PostgreSQL.
    """
    from backend.app.models import User, Doctor, Appointment
    from backend.app.auth.security import get_password_hash
    
    doc_user = User(email="pg_doc3@test.com", password_hash=get_password_hash("pw"), role="doctor", first_name="PG", last_name="Doc3")
    pg_session.add(doc_user)
    pg_session.flush()
    doctor = Doctor(id=doc_user.id, specialization="Pediatrics", working_hours="{}", slot_duration_minutes=30)
    pg_session.add(doctor)
    
    p1 = User(email="pg_p3@test.com", password_hash=get_password_hash("pw"), role="patient", first_name="P", last_name="3")
    pg_session.add(p1)
    pg_session.commit()
    
    a1 = Appointment(
        patient_id=p1.id, doctor_id=doctor.id,
        start_time=datetime.datetime(2026, 9, 3, 10, 0, 0, tzinfo=datetime.timezone.utc),
        end_time=datetime.datetime(2026, 9, 3, 10, 30, 0, tzinfo=datetime.timezone.utc),
        status="CONFIRMED"
    )
    a2 = Appointment(
        patient_id=p1.id, doctor_id=doctor.id,
        start_time=datetime.datetime(2026, 9, 3, 10, 30, 0, tzinfo=datetime.timezone.utc),
        end_time=datetime.datetime(2026, 9, 3, 11, 0, 0, tzinfo=datetime.timezone.utc),
        status="CONFIRMED"
    )
    pg_session.add_all([a1, a2])
    pg_session.commit()
    assert a1.id is not None
    assert a2.id is not None

def test_pg_cancelled_appointment_releases_slot(pg_session):
    """
    Scenario D: CANCELLED appointment does not participate in exclusion constraint.
    New booking for same slot must succeed.
    """
    from backend.app.models import User, Doctor, Appointment
    from backend.app.auth.security import get_password_hash
    
    doc_user = User(email="pg_doc4@test.com", password_hash=get_password_hash("pw"), role="doctor", first_name="PG", last_name="Doc4")
    pg_session.add(doc_user)
    pg_session.flush()
    doctor = Doctor(id=doc_user.id, specialization="Dermatology", working_hours="{}", slot_duration_minutes=30)
    pg_session.add(doctor)
    
    p1 = User(email="pg_p4@test.com", password_hash=get_password_hash("pw"), role="patient", first_name="P", last_name="4")
    pg_session.add(p1)
    pg_session.commit()
    
    start_dt = datetime.datetime(2026, 9, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
    end_dt = datetime.datetime(2026, 9, 4, 10, 30, 0, tzinfo=datetime.timezone.utc)
    
    a1 = Appointment(patient_id=p1.id, doctor_id=doctor.id, start_time=start_dt, end_time=end_dt, status="CANCELLED")
    pg_session.add(a1)
    pg_session.commit()
    
    a2 = Appointment(patient_id=p1.id, doctor_id=doctor.id, start_time=start_dt, end_time=end_dt, status="CONFIRMED")
    pg_session.add(a2)
    pg_session.commit()
    assert a2.id is not None

def test_pg_expired_hold_releases_slot(pg_session):
    """
    Scenario E: EXPIRED hold does not block new booking on PostgreSQL.
    """
    from backend.app.models import User, Doctor, Appointment
    from backend.app.auth.security import get_password_hash
    
    doc_user = User(email="pg_doc5@test.com", password_hash=get_password_hash("pw"), role="doctor", first_name="PG", last_name="Doc5")
    pg_session.add(doc_user)
    pg_session.flush()
    doctor = Doctor(id=doc_user.id, specialization="Neurology", working_hours="{}", slot_duration_minutes=30)
    pg_session.add(doctor)
    
    p1 = User(email="pg_p5@test.com", password_hash=get_password_hash("pw"), role="patient", first_name="P", last_name="5")
    pg_session.add(p1)
    pg_session.commit()
    
    start_dt = datetime.datetime(2026, 9, 5, 10, 0, 0, tzinfo=datetime.timezone.utc)
    end_dt = datetime.datetime(2026, 9, 5, 10, 30, 0, tzinfo=datetime.timezone.utc)
    
    a1 = Appointment(patient_id=p1.id, doctor_id=doctor.id, start_time=start_dt, end_time=end_dt, status="EXPIRED")
    pg_session.add(a1)
    pg_session.commit()
    
    a2 = Appointment(patient_id=p1.id, doctor_id=doctor.id, start_time=start_dt, end_time=end_dt, status="HELD")
    pg_session.add(a2)
    pg_session.commit()
    assert a2.id is not None

def test_pg_held_vs_confirmed(pg_session):
    """
    Scenario F: Active HELD appointment blocks overlapping CONFIRMED appointment.
    """
    from backend.app.models import User, Doctor, Appointment
    from backend.app.auth.security import get_password_hash
    from sqlalchemy.exc import IntegrityError
    
    doc_user = User(email="pg_doc6@test.com", password_hash=get_password_hash("pw"), role="doctor", first_name="PG", last_name="Doc6")
    pg_session.add(doc_user)
    pg_session.flush()
    doctor = Doctor(id=doc_user.id, specialization="General", working_hours="{}", slot_duration_minutes=30)
    pg_session.add(doctor)
    
    p1 = User(email="pg_p6@test.com", password_hash=get_password_hash("pw"), role="patient", first_name="P", last_name="6")
    p2 = User(email="pg_p7@test.com", password_hash=get_password_hash("pw"), role="patient", first_name="P", last_name="7")
    pg_session.add_all([p1, p2])
    pg_session.commit()
    
    start_dt = datetime.datetime(2026, 9, 6, 10, 0, 0, tzinfo=datetime.timezone.utc)
    end_dt = datetime.datetime(2026, 9, 6, 10, 30, 0, tzinfo=datetime.timezone.utc)
    
    a1 = Appointment(patient_id=p1.id, doctor_id=doctor.id, start_time=start_dt, end_time=end_dt, status="HELD")
    pg_session.add(a1)
    pg_session.commit()
    
    a2 = Appointment(patient_id=p2.id, doctor_id=doctor.id, start_time=start_dt, end_time=end_dt, status="CONFIRMED")
    pg_session.add(a2)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_pg_completed_appointment_blocks(pg_session):
    """
    Scenario G: COMPLETED appointment continues to prevent overlapping active attempt.
    """
    from backend.app.models import User, Doctor, Appointment
    from backend.app.auth.security import get_password_hash
    from sqlalchemy.exc import IntegrityError
    
    doc_user = User(email="pg_doc7@test.com", password_hash=get_password_hash("pw"), role="doctor", first_name="PG", last_name="Doc7")
    pg_session.add(doc_user)
    pg_session.flush()
    doctor = Doctor(id=doc_user.id, specialization="Cardiology", working_hours="{}", slot_duration_minutes=30)
    pg_session.add(doctor)
    
    p1 = User(email="pg_p8@test.com", password_hash=get_password_hash("pw"), role="patient", first_name="P", last_name="8")
    p2 = User(email="pg_p9@test.com", password_hash=get_password_hash("pw"), role="patient", first_name="P", last_name="9")
    pg_session.add_all([p1, p2])
    pg_session.commit()
    
    start_dt = datetime.datetime(2026, 9, 7, 10, 0, 0, tzinfo=datetime.timezone.utc)
    end_dt = datetime.datetime(2026, 9, 7, 10, 30, 0, tzinfo=datetime.timezone.utc)
    
    a1 = Appointment(patient_id=p1.id, doctor_id=doctor.id, start_time=start_dt, end_time=end_dt, status="COMPLETED")
    pg_session.add(a1)
    pg_session.commit()
    
    a2 = Appointment(patient_id=p2.id, doctor_id=doctor.id, start_time=start_dt, end_time=end_dt, status="HELD")
    pg_session.add(a2)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()
