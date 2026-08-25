import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models import User, Appointment, Medication
from backend.app.schemas import ClinicalNotesInput, AppointmentOut
from backend.app.auth.security import RoleChecker
from backend.app.services.gemini_service import generate_post_visit_summary
from backend.app.services.medication_scheduler import schedule_medication_reminders

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clinical", tags=["Clinical Operations"])

# Access allowed for doctors only
doctor_only = RoleChecker(["doctor"])

@router.post("/appointments/{appointment_id}/complete", response_model=AppointmentOut)
def complete_appointment(
    appointment_id: int, 
    notes_in: ClinicalNotesInput, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(doctor_only)
):
    """
    Submits clinical notes, prescriptions, and schedules medications for an appointment.
    Marks the appointment COMPLETED. Triggers Gemini AI post-visit summaries.
    """
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    if appt.doctor_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not the assigned doctor for this appointment")
        
    if appt.status != "CONFIRMED":
        raise HTTPException(status_code=400, detail=f"Cannot complete appointment in state {appt.status}")

    # 1. Trigger Gemini post-visit summary (wrapped in try/except)
    ai_summary = None
    try:
        ai_summary = generate_post_visit_summary(notes_in.clinical_notes, notes_in.prescription)
    except Exception as ex:
        logger.error(f"Failed to generate AI post-visit summary: {str(ex)}")

    # 2. Update appointment info
    appt.status = "COMPLETED"
    appt.clinical_notes = notes_in.clinical_notes
    appt.prescription = notes_in.prescription
    
    if ai_summary:
        appt.ai_patient_summary = ai_summary.get("patient_summary")
        appt.ai_medication_schedule = ai_summary.get("medication_schedule")
        appt.ai_follow_up_steps = ai_summary.get("follow_up_steps")
    else:
        # Fallback values
        appt.ai_patient_summary = f"Clinical notes:\n{notes_in.clinical_notes}\n\nPrescription:\n{notes_in.prescription}"
        appt.ai_medication_schedule = "Please follow the prescription as written by your doctor."
        appt.ai_follow_up_steps = "Follow up as advised by your healthcare provider."

    db.flush()

    # 3. Add Medications and schedule reminders
    patient_email = appt.patient.email
    if notes_in.medications:
        for med_in in notes_in.medications:
            reminder_times_str = json.dumps(med_in.reminder_times) if med_in.reminder_times else None
            
            medication_record = Medication(
                appointment_id=appt.id,
                name=med_in.name,
                dosage=med_in.dosage,
                frequency=med_in.frequency,
                reminder_times=reminder_times_str,
                start_date=med_in.start_date,
                end_date=med_in.end_date
            )
            db.add(medication_record)
            db.flush()  # Generate primary key ID
            
            # Pre-schedule reminders using medication_scheduler helper
            try:
                schedule_medication_reminders(db, medication_record, patient_email)
            except Exception as sched_err:
                logger.error(f"Failed to schedule reminders for medication {med_in.name}: {str(sched_err)}")

    db.commit()
    db.refresh(appt)

    # Decode JSON fields for schema compatibility
    if appt.ai_suggested_questions and isinstance(appt.ai_suggested_questions, str):
        appt.ai_suggested_questions = json.loads(appt.ai_suggested_questions)

    return appt
