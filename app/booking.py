"""Appointment CRUD and availability logic."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from .models import Appointment, AppointmentStatus, Business


# ---------------------------------------------------------------------------
# Availability helpers
# ---------------------------------------------------------------------------

def get_available_slots(
    db: Session,
    business: Business,
    date: datetime,
    service_name: str,
    count: int = 5,
) -> List[datetime]:
    """
    Return up to `count` available start times for `service_name` on `date`.

    Strategy:
    1. Determine opening window from business.opening_hours.
    2. Determine slot duration from business.services.
    3. Walk the day in slot increments.
    4. Skip slots that overlap an existing CONFIRMED appointment.
    """
    day_name = date.strftime("%a")  # e.g. "Mon"
    hours = (business.opening_hours or {}).get(day_name)
    if not hours:
        return []  # closed

    open_h, open_m = map(int, hours[0].split(":"))
    close_h, close_m = map(int, hours[1].split(":"))

    rules = business.booking_rules or {}
    slot_duration = _service_duration(business, service_name)
    buffer = rules.get("buffer_between_min", 0)
    step = slot_duration + buffer

    window_start = date.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
    window_end = date.replace(hour=close_h, minute=close_m, second=0, microsecond=0)

    # Fetch booked slots for the day
    booked = db.query(Appointment).filter(
        Appointment.business_id == business.id,
        Appointment.start_time >= window_start,
        Appointment.start_time < window_end,
        Appointment.status.in_([
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.PENDING,
        ]),
    ).all()

    booked_ranges = [(a.start_time, a.end_time) for a in booked]

    slots: List[datetime] = []
    cursor = window_start

    while cursor + timedelta(minutes=slot_duration) <= window_end:
        slot_end = cursor + timedelta(minutes=slot_duration)
        if not _overlaps(cursor, slot_end, booked_ranges):
            slots.append(cursor)
            if len(slots) >= count:
                break
        cursor += timedelta(minutes=step)

    return slots


def _service_duration(business: Business, service_name: str) -> int:
    """Look up duration in minutes for a service; default 30."""
    for svc in (business.services or []):
        if svc.get("name", "").lower() == service_name.lower():
            return int(svc.get("duration_min", 30))
    return (business.booking_rules or {}).get("slot_duration_min", 30)


def _overlaps(
    start: datetime,
    end: datetime,
    booked_ranges: List[tuple],
) -> bool:
    for b_start, b_end in booked_ranges:
        if start < b_end and end > b_start:
            return True
    return False


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_appointment(
    db: Session,
    business_id: str,
    customer_name: str,
    customer_phone: str,
    service_name: str,
    start_time: datetime,
    staff_name: Optional[str] = None,
    call_log_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> Appointment:
    """Create and persist a new appointment."""
    business = db.get(Business, business_id)
    if not business:
        raise ValueError(f"Business {business_id} not found")

    duration = _service_duration(business, service_name)
    end_time = start_time + timedelta(minutes=duration)

    appt = Appointment(
        business_id=business_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        service_name=service_name,
        staff_name=staff_name,
        start_time=start_time,
        end_time=end_time,
        call_log_id=call_log_id,
        notes=notes,
        status=AppointmentStatus.CONFIRMED,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt


def cancel_appointment(
    db: Session,
    appointment_id: str,
    business_id: str,
) -> Optional[Appointment]:
    """Cancel an appointment by ID."""
    appt = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.business_id == business_id,
    ).first()
    if not appt:
        return None
    appt.status = AppointmentStatus.CANCELLED
    db.commit()
    db.refresh(appt)
    return appt


def find_appointment_by_phone(
    db: Session,
    business_id: str,
    customer_phone: str,
) -> List[Appointment]:
    """Find upcoming confirmed appointments for a caller."""
    return db.query(Appointment).filter(
        Appointment.business_id == business_id,
        Appointment.customer_phone == customer_phone,
        Appointment.status == AppointmentStatus.CONFIRMED,
        Appointment.start_time >= datetime.utcnow(),
    ).order_by(Appointment.start_time).all()


def reschedule_appointment(
    db: Session,
    appointment_id: str,
    business_id: str,
    new_start_time: datetime,
) -> Optional[Appointment]:
    """Reschedule an existing appointment."""
    appt = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.business_id == business_id,
    ).first()
    if not appt:
        return None

    business = db.get(Business, business_id)
    duration = _service_duration(business, appt.service_name)
    appt.start_time = new_start_time
    appt.end_time = new_start_time + timedelta(minutes=duration)
    db.commit()
    db.refresh(appt)
    return appt
