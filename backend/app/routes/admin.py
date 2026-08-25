import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime, timezone
from backend.app.database import get_db
from backend.app.models import User, Doctor, DoctorLeave, Appointment
from backend.app.schemas import DoctorCreate, DoctorOut, DoctorLeaveCreate, DoctorLeaveOut, DoctorUpdate
from backend.app.auth.security import RoleChecker, get_password_hash
from backend.app.services.email_service import queue_leave_cancellation
from backend.app.services.calendar_service import delete_appointment_calendar_events

router = APIRouter(prefix="/admin", tags=["Admin Operations"])

# Role checker for Admin only
admin_only = RoleChecker(["admin"])

@router.post("/doctors", response_model=DoctorOut, status_code=status.HTTP_201_CREATED)
def create_doctor(doc_in: DoctorCreate, db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    """
    Creates a new doctor. Can only be invoked by an admin.
    Performs case-insensitive email check.
    """
    email_lower = doc_in.email.lower()
    existing_user = db.query(User).filter(func.lower(User.email) == email_lower).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
        
    hashed_password = get_password_hash(doc_in.password)
    new_user = User(
        email=email_lower,
        password_hash=hashed_password,
        role="doctor",
        first_name=doc_in.first_name,
        last_name=doc_in.last_name
    )
    db.add(new_user)
    db.flush()  # Get user ID
    
    # Validate working hours format
    try:
        json.loads(doc_in.working_hours)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="working_hours must be a valid JSON string"
        )

    doctor_profile = Doctor(
        id=new_user.id,
        specialization=doc_in.specialization,
        working_hours=doc_in.working_hours,
        slot_duration_minutes=doc_in.slot_duration_minutes
    )
    db.add(doctor_profile)
    db.commit()
    db.refresh(new_user)
    db.refresh(doctor_profile)
    
    return DoctorOut(
        id=doctor_profile.id,
        first_name=new_user.first_name,
        last_name=new_user.last_name,
        email=new_user.email,
        specialization=doctor_profile.specialization,
        working_hours=doctor_profile.working_hours,
        slot_duration_minutes=doctor_profile.slot_duration_minutes
    )

@router.get("/doctors", response_model=list[DoctorOut])
def list_doctors(db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["admin", "patient"]))):
    """
    Lists all doctors in the system. Accessible by admins and patients.
    """
    docs = db.query(Doctor).join(User).all()
    results = []
    for doc in docs:
        results.append(DoctorOut(
            id=doc.id,
            first_name=doc.user.first_name,
            last_name=doc.user.last_name,
            email=doc.user.email,
            specialization=doc.specialization,
            working_hours=doc.working_hours,
            slot_duration_minutes=doc.slot_duration_minutes
        ))
    return results

@router.put("/doctors/{doctor_id}", response_model=DoctorOut)
def update_doctor(doctor_id: int, doc_in: DoctorUpdate, db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    doc = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
        
    if doc_in.specialization is not None:
        doc.specialization = doc_in.specialization
    if doc_in.slot_duration_minutes is not None:
        doc.slot_duration_minutes = doc_in.slot_duration_minutes
    if doc_in.working_hours is not None:
        try:
            json.loads(doc_in.working_hours)
            doc.working_hours = doc_in.working_hours
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="working_hours must be a valid JSON string")
            
    db.commit()
    db.refresh(doc)
    return DoctorOut(
        id=doc.id,
        first_name=doc.user.first_name,
        last_name=doc.user.last_name,
        email=doc.user.email,
        specialization=doc.specialization,
        working_hours=doc.working_hours,
        slot_duration_minutes=doc.slot_duration_minutes
    )

@router.post("/leaves", response_model=DoctorLeaveOut, status_code=status.HTTP_201_CREATED)
def add_doctor_leave(leave_in: DoctorLeaveCreate, db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    """
    Registers a leave day for a doctor. Can only be done by admin.
    Automatically:
    - Verifies the leave date is in the future.
    - Cancels all active (HELD or CONFIRMED) appointments for that doctor on that date.
    - Triggers notification queueing and Google Calendar removal.
    """
    # 1. Verify doctor exists
    doctor = db.query(Doctor).filter(Doctor.id == leave_in.doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
        
    # 2. Verify date is in the future
    if leave_in.leave_date <= date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Leave date must be in the future"
        )
        
    # 3. Check for existing leave on the same date (uniqueness constraint helper)
    existing_leave = db.query(DoctorLeave).filter(
        DoctorLeave.doctor_id == leave_in.doctor_id,
        DoctorLeave.leave_date == leave_in.leave_date
    ).first()
    if existing_leave:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doctor is already marked on leave for this date"
        )
        
    # 4. Insert leave
    leave = DoctorLeave(
        doctor_id=leave_in.doctor_id,
        leave_date=leave_in.leave_date
    )
    db.add(leave)
    db.flush()  # Save leave record to database context

    # 5. Cancel affected appointments
    # Need to match all appointments on leave_date for this doctor with status HELD or CONFIRMED
    start_of_day = datetime.combine(leave_in.leave_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day = datetime.combine(leave_in.leave_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    affected_appointments = db.query(Appointment).filter(
        Appointment.doctor_id == leave_in.doctor_id,
        Appointment.status.in_(["HELD", "CONFIRMED"]),
        Appointment.start_time >= start_of_day,
        Appointment.start_time <= end_of_day
    ).all()
    
    for appointment in affected_appointments:
        appointment.status = "CANCELLED"
        
        # Queue email cancellation notification
        queue_leave_cancellation(db, appointment)
        
        # Attempt to delete Google Calendar events
        try:
            delete_appointment_calendar_events(db, appointment)
        except Exception as ex:
            # Audit log/error preserve
            print(f"Error deleting Google Calendar events for affected appointment {appointment.id}: {str(ex)}")
            
    db.commit()
    db.refresh(leave)
    return leave
