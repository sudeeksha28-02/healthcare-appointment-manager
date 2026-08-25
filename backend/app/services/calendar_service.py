import datetime
import logging
import base64
import hashlib
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from backend.app.database import settings
from backend.app.models import GoogleToken, Appointment

logger = logging.getLogger(__name__)

# Initialize Fernet cipher suite safely
try:
    key_bytes = settings.ENCRYPTION_KEY.encode()
    # Fernet requires a 32-byte key, url-safe base64 encoded
    fernet_key = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
    cipher_suite = Fernet(fernet_key)
except Exception as e:
    logger.error(f"Failed to initialize Fernet cipher: {str(e)}")
    cipher_suite = None

def encrypt_token(token: str) -> str:
    if not token or not cipher_suite:
        return token
    return cipher_suite.encrypt(token.encode()).decode()

def decrypt_token(token: str) -> str:
    if not token or not cipher_suite:
        return token
    return cipher_suite.decrypt(token.encode()).decode()

def get_user_credentials(db: Session, user_id: int) -> Credentials | None:
    """
    Retrieves and decrypts Google OAuth credentials for a user.
    Refreshes the token if it has expired.
    """
    token_rec = db.query(GoogleToken).filter(GoogleToken.user_id == user_id).first()
    if not token_rec:
        return None

    try:
        access_token = decrypt_token(token_rec.access_token)
        refresh_token = decrypt_token(token_rec.refresh_token) if token_rec.refresh_token else None
        
        # Build google credentials object
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            expiry=token_rec.expires_at.replace(tzinfo=None) if token_rec.expires_at else None
        )
        
        # Check expiry and refresh if refresh token is present
        if creds.expired and creds.refresh_token:
            logger.info(f"Refreshing Google OAuth token for user {user_id}")
            creds.refresh(Request())
            
            # Save updated credentials back to database
            token_rec.access_token = encrypt_token(creds.token)
            token_rec.expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=creds.expiry.timestamp() - datetime.datetime.utcnow().timestamp())
            db.commit()
            
        return creds
    except Exception as e:
        logger.error(f"Error loading/refreshing credentials for user {user_id}: {str(e)}")
        return None

def create_event_for_user(db: Session, user_id: int, appointment: Appointment, attendee_email: str, is_doctor: bool) -> str | None:
    """
    Helper to call real Google Calendar API and insert an event.
    """
    creds = get_user_credentials(db, user_id)
    if not creds:
        logger.info(f"User {user_id} has not linked Google Calendar. Skipping calendar event creation.")
        return None

    try:
        service = build("calendar", "v3", credentials=creds)
        
        role_label = "Doctor" if is_doctor else "Patient"
        summary = f"Medical Appointment: Dr. {appointment.doctor.user.last_name} / {appointment.patient.first_name}"
        description = f"Healthcare Appointment\nChief Complaint: {appointment.ai_chief_complaint or 'Symptom Consultation'}"
        
        event_body = {
            "summary": summary,
            "description": description,
            "start": {
                "dateTime": appointment.start_time.isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": appointment.end_time.isoformat(),
                "timeZone": "UTC",
            },
            "attendees": [
                {"email": attendee_email}
            ]
        }
        
        created_event = service.events().insert(calendarId="primary", body=event_body).execute()
        return created_event.get("id")
    except Exception as e:
        logger.error(f"Google Calendar API failed to create event for user {user_id}: {str(e)}")
        return None

def update_event_for_user(db: Session, user_id: int, event_id: str, appointment: Appointment, attendee_email: str) -> bool:
    creds = get_user_credentials(db, user_id)
    if not creds or not event_id:
        return False

    try:
        service = build("calendar", "v3", credentials=creds)
        summary = f"Rescheduled Appointment: Dr. {appointment.doctor.user.last_name} / {appointment.patient.first_name}"
        
        event_body = service.events().get(calendarId="primary", eventId=event_id).execute()
        event_body["summary"] = summary
        event_body["start"] = {
            "dateTime": appointment.start_time.isoformat(),
            "timeZone": "UTC",
        }
        event_body["end"] = {
            "dateTime": appointment.end_time.isoformat(),
            "timeZone": "UTC",
        }
        
        service.events().update(calendarId="primary", eventId=event_id, body=event_body).execute()
        return True
    except Exception as e:
        logger.error(f"Google Calendar API failed to update event {event_id} for user {user_id}: {str(e)}")
        return False

def delete_event_for_user(db: Session, user_id: int, event_id: str) -> bool:
    creds = get_user_credentials(db, user_id)
    if not creds or not event_id:
        return False

    try:
        service = build("calendar", "v3", credentials=creds)
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return True
    except Exception as e:
        logger.error(f"Google Calendar API failed to delete event {event_id} for user {user_id}: {str(e)}")
        return False

# Public interface functions
def create_appointment_calendar_events(db: Session, appointment: Appointment) -> None:
    # 1. Create event in patient's calendar (if authenticated)
    patient_event_id = create_event_for_user(
        db, 
        appointment.patient_id, 
        appointment, 
        appointment.doctor.user.email, 
        is_doctor=False
    )
    if patient_event_id:
        appointment.google_event_patient_id = patient_event_id

    # 2. Create event in doctor's calendar (if authenticated)
    doctor_event_id = create_event_for_user(
        db, 
        appointment.doctor_id, 
        appointment, 
        appointment.patient.email, 
        is_doctor=True
    )
    if doctor_event_id:
        appointment.google_event_doctor_id = doctor_event_id

    db.commit()

def update_appointment_calendar_events(db: Session, appointment: Appointment) -> None:
    if appointment.google_event_patient_id:
        update_event_for_user(
            db, 
            appointment.patient_id, 
            appointment.google_event_patient_id, 
            appointment, 
            appointment.doctor.user.email
        )
    if appointment.google_event_doctor_id:
        update_event_for_user(
            db, 
            appointment.doctor_id, 
            appointment.google_event_doctor_id, 
            appointment, 
            appointment.patient.email
        )

def delete_appointment_calendar_events(db: Session, appointment: Appointment) -> None:
    if appointment.google_event_patient_id:
        delete_event_for_user(db, appointment.patient_id, appointment.google_event_patient_id)
        appointment.google_event_patient_id = None
    if appointment.google_event_doctor_id:
        delete_event_for_user(db, appointment.doctor_id, appointment.google_event_doctor_id)
        appointment.google_event_doctor_id = None
    db.commit()
