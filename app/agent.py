"""LLM conversation agent for handling phone calls.

The agent uses OpenAI function-calling to decide when to:
  - check_availability  -> query DB for open slots
  - create_appointment  -> write a booking
  - cancel_appointment  -> cancel an existing booking
  - find_appointments   -> look up caller's upcoming appointments
  - escalate            -> signal that the call should go to a human

All tool execution happens server-side; the agent only returns the
next spoken response to the caller.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from .booking import (
    create_appointment,
    cancel_appointment,
    find_appointment_by_phone,
    get_available_slots,
    reschedule_appointment,
)
from .config import settings
from .models import Business

client = OpenAI(api_key=settings.openai_api_key)

# ---------------------------------------------------------------------------
# Tool / function definitions passed to the LLM
# ---------------------------------------------------------------------------

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check available appointment slots for a service on a given date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "Name of the service (e.g. Haircut)"},
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                },
                "required": ["service_name", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_appointment",
            "description": "Book an appointment for the caller.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string"},
                    "service_name": {"type": "string"},
                    "start_time": {"type": "string", "description": "ISO 8601 datetime, e.g. 2026-03-10T14:30:00"},
                    "staff_name": {"type": "string", "description": "Preferred staff member (optional)"},
                },
                "required": ["customer_name", "service_name", "start_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_appointments",
            "description": "Look up upcoming appointments for the caller by phone number.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Cancel an existing appointment by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "string"},
                },
                "required": ["appointment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate",
            "description": "Transfer the caller to a human agent when unable to help.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                },
                "required": ["reason"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def _build_system_prompt(business: Business, caller_phone: str) -> str:
    services = ", ".join(
        s.get("name", "") for s in (business.services or [])
    ) or "various services"

    hours_lines = []
    for day, times in (business.opening_hours or {}).items():
        if times:
            hours_lines.append(f"  {day}: {times[0]} - {times[1]}")
        else:
            hours_lines.append(f"  {day}: Closed")
    hours_text = "\n".join(hours_lines) or "  (Hours not set)"

    greeting = business.custom_greeting or f"Hello, thank you for calling {business.name}!"

    return f"""You are an AI receptionist for {business.name}.
Your job is to help callers book, reschedule, or cancel appointments,
and answer questions about the business.

Business details:
- Name: {business.name}
- Services offered: {services}
- Opening hours:\n{hours_text}
- Caller's phone number (use for lookups): {caller_phone}

Greeting to use at the start: "{greeting}"

Guidelines:
1. Be warm, concise, and professional. Speak as if on a phone call.
2. Always confirm key details before booking (name, service, time).
3. If asked something you don't know, say you'll pass the message on.
4. Never reveal internal IDs to the caller.
5. If the caller is angry or needs something beyond your capabilities, use the escalate tool.
6. Always offer 2-3 specific time options; never ask the caller to name a time first.
7. Today's date is {datetime.utcnow().strftime('%A, %B %d, %Y')}.
"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class CallAgent:
    """
    Stateful agent for a single phone call.
    Maintains message history and executes tools against the DB.
    """

    def __init__(
        self,
        business: Business,
        caller_phone: str,
        db: Session,
    ):
        self.business = business
        self.caller_phone = caller_phone
        self.db = db
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": _build_system_prompt(business, caller_phone)}
        ]
        self.escalated = False
        self.booking_created: Optional[str] = None  # appointment id if booked

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def respond(self, user_text: str) -> str:
        """
        Accept caller's transcribed utterance, run LLM turn(s), and
        return the assistant's spoken response.
        """
        self.messages.append({"role": "user", "content": user_text})

        # Allow multiple tool-call rounds (e.g., check availability -> book)
        for _ in range(5):  # safety limit
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=self.messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.4,
                max_tokens=400,
            )
            msg = response.choices[0].message

            # No tool calls -> return spoken text
            if not msg.tool_calls:
                reply = msg.content or "I'm sorry, I didn't catch that."
                self.messages.append({"role": "assistant", "content": reply})
                return reply

            # Execute each tool call
            self.messages.append(msg)  # assistant message with tool_calls
            for tc in msg.tool_calls:
                result = self._execute_tool(tc.function.name, tc.function.arguments)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })

        return "I'm having trouble processing that. Let me connect you to someone who can help."

    def get_history(self) -> List[Dict[str, Any]]:
        """Return full message history (for transcript storage)."""
        return self.messages

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def _execute_tool(self, name: str, arguments_json: str) -> Dict[str, Any]:
        try:
            args = json.loads(arguments_json)
        except json.JSONDecodeError:
            return {"error": "Invalid arguments"}

        if name == "check_availability":
            return self._check_availability(args)
        if name == "create_appointment":
            return self._create_appointment(args)
        if name == "find_appointments":
            return self._find_appointments()
        if name == "cancel_appointment":
            return self._cancel_appointment(args)
        if name == "escalate":
            self.escalated = True
            return {"status": "escalating", "reason": args.get("reason")}
        return {"error": f"Unknown tool: {name}"}

    def _check_availability(self, args: dict) -> dict:
        try:
            date = datetime.strptime(args["date"], "%Y-%m-%d")
        except ValueError:
            return {"error": "Invalid date format, use YYYY-MM-DD"}

        slots = get_available_slots(
            self.db, self.business, date, args["service_name"]
        )
        if not slots:
            return {"available": False, "message": "No slots available on that day."}
        return {
            "available": True,
            "slots": [s.strftime("%I:%M %p") for s in slots],
            "date": date.strftime("%A, %B %d"),
        }

    def _create_appointment(self, args: dict) -> dict:
        try:
            start_time = datetime.fromisoformat(args["start_time"])
        except ValueError:
            return {"error": "Invalid start_time format"}

        appt = create_appointment(
            db=self.db,
            business_id=self.business.id,
            customer_name=args["customer_name"],
            customer_phone=self.caller_phone,
            service_name=args["service_name"],
            start_time=start_time,
            staff_name=args.get("staff_name"),
        )
        self.booking_created = appt.id
        return {
            "status": "booked",
            "appointment_id": appt.id,
            "service": appt.service_name,
            "time": appt.start_time.strftime("%I:%M %p on %A, %B %d"),
        }

    def _find_appointments(self) -> dict:
        appts = find_appointment_by_phone(
            self.db, self.business.id, self.caller_phone
        )
        if not appts:
            return {"appointments": [], "message": "No upcoming appointments found."}
        return {
            "appointments": [
                {
                    "id": a.id,
                    "service": a.service_name,
                    "time": a.start_time.strftime("%I:%M %p on %A, %B %d"),
                    "staff": a.staff_name,
                }
                for a in appts
            ]
        }

    def _cancel_appointment(self, args: dict) -> dict:
        appt = cancel_appointment(
            self.db, args["appointment_id"], self.business.id
        )
        if not appt:
            return {"error": "Appointment not found or already cancelled."}
        return {"status": "cancelled", "appointment_id": appt.id}
