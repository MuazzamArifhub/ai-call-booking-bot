"""Business owner dashboard API routes.

Endpoints for managing businesses, viewing appointments, and call logs.
In a real deployment, these would be protected by API key or JWT auth.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db
from .models import Appointment, AppointmentStatus, Business, CallLog

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class BusinessCreate(BaseModel):
    name: str
    phone_number: str
    timezone: str = "America/Regina"
    opening_hours: Optional[dict] = None
    services: Optional[list] = None
    booking_rules: Optional[dict] = None
    custom_greeting: Optional[str] = None


class BusinessOut(BaseModel):
    id: str
    name: str
    phone_number: str
    timezone: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AppointmentOut(BaseModel):
    id: str
    customer_name: str
    customer_phone: str
    service_name: str
    staff_name: Optional[str]
    start_time: datetime
    end_time: datetime
    status: str
    sms_confirmation_sent: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CallLogOut(BaseModel):
    id: str
    twilio_call_sid: Optional[str]
    from_number: str
    duration_seconds: Optional[int]
    intent: Optional[str]
    outcome: Optional[str]
    quality_score: Optional[float]
    summary: Optional[str]
    started_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Business endpoints
# ---------------------------------------------------------------------------

@router.post("/businesses", response_model=BusinessOut, status_code=201)
def create_business(payload: BusinessCreate, db: Session = Depends(get_db)):
    """Register a new business."""
    existing = db.query(Business).filter(
        Business.phone_number == payload.phone_number
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Phone number already registered")

    biz = Business(
        name=payload.name,
        phone_number=payload.phone_number,
        timezone=payload.timezone,
        opening_hours=payload.opening_hours or {
            "Mon": ["09:00", "17:00"],
            "Tue": ["09:00", "17:00"],
            "Wed": ["09:00", "17:00"],
            "Thu": ["09:00", "17:00"],
            "Fri": ["09:00", "17:00"],
            "Sat": ["10:00", "15:00"],
            "Sun": None,
        },
        services=payload.services or [
            {"name": "Haircut", "duration_min": 30, "price": 25},
            {"name": "Beard Trim", "duration_min": 20, "price": 15},
            {"name": "Haircut + Beard", "duration_min": 45, "price": 35},
        ],
        booking_rules=payload.booking_rules or {
            "slot_duration_min": 30,
            "buffer_between_min": 5,
            "max_advance_days": 30,
        },
        custom_greeting=payload.custom_greeting,
    )
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return biz


@router.get("/businesses", response_model=List[BusinessOut])
def list_businesses(db: Session = Depends(get_db)):
    return db.query(Business).filter(Business.is_active == True).all()


@router.get("/businesses/{business_id}", response_model=BusinessOut)
def get_business(business_id: str, db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")
    return biz


# ---------------------------------------------------------------------------
# Appointment endpoints
# ---------------------------------------------------------------------------

@router.get("/businesses/{business_id}/appointments", response_model=List[AppointmentOut])
def list_appointments(
    business_id: str,
    status: Optional[str] = Query(None),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Appointment).filter(Appointment.business_id == business_id)

    if status:
        query = query.filter(Appointment.status == status)
    if from_date:
        query = query.filter(Appointment.start_time >= from_date)
    if to_date:
        query = query.filter(Appointment.start_time <= to_date)
    else:
        # Default: show next 30 days
        query = query.filter(Appointment.start_time <= datetime.utcnow() + timedelta(days=30))

    return query.order_by(Appointment.start_time).all()


@router.patch("/businesses/{business_id}/appointments/{appointment_id}/cancel")
def cancel(
    business_id: str,
    appointment_id: str,
    db: Session = Depends(get_db),
):
    appt = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.business_id == business_id,
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    appt.status = AppointmentStatus.CANCELLED
    db.commit()
    return {"status": "cancelled"}


# ---------------------------------------------------------------------------
# Call log endpoints
# ---------------------------------------------------------------------------

@router.get("/businesses/{business_id}/calls", response_model=List[CallLogOut])
def list_calls(
    business_id: str,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    return (
        db.query(CallLog)
        .filter(CallLog.business_id == business_id)
        .order_by(CallLog.started_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/businesses/{business_id}/calls/{call_id}", response_model=CallLogOut)
def get_call(
    business_id: str,
    call_id: str,
    db: Session = Depends(get_db),
):
    call = db.query(CallLog).filter(
        CallLog.id == call_id,
        CallLog.business_id == business_id,
    ).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call log not found")
    return call


# ---------------------------------------------------------------------------
# Analytics summary
# ---------------------------------------------------------------------------

@router.get("/businesses/{business_id}/analytics")
def analytics(business_id: str, db: Session = Depends(get_db)):
    """Simple analytics summary for the business dashboard."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    total_calls = db.query(CallLog).filter(
        CallLog.business_id == business_id,
        CallLog.started_at >= week_ago,
    ).count()

    total_bookings = db.query(Appointment).filter(
        Appointment.business_id == business_id,
        Appointment.created_at >= week_ago,
        Appointment.status == AppointmentStatus.CONFIRMED,
    ).count()

    upcoming = db.query(Appointment).filter(
        Appointment.business_id == business_id,
        Appointment.start_time >= now,
        Appointment.status == AppointmentStatus.CONFIRMED,
    ).count()

    return {
        "period": "last_7_days",
        "total_calls": total_calls,
        "bookings_created": total_bookings,
        "upcoming_appointments": upcoming,
    }
