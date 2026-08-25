import logging
import datetime
from sqlalchemy.orm import Session
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from backend.app.database import settings
from backend.app.models import Notification

logger = logging.getLogger(__name__)

def send_email_direct(to_email: str, subject: str, html_content: str) -> bool:
    """
    Sends an email directly using SendGrid API.
    If SENDGRID_API_KEY is not configured, logs it as fallback.
    """
    if not settings.SENDGRID_API_KEY:
        logger.info(f"[DEV FALLBACK EMAIL] Sending to {to_email}\nSubject: {subject}\nBody:\n{html_content}\n")
        return True

    try:
        message = Mail(
            from_email=settings.FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        if response.status_code in [200, 201, 202]:
            return True
        logger.error(f"SendGrid returned unexpected status code: {response.status_code}")
        return False
    except Exception as e:
        logger.error(f"SendGrid exception sending email: {str(e)}")
        return False

def queue_notification(
    db: Session,
    appointment_id: int | None,
    recipient_email: str,
    notification_type: str,
    subject: str,
    body: str,
    next_retry_at: datetime.datetime | None = None
) -> Notification:
    """
    Safely creates a PENDING notification in the database.
    Does NOT invoke third-party services directly, ensuring transactional safety.
    """
    notification = Notification(
        appointment_id=appointment_id,
        recipient_email=recipient_email,
        type=notification_type,
        subject=subject,
        body=body,
        status="PENDING",
        retry_count=0,
        next_retry_at=next_retry_at or datetime.datetime.now(datetime.timezone.utc),
        created_at=datetime.datetime.now(datetime.timezone.utc)
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification

def queue_booking_confirmation(db: Session, appointment) -> None:
    patient_email = appointment.patient.email
    subject = "Appointment Booking Confirmation"
    body = f"""
    <h2>Your Appointment is Confirmed!</h2>
    <p>Dear {appointment.patient.first_name},</p>
    <p>Your appointment with Dr. {appointment.doctor.user.last_name} has been confirmed.</p>
    <p><strong>Date & Time:</strong> {appointment.start_time.strftime('%Y-%m-%d %H:%M %Z')}</p>
    """
    queue_notification(db, appointment.id, patient_email, "booking_confirmation", subject, body)

def queue_cancellation(db: Session, appointment) -> None:
    patient_email = appointment.patient.email
    subject = "Appointment Cancellation Notification"
    body = f"""
    <h2>Appointment Cancelled</h2>
    <p>Dear {appointment.patient.first_name},</p>
    <p>Your appointment with Dr. {appointment.doctor.user.last_name} scheduled for {appointment.start_time.strftime('%Y-%m-%d %H:%M %Z')} has been cancelled.</p>
    """
    queue_notification(db, appointment.id, patient_email, "cancellation", subject, body)

def queue_leave_cancellation(db: Session, appointment) -> None:
    patient_email = appointment.patient.email
    subject = "Urgent: Doctor Leave - Appointment Cancelled"
    body = f"""
    <h2>Appointment Cancelled Due to Doctor Leave</h2>
    <p>Dear {appointment.patient.first_name},</p>
    <p>We regret to inform you that your appointment with Dr. {appointment.doctor.user.last_name} scheduled for {appointment.start_time.strftime('%Y-%m-%d %H:%M %Z')} has been cancelled because the doctor is on leave that day.</p>
    <p>Please log in to reschedule your appointment at your convenience.</p>
    """
    queue_notification(db, appointment.id, patient_email, "leave_cancellation", subject, body)
