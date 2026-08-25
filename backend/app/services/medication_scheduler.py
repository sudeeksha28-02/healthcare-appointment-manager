import datetime
import json
import logging
from sqlalchemy.orm import Session
from backend.app.models import Medication, Notification

logger = logging.getLogger(__name__)

def schedule_medication_reminders(db: Session, medication: Medication, patient_email: str) -> None:
    """
    Schedules medication reminders in the notifications table based on explicit reminder_times.
    If reminder_times is empty or null, does not schedule any notifications.
    """
    if not medication.reminder_times:
        logger.info(f"Medication {medication.name} has no reminder times configured. Skipping scheduling.")
        return

    try:
        # reminder_times should be parsed if it's a string representation of a JSON list
        times = json.loads(medication.reminder_times) if isinstance(medication.reminder_times, str) else medication.reminder_times
        if not isinstance(times, list) or len(times) == 0:
            logger.info(f"Medication {medication.name} has empty reminder times. Skipping scheduling.")
            return
    except Exception as e:
        logger.error(f"Failed to parse reminder times for medication {medication.id}: {str(e)}")
        return

    current_date = medication.start_date
    end_date = medication.end_date
    delta = datetime.timedelta(days=1)

    while current_date <= end_date:
        for t_str in times:
            try:
                # Parse HH:MM
                hour_str, min_str = t_str.split(":")
                hour = int(hour_str)
                minute = int(min_str)
                
                # Combine into a timezone-aware datetime (standard UTC)
                reminder_time = datetime.datetime.combine(
                    current_date, 
                    datetime.time(hour=hour, minute=minute)
                ).replace(tzinfo=datetime.timezone.utc)
                
                # Verify that we don't schedule reminders in the past relative to creation
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                if reminder_time < now_utc:
                    continue

                subject = f"Medication Reminder: {medication.name}"
                body = (
                    f"Reminder to take your medication:\n"
                    f"Name: {medication.name}\n"
                    f"Dosage: {medication.dosage}\n"
                    f"Frequency: {medication.frequency}\n"
                    f"Scheduled Time: {t_str} UTC"
                )

                notification = Notification(
                    appointment_id=medication.appointment_id,
                    recipient_email=patient_email,
                    type="medication_reminder",
                    subject=subject,
                    body=body,
                    status="PENDING",
                    retry_count=0,
                    next_retry_at=reminder_time,
                    created_at=now_utc
                )
                db.add(notification)
            except Exception as e:
                logger.error(f"Error scheduling medication reminder for {medication.name} at {t_str}: {str(e)}")
        
        current_date += delta

    db.commit()
