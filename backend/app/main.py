import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.database import engine, Base, SessionLocal
from backend.app.models import User
from backend.app.auth.security import get_password_hash
from backend.app.routes import auth, admin, appointments, clinical, google_oauth
from backend.app.services.notification_worker import start_notification_worker

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Healthcare Appointment & Follow-up Manager API",
    description="A secure transactional API supporting holds, double-booking prevention, leaves, and integrations.",
    version="1.0.0"
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(appointments.router, prefix="/api")
app.include_router(clinical.router, prefix="/api")
app.include_router(google_oauth.router, prefix="/api")

def seed_default_admin():
    db = SessionLocal()
    try:
        admin_email = "admin@healthcare.com"
        existing = db.query(User).filter(User.email == admin_email).first()
        if not existing:
            logger.info("Seeding default admin user: admin@healthcare.com")
            hashed_pw = get_password_hash("adminpassword123")
            admin_user = User(
                email=admin_email,
                password_hash=hashed_pw,
                role="admin",
                first_name="System",
                last_name="Admin"
            )
            db.add(admin_user)
            db.commit()
    except Exception as e:
        logger.error(f"Error seeding default admin: {str(e)}")
        db.rollback()
    finally:
        db.close()

@app.on_event("startup")
def on_startup():
    # 1. Ensure all database tables exist
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=engine)
    
    # 2. Seed default admin account
    seed_default_admin()
    
    # 3. Spawn background notification retry worker task if not testing
    import os
    if os.environ.get("TESTING") != "1":
        asyncio.create_task(start_notification_worker())

@app.get("/")
def read_root():
    return {"message": "Healthcare Appointment & Follow-up Manager API is running"}
