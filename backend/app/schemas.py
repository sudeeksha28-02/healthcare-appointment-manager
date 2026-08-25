from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List, Optional
from datetime import datetime, date
import re

# Base User schemas
class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    email: str
    password: str

class UserOut(UserBase):
    id: int
    role: str
    created_at: datetime

    class Config:
        from_attributes = True

# Token schemas
class Token(BaseModel):
    access_token: str
    token_type: str
    role: str

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None

# Doctor schemas
class DoctorCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    first_name: str
    last_name: str
    specialization: str
    working_hours: str = "{}"  # Stringified JSON
    slot_duration_minutes: int = 30

class DoctorUpdate(BaseModel):
    specialization: Optional[str] = None
    working_hours: Optional[str] = None
    slot_duration_minutes: Optional[int] = None

class DoctorOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    specialization: str
    working_hours: str
    slot_duration_minutes: int

    class Config:
        from_attributes = True

# DoctorLeave schemas
class DoctorLeaveCreate(BaseModel):
    doctor_id: int
    leave_date: date

class DoctorLeaveOut(BaseModel):
    id: int
    doctor_id: int
    leave_date: date
    created_at: datetime

    class Config:
        from_attributes = True

# Medication schemas
class MedicationCreate(BaseModel):
    name: str
    dosage: str
    frequency: str  # once daily, twice daily, three times daily, every 4 hours, etc.
    reminder_times: Optional[List[str]] = None  # ["08:00", "20:00"]
    start_date: date
    end_date: date

    @field_validator("reminder_times")
    @classmethod
    def validate_times(cls, v):
        if v is not None:
            for t in v:
                if not re.match(r"^\d{2}:\d{2}$", t):
                    raise ValueError("Time must be in HH:MM format")
        return v

class MedicationOut(BaseModel):
    id: int
    appointment_id: int
    name: str
    dosage: str
    frequency: str
    reminder_times: Optional[List[str]] = None
    start_date: date
    end_date: date

    @field_validator("reminder_times", mode="before")
    @classmethod
    def parse_reminder_times(cls, v):
        if isinstance(v, str):
            try:
                import json
                return json.loads(v)
            except Exception:
                return []
        return v

    class Config:
        from_attributes = True

# Appointment schemas
class AppointmentHoldRequest(BaseModel):
    doctor_id: int
    start_time: datetime  # Timezone-aware
    end_time: datetime    # Timezone-aware

class AppointmentConfirmRequest(BaseModel):
    symptoms: str

class AppointmentRescheduleRequest(BaseModel):
    start_time: datetime
    end_time: datetime

class ClinicalNotesInput(BaseModel):
    clinical_notes: str
    prescription: str
    medications: Optional[List[MedicationCreate]] = None

class AppointmentOut(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    start_time: datetime
    end_time: datetime
    status: str
    hold_expires_at: Optional[datetime] = None
    symptoms: Optional[str] = None
    ai_urgency_level: Optional[str] = None
    ai_chief_complaint: Optional[str] = None
    ai_suggested_questions: Optional[List[str]] = None
    clinical_notes: Optional[str] = None
    prescription: Optional[str] = None
    ai_patient_summary: Optional[str] = None
    ai_medication_schedule: Optional[str] = None
    ai_follow_up_steps: Optional[str] = None
    google_event_patient_id: Optional[str] = None
    google_event_doctor_id: Optional[str] = None
    created_at: datetime
    
    # Nested Medication info
    medications: List[MedicationOut] = []

    class Config:
        from_attributes = True
