import asyncio
import datetime
import logging
from sqlalchemy.orm import Session
from backend.app.database import SessionLocal
from backend.app.models import Notification
from backend.app.services.email_service import send_email_direct

logger = logging.getLogger(__name__)

# Max retry count for failed notifications
MAX_RETRIES = 5

async def start_notification_worker():
    """
    Starts the background worker loop that processes pending notifications.
    This should be started as a background task on FastAPI startup.
    """
    logger.info("Starting background notification worker loop...")
    while True:
        try:
            await process_pending_notifications()
        except Exception as e:
            logger.error(f"Error in background notification worker: {str(e)}")
        
        # Sleep for 10 seconds before next poll
        await asyncio.sleep(10)

async def process_pending_notifications(db: Session | None = None):
    """
    Queries and processes PENDING notifications.
    """
    close_db_session = False
    if db is None:
        db = SessionLocal()
        close_db_session = True
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Fetch notifications that are PENDING and scheduled to run (next_retry_at <= now)
        pending = db.query(Notification).filter(
            Notification.status == "PENDING",
            Notification.next_retry_at <= now
        ).all()
        
        if not pending:
            return

        logger.info(f"Notification worker picked up {len(pending)} pending jobs.")

        for notification in pending:
            # Attempt to send email
            success = send_email_direct(
                to_email=notification.recipient_email,
                subject=notification.subject,
                html_content=notification.body
            )
            
            if success:
                notification.status = "SENT"
                notification.last_error = None
            else:
                notification.retry_count += 1
                if notification.retry_count >= MAX_RETRIES:
                    notification.status = "FAILED"
                    logger.error(f"Notification {notification.id} permanently failed after {MAX_RETRIES} attempts.")
                else:
                    # Exponential backoff: 2 ^ retry_count * 60 seconds
                    backoff_seconds = (2 ** notification.retry_count) * 60
                    notification.next_retry_at = now + datetime.timedelta(seconds=backoff_seconds)
                    logger.warning(f"Notification {notification.id} failed. Scheduling retry {notification.retry_count} at {notification.next_retry_at}")
                
                notification.last_error = "SendGrid API call failed (see logs for detail)"
                
            db.commit()
            
    finally:
        if close_db_session:
            db.close()
