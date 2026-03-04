"""SQLAlchemy ORM models for all database tables."""
import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, String, Boolean, DateTime, Float, Integer,
    Text, ForeignKey, JSON, Enum
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AppointmentStatus(str, PyEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class CallIntent(str, PyEnum):
    BOOKING = "booking"
    RESCHEDULE = "reschedule"
    CANCELLATION = "cancellation"
    FAQ = "faq"
    ESCALATION = "escalation"  # transferred to human
    UNKNOWN = "unknown"


class CallOutcome(str, PyEnum):
    SUCCESS = "success"          # intent fulfilled
    PARTIAL = "partial"          # some steps completed
    ESCALATED = "escalated"      # handed off to human
    FAILED = "failed"            # bot could not help


# ---------------------------------------------------------------------------
# Business  (multi-tenant root)
# ---------------------------------------------------------------------------

class Business(Base):
    __tablename__ = "businesses"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    phone_number = Column(String(20), unique=True, nullable=False)  # E.164
    timezone = Column(String(50), default="America/Regina")
    # JSON blob: {"Mon": ["09:00", "17:00"], ...}  null = closed
    opening_hours = Column(JSON, nullable=True)
    # JSON list of service objects: [{"name": "Haircut", "duration_min": 30, "price": 25}]
    services = Column(JSON, default=list)
    # Extra rules: slot_duration_min, buffer_between_min, max_advance_days, etc.
    booking_rules = Column(JSON, default=dict)
    # Short system-prompt snippet injected into every call for this business
    custom_greeting = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    appointments = relationship("Appointment", back_populates="business", cascade="all, delete-orphan")
    call_logs = relationship("CallLog", back_populates="business", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Business {self.name}>"


# ---------------------------------------------------------------------------
# Appointment
# ---------------------------------------------------------------------------

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(String, primary_key=True, default=_uuid)
    business_id = Column(String, ForeignKey("businesses.id"), nullable=False)

    # Customer info
    customer_name = Column(String(200), nullable=False)
    customer_phone = Column(String(20), nullable=False)  # E.164

    # Booking details
    service_name = Column(String(200), nullable=False)
    staff_name = Column(String(200), nullable=True)  # optional barber preference
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)

    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.CONFIRMED)
    notes = Column(Text, nullable=True)

    # Link back to the call that created this booking
    call_log_id = Column(String, ForeignKey("call_logs.id"), nullable=True)

    # Tracking
    sms_confirmation_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business = relationship("Business", back_populates="appointments")
    call_log = relationship("CallLog", back_populates="appointment", foreign_keys=[call_log_id])

    def __repr__(self):
        return f"<Appointment {self.customer_name} @ {self.start_time}>"


# ---------------------------------------------------------------------------
# CallLog  (one row per inbound call)
# ---------------------------------------------------------------------------

class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(String, primary_key=True, default=_uuid)
    business_id = Column(String, ForeignKey("businesses.id"), nullable=False)

    # Twilio fields
    twilio_call_sid = Column(String(64), unique=True, nullable=True)
    from_number = Column(String(20), nullable=False)   # caller
    to_number = Column(String(20), nullable=False)     # business line
    recording_url = Column(String(500), nullable=True)

    # Timing
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # Content
    transcript = Column(Text, nullable=True)        # raw ASR output
    transcript_clean = Column(Text, nullable=True)  # PII-scrubbed version
    summary = Column(Text, nullable=True)           # 1-2 sentence LLM summary

    # Classification
    intent = Column(Enum(CallIntent), default=CallIntent.UNKNOWN)
    outcome = Column(Enum(CallOutcome), nullable=True)
    # Quality score 0-1 used by training pipeline filter
    quality_score = Column(Float, nullable=True)

    # Consent
    training_consent = Column(Boolean, default=True)  # caller opted in

    # Relationship to appointment (if booking happened)
    appointment = relationship(
        "Appointment",
        back_populates="call_log",
        foreign_keys="Appointment.call_log_id",
        uselist=False,
    )
    business = relationship("Business", back_populates="call_logs")
    training_samples = relationship("TrainingSample", back_populates="call_log", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CallLog {self.twilio_call_sid} intent={self.intent}>"


# ---------------------------------------------------------------------------
# TrainingSample  (derived from CallLog, used for fine-tuning / RAG)
# ---------------------------------------------------------------------------

class TrainingSample(Base):
    __tablename__ = "training_samples"

    id = Column(String, primary_key=True, default=_uuid)
    call_log_id = Column(String, ForeignKey("call_logs.id"), nullable=False)

    # OpenAI fine-tune format: system / user / assistant messages as JSON
    messages = Column(JSON, nullable=False)  # list of {role, content} dicts

    # Metadata
    tags = Column(JSON, default=list)     # e.g. ["booking", "barber", "faq"]
    quality_score = Column(Float, nullable=True)
    reviewed = Column(Boolean, default=False)  # manually reviewed flag

    created_at = Column(DateTime, default=datetime.utcnow)

    call_log = relationship("CallLog", back_populates="training_samples")

    def __repr__(self):
        return f"<TrainingSample call={self.call_log_id} tags={self.tags}>"
