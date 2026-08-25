import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Date, Text, Index, UniqueConstraint, event, DDL, func, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from backend.app.database import Base

# Setup PostgreSQL extension btree_gist
create_extension = DDL("CREATE EXTENSION IF NOT EXISTS btree_gist")
event.listen(
    Base.metadata,
    "before_create",
    create_extension.execute_if(dialect="postgresql")
)

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # patient, doctor, admin
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    doctor_profile = relationship("Doctor", back_populates="user", uselist=False)
    patient_appointments = relationship("Appointment", foreign_keys="[Appointment.patient_id]", back_populates="patient")
    google_token = relationship("GoogleToken", back_populates="user", uselist=False)

# Case-insensitive unique index on email
# Note: For SQLite, unique=True on column email handles simple cases, but index on func.lower(email) enforces it case-insensitively
Index("idx_users_email_lower", func.lower(User.email), unique=True)


class Doctor(Base):
    __tablename__ = "doctors"
    
    id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    specialization = Column(String, nullable=False)
    # working_hours stored as JSON, e.g. {"monday": [{"start": "09:00", "end": "17:00"}], ...}
    working_hours = Column(Text, nullable=False, default="{}")  # Stringified JSON
    slot_duration_minutes = Column(Integer, nullable=False, default=30)

    # Relationships
    user = relationship("User", back_populates="doctor_profile")
    leaves = relationship("DoctorLeave", back_populates="doctor", cascade="all, delete-orphan")
    appointments = relationship("Appointment", foreign_keys="[Appointment.doctor_id]", back_populates="doctor")


class DoctorLeave(Base):
    __tablename__ = "doctor_leaves"
    
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    leave_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    doctor = relationship("Doctor", back_populates="leaves")

    # Uniqueness constraint: a doctor cannot have more than one leave on the same date
    __table_args__ = (
        UniqueConstraint("doctor_id", "leave_date", name="uq_doctor_leave_date"),
    )


class GoogleToken(Base):
    __tablename__ = "google_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    user = relationship("User", back_populates="google_token")


class Appointment(Base):
    __tablename__ = "appointments"
    
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, nullable=False)  # HELD, CONFIRMED, COMPLETED, CANCELLED, EXPIRED
    hold_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Pre-visit symptoms and AI analyses
    symptoms = Column(Text, nullable=True)
    ai_urgency_level = Column(String, nullable=True)
    ai_chief_complaint = Column(Text, nullable=True)
    ai_suggested_questions = Column(Text, nullable=True)  # JSON string list
    
    # Post-visit and Prescriptions
    clinical_notes = Column(Text, nullable=True)
    prescription = Column(Text, nullable=True)
    ai_patient_summary = Column(Text, nullable=True)
    ai_medication_schedule = Column(Text, nullable=True)
    ai_follow_up_steps = Column(Text, nullable=True)
    
    # Google Calendar event mappings
    google_event_patient_id = Column(String, nullable=True)
    google_event_doctor_id = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    patient = relationship("User", foreign_keys=[patient_id], back_populates="patient_appointments")
    doctor = relationship("Doctor", foreign_keys=[doctor_id], back_populates="appointments")
    medications = relationship("Medication", back_populates="appointment", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="appointment", cascade="all, delete-orphan")

    # Table arguments: Add partial unique index for SQLite slot concurrency
    __table_args__ = (
        Index(
            "idx_doctor_active_slot",
            doctor_id,
            start_time,
            unique=True,
            postgresql_where=text("status IN ('HELD', 'CONFIRMED', 'COMPLETED')"),
            sqlite_where=text("status IN ('HELD', 'CONFIRMED', 'COMPLETED')")
        ),
    )

# Dynamically attach PostgreSQL ExcludeConstraint when running on PostgreSQL dialect
from sqlalchemy.dialects.postgresql import ExcludeConstraint

@event.listens_for(Appointment.__table__, "before_create")
def add_pg_exclusion_constraint(target, connection, **kw):
    if connection.dialect.name == "postgresql":
        for const in target.constraints:
            if getattr(const, "name", None) == "prevent_doctor_double_booking":
                return
        target.append_constraint(
            ExcludeConstraint(
                ("doctor_id", "="),
                (func.tsrange(target.c.start_time, target.c.end_time, '[)'), "&&"),
                name="prevent_doctor_double_booking",
                where=text("status IN ('HELD', 'CONFIRMED', 'COMPLETED')")
            )
        )


class Medication(Base):
    __tablename__ = "medications"
    
    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    dosage = Column(String, nullable=False)
    frequency = Column(String, nullable=False)  # once daily, twice daily, every 8 hours, etc.
    reminder_times = Column(Text, nullable=True)  # JSON string list of "HH:MM", e.g., ["08:00", "20:00"]
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    # Relationships
    appointment = relationship("Appointment", back_populates="medications")


class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True)
    recipient_email = Column(String, nullable=False)
    type = Column(String, nullable=False)  # booking_confirmation, reminder, cancellation, leave_cancellation, medication_reminder
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="PENDING")  # PENDING, SENT, FAILED
    retry_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    appointment = relationship("Appointment", back_populates="notifications")
