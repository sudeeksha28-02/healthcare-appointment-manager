import json
import logging
import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from sqlalchemy.exc import IntegrityError, OperationalError
from backend.app.database import get_db
from backend.app.models import User, Doctor, DoctorLeave, Appointment
from backend.app.schemas import (
    AppointmentHoldRequest, AppointmentConfirmRequest, AppointmentOut, AppointmentRescheduleRequest
)
from backend.app.auth.security import get_current_user, RoleChecker
from backend.app.services.gemini_service import analyze_symptoms
from backend.app.services.email_service import queue_booking_confirmation, queue_cancellation
from backend.app.services.calendar_service import (
    create_appointment_calendar_events, update_appointment_calendar_events, delete_appointment_calendar_events
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/appointments", tags=["Appointments & Booking"])

def ensure_tz_aware(dt: datetime.datetime | None) -> datetime.datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt

def clean_expired_holds(db: Session):
    """
    Identifies all expired holds and marks them EXPIRED.
    """
    db.expire_all()
    now = datetime.datetime.now(datetime.timezone.utc)
    held_appts = db.query(Appointment).filter(Appointment.status == "HELD").all()
    has_expired = False
    for appt in held_appts:
        if appt.hold_expires_at:
            exp_time = ensure_tz_aware(appt.hold_expires_at)
            if exp_time < now:
                appt.status = "EXPIRED"
                has_expired = True
    if has_expired:
        db.commit()

@router.get("/slots")
def get_available_slots(doctor_id: int, date_str: str, db: Session = Depends(get_db)):
    """
    Fetches available slots for a doctor on a specific date (YYYY-MM-DD).
    Generates 30-minute slots based on doctor's working hours,
    omitting slots that overlap with leave days or existing bookings.
    """
    # 1. Validate doctor
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
        
    try:
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # 2. Check if doctor is on leave
    leave = db.query(DoctorLeave).filter(
        DoctorLeave.doctor_id == doctor_id,
        DoctorLeave.leave_date == target_date
    ).first()
    if leave:
        return []  # Doctor is on leave, no slots

    # 3. Get working hours for the day of the week
    weekday_map = {
        0: "monday", 1: "tuesday", 2: "wednesday", 
        3: "thursday", 4: "friday", 5: "saturday", 6: "sunday"
    }
    weekday_name = weekday_map[target_date.weekday()]
    
    try:
        hours_data = json.loads(doctor.working_hours)
    except Exception:
        hours_data = {}

    day_slots_config = hours_data.get(weekday_name, [])
    if not day_slots_config:
        return []

    # 4. Clean expired holds first to make slots accurate
    clean_expired_holds(db)

    # 5. Fetch active appointments on that day
    start_of_day = datetime.datetime.combine(target_date, datetime.time.min).replace(tzinfo=datetime.timezone.utc)
    end_of_day = datetime.datetime.combine(target_date, datetime.time.max).replace(tzinfo=datetime.timezone.utc)
    
    active_appointments = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.status.in_(["HELD", "CONFIRMED", "COMPLETED"]),
        Appointment.start_time >= start_of_day,
        Appointment.start_time <= end_of_day
    ).all()

    # Generate prospective slots
    available_slots = []
    duration = datetime.timedelta(minutes=doctor.slot_duration_minutes)

    for config in day_slots_config:
        try:
            start_hour, start_min = map(int, config["start"].split(":"))
            end_hour, end_min = map(int, config["end"].split(":"))
        except Exception:
            continue

        work_start = datetime.datetime.combine(target_date, datetime.time(hour=start_hour, minute=start_min)).replace(tzinfo=datetime.timezone.utc)
        work_end = datetime.datetime.combine(target_date, datetime.time(hour=end_hour, minute=end_min)).replace(tzinfo=datetime.timezone.utc)
        
        current_time = work_start
        while current_time + duration <= work_end:
            slot_start = current_time
            slot_end = current_time + duration
            
            # Check overlap with existing active appointments
            overlap = False
            for appt in active_appointments:
                # Half-open time range comparison [start_time, end_time)
                # Overlaps if slot_start < appt.end_time AND slot_end > appt.start_time
                appt_start = ensure_tz_aware(appt.start_time)
                appt_end = ensure_tz_aware(appt.end_time)
                if slot_start < appt_end and slot_end > appt_start:
                    overlap = True
                    break
                    
            if not overlap:
                available_slots.append({
                    "start_time": slot_start.isoformat(),
                    "end_time": slot_end.isoformat()
                })
                
            current_time += duration

    return available_slots

@router.post("/hold", response_model=AppointmentOut)
def hold_appointment(hold_in: AppointmentHoldRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Creates a temporary 5-minute hold on a slot.
    Rely on the PostgreSQL exclusion constraint for final concurrency guarantee.
    """
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can hold slots")

    # 1. Clean expired holds first
    clean_expired_holds(db)

    # 2. Check that target start time is in the future
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if hold_in.start_time <= now_utc:
        raise HTTPException(status_code=400, detail="Booking slot must be in the future")

    # 3. Check if doctor exists
    doctor = db.query(Doctor).filter(Doctor.id == hold_in.doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # 4. Check if doctor is on leave that date
    slot_date = hold_in.start_time.date()
    leave = db.query(DoctorLeave).filter(
        DoctorLeave.doctor_id == hold_in.doctor_id,
        DoctorLeave.leave_date == slot_date
    ).first()
    if leave:
        raise HTTPException(status_code=400, detail="Doctor is on leave on the selected date")

    # 5. Check if slot matches doctor's working hours
    weekday_map = {
        0: "monday", 1: "tuesday", 2: "wednesday", 
        3: "thursday", 4: "friday", 5: "saturday", 6: "sunday"
    }
    weekday_name = weekday_map[slot_date.weekday()]
    try:
        hours_data = json.loads(doctor.working_hours)
    except Exception:
        hours_data = {}
        
    day_slots_config = hours_data.get(weekday_name, [])
    in_working_hours = False
    
    for config in day_slots_config:
        try:
            sh, sm = map(int, config["start"].split(":"))
            eh, em = map(int, config["end"].split(":"))
            work_start_time = datetime.time(hour=sh, minute=sm)
            work_end_time = datetime.time(hour=eh, minute=em)
            
            slot_start_time = hold_in.start_time.time()
            slot_end_time = hold_in.end_time.time()
            
            if slot_start_time >= work_start_time and slot_end_time <= work_end_time:
                in_working_hours = True
                break
        except Exception:
            continue

    if not in_working_hours:
        raise HTTPException(status_code=400, detail="Selected slot falls outside doctor working hours")

    # 6. Try to create the HELD appointment inside a database transaction block
    hold_duration = datetime.timedelta(minutes=5)
    hold_expires = now_utc + hold_duration

    new_appointment = Appointment(
        patient_id=current_user.id,
        doctor_id=hold_in.doctor_id,
        start_time=hold_in.start_time,
        end_time=hold_in.end_time,
        status="HELD",
        hold_expires_at=hold_expires
    )

    db.add(new_appointment)
    try:
        db.commit()
        db.refresh(new_appointment)
        return new_appointment
    except Exception as ex:
        try:
            db.expunge(new_appointment)
            db.rollback()
        except Exception:
            pass
        logger.warning(f"Booking collision occurred on slot {hold_in.start_time} for doctor {hold_in.doctor_id}. Reason: {str(ex)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This slot is no longer available. A simultaneous booking attempt has secured the slot."
        )

@router.post("/{appointment_id}/confirm", response_model=AppointmentOut)
def confirm_appointment(appointment_id: int, confirm_in: AppointmentConfirmRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Confirms an appointment under a temporary slot hold.
    Validates hold expiry, symptoms pre-visit AI processing, and triggers integrations.
    """
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Only patient who owns it can confirm
    if appt.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not own this slot hold")

    if appt.status != "HELD":
        raise HTTPException(status_code=400, detail=f"Appointment cannot be confirmed in state {appt.status}")

    # Check expiration
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if ensure_tz_aware(appt.hold_expires_at) < now_utc:
        appt.status = "EXPIRED"
        db.commit()
        raise HTTPException(status_code=400, detail="Hold has expired. Please select the slot again.")

    # Call Gemini for Pre-Visit symptom analysis (wrapped in try/except)
    ai_analysis = None
    try:
        ai_analysis = analyze_symptoms(confirm_in.symptoms)
    except Exception as ex:
        logger.error(f"Gemini symptom analysis crashed: {str(ex)}")

    # Update appointment details
    appt.status = "CONFIRMED"
    appt.symptoms = confirm_in.symptoms
    
    if ai_analysis:
        appt.ai_urgency_level = ai_analysis.get("urgency_level")
        appt.ai_chief_complaint = ai_analysis.get("chief_complaint")
        appt.ai_suggested_questions = json.dumps(ai_analysis.get("suggested_questions", []))
    else:
        appt.ai_urgency_level = "Medium"
        appt.ai_chief_complaint = "Symptom reporting (AI summary unavailable)"
        appt.ai_suggested_questions = json.dumps([])

    db.commit()
    db.refresh(appt)

    # Queue Email Notification
    try:
        queue_booking_confirmation(db, appt)
    except Exception as email_err:
        logger.error(f"Queueing email notification failed: {str(email_err)}")

    # Trigger Google Calendar Sync (non-blocking)
    try:
        create_appointment_calendar_events(db, appt)
    except Exception as cal_err:
        logger.error(f"Syncing Google Calendar failed: {str(cal_err)}")

    # Retrieve parsed suggested questions as list before sending
    if appt.ai_suggested_questions:
        appt.ai_suggested_questions = json.loads(appt.ai_suggested_questions)

    return appt

@router.post("/{appointment_id}/reschedule", response_model=AppointmentOut)
def reschedule_appointment(appointment_id: int, resched_in: AppointmentRescheduleRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Reschedules an existing appointment.
    Transactional safety: checks limits first; the original slot is preserved if the target slot cannot be secured.
    """
    clean_expired_holds(db)
    
    # 1. Fetch current appointment
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Authorize: patient owner or admin
    if current_user.role == "patient" and appt.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not own this appointment")
        
    if appt.status not in ["CONFIRMED", "HELD"]:
        raise HTTPException(status_code=400, detail="Only active appointments can be rescheduled")

    # 2. Check future date
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if resched_in.start_time <= now_utc:
        raise HTTPException(status_code=400, detail="Reschedule slot must be in the future")

    # 3. Check leave conflict
    target_date = resched_in.start_time.date()
    leave = db.query(DoctorLeave).filter(
        DoctorLeave.doctor_id == appt.doctor_id,
        DoctorLeave.leave_date == target_date
    ).first()
    if leave:
        raise HTTPException(status_code=400, detail="Doctor is on leave on the selected date")

    # 4. Check doctor working hours
    weekday_map = {
        0: "monday", 1: "tuesday", 2: "wednesday", 
        3: "thursday", 4: "friday", 5: "saturday", 6: "sunday"
    }
    weekday_name = weekday_map[target_date.weekday()]
    try:
        hours_data = json.loads(appt.doctor.working_hours)
    except Exception:
        hours_data = {}
        
    day_slots_config = hours_data.get(weekday_name, [])
    in_working_hours = False
    
    for config in day_slots_config:
        try:
            sh, sm = map(int, config["start"].split(":"))
            eh, em = map(int, config["end"].split(":"))
            work_start_time = datetime.time(hour=sh, minute=sm)
            work_end_time = datetime.time(hour=eh, minute=em)
            if resched_in.start_time.time() >= work_start_time and resched_in.end_time.time() <= work_end_time:
                in_working_hours = True
                break
        except Exception:
            continue

    if not in_working_hours:
        raise HTTPException(status_code=400, detail="Reschedule slot falls outside doctor working hours")

    # Store original time details in case of rollback
    orig_start = appt.start_time
    orig_end = appt.end_time
    orig_status = appt.status

    # 5. Perform slot update inside a transaction block
    # We update the time first. If there's an exclusion conflict, SQL will throw exception, triggering rollback.
    try:
        appt.start_time = resched_in.start_time
        appt.end_time = resched_in.end_time
        appt.status = "CONFIRMED" # Automatically transition to confirmed (or preserve held if they held)
        db.commit()
        db.refresh(appt)
    except (IntegrityError, OperationalError) as ex:
        db.rollback()
        # Restore local objects status
        logger.warning(f"Reschedule conflict: new slot no longer available. Reverting to original slot times: {str(ex)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The target slot is already booked or held. Your original appointment slot is preserved."
        )

    # 6. Update Google Calendar Events (non-blocking)
    try:
        update_appointment_calendar_events(db, appt)
    except Exception as cal_err:
        logger.error(f"Failed to update calendar events: {str(cal_err)}")

    if appt.ai_suggested_questions and isinstance(appt.ai_suggested_questions, str):
        appt.ai_suggested_questions = json.loads(appt.ai_suggested_questions)

    return appt

@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(appointment_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Cancels an appointment, freeing up the slot instantly by removing the HELD/CONFIRMED status constraint lock.
    """
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Authorize: patient owner, doctor, or admin
    if current_user.role == "patient" and appt.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not own this appointment")
    if current_user.role == "doctor" and appt.doctor_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not the doctor for this appointment")

    if appt.status not in ["HELD", "CONFIRMED"]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel appointment in status {appt.status}")

    appt.status = "CANCELLED"
    db.commit()

    # Queue Cancellation Notification
    try:
        queue_cancellation(db, appt)
    except Exception as e:
        logger.error(f"Error queueing cancellation email: {str(e)}")

    # Delete Google Calendar events (non-blocking)
    try:
        delete_appointment_calendar_events(db, appt)
    except Exception as cal_err:
        logger.error(f"Failed to delete Google Calendar events: {str(cal_err)}")

    if appt.ai_suggested_questions and isinstance(appt.ai_suggested_questions, str):
        appt.ai_suggested_questions = json.loads(appt.ai_suggested_questions)

    return appt

@router.get("", response_model=list[AppointmentOut])
def list_appointments(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Lists appointments filtered by role.
    Patients view their bookings; Doctors view their schedule; Admins see all.
    """
    clean_expired_holds(db)
    
    if current_user.role == "patient":
        appts = db.query(Appointment).filter(Appointment.patient_id == current_user.id).order_by(Appointment.start_time.asc()).all()
    elif current_user.role == "doctor":
        appts = db.query(Appointment).filter(Appointment.doctor_id == current_user.id).order_by(Appointment.start_time.asc()).all()
    else:  # admin
        appts = db.query(Appointment).order_by(Appointment.start_time.asc()).all()

    for appt in appts:
        if appt.ai_suggested_questions and isinstance(appt.ai_suggested_questions, str):
            try:
                appt.ai_suggested_questions = json.loads(appt.ai_suggested_questions)
            except Exception:
                appt.ai_suggested_questions = []

    return appts
