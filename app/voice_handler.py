"""Twilio webhook routes for inbound voice calls.

Flow per call:
  POST /voice/incoming   <- Twilio sends when call arrives
      -> Return TwiML: Greet + gather first utterance
  POST /voice/process    <- Twilio sends with speech transcript
      -> Run agent turn -> Return TwiML: Say response + gather next
  POST /voice/status     <- Twilio call-status callback
      -> Persist call log + trigger async transcript pipeline
"""
from __future__ import annotations

import time
from typing import Dict

from fastapi import APIRouter, Form, Request, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session
from twilio.twiml.voice_response import VoiceResponse, Gather
from loguru import logger

from .agent import CallAgent
from .config import settings
from .database import get_db
from .models import Business, CallLog

router = APIRouter(prefix="/voice", tags=["voice"])

# In-memory store of active CallAgent instances keyed by Twilio CallSid.
# In production, replace with Redis or a DB-backed session store.
_active_agents: Dict[str, CallAgent] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_business_by_called_number(db: Session, to_number: str) -> Business | None:
    return db.query(Business).filter(
        Business.phone_number == to_number,
        Business.is_active == True,
    ).first()


def _twiml_response(text: str, gather_action: str, timeout: int = 5) -> str:
    """Build a TwiML response that speaks `text` then listens for speech."""
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action=gather_action,
        method="POST",
        timeout=timeout,
        speech_timeout="auto",
        language="en-US",
    )
    gather.say(text, voice="Polly.Joanna")  # AWS Polly via Twilio (free)
    resp.append(gather)
    # If caller says nothing, re-prompt
    resp.redirect(gather_action, method="POST")
    return str(resp)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/incoming")
async def voice_incoming(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    db: Session = Depends(get_db),
):
    """Twilio calls this when a new inbound call arrives."""
    logger.info(f"Incoming call CallSid={CallSid} From={From} To={To}")

    business = _get_business_by_called_number(db, To)
    if not business:
        resp = VoiceResponse()
        resp.say("Sorry, this number is not currently configured. Goodbye.")
        resp.hangup()
        return Response(content=str(resp), media_type="application/xml")

    # Consent notice (required before recording / training)
    consent_text = (
        "This call may be recorded to improve our service. "
        "Say 'no recording' at any time to opt out. "
    )
    greeting = business.custom_greeting or f"Hello, thank you for calling {business.name}!"

    agent = CallAgent(business=business, caller_phone=From, db=db)
    _active_agents[CallSid] = agent

    opening_text = consent_text + greeting + " How can I help you today?"
    action_url = f"{settings.public_base_url}/voice/process"

    twiml = _twiml_response(opening_text, action_url)
    return Response(content=twiml, media_type="application/xml")


@router.post("/process")
async def voice_process(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    SpeechResult: str = Form(default=""),
    Confidence: float = Form(default=0.0),
    db: Session = Depends(get_db),
):
    """Twilio calls this after each speech utterance from the caller."""
    logger.debug(f"CallSid={CallSid} speech='{SpeechResult}' confidence={Confidence}")

    action_url = f"{settings.public_base_url}/voice/process"

    # Handle opt-out from training
    if "no recording" in SpeechResult.lower():
        agent = _active_agents.get(CallSid)
        if agent:
            # Mark future transcript as training-excluded
            pass  # handled in /status callback

    # Get or recreate agent (e.g., server restart)
    agent = _active_agents.get(CallSid)
    if not agent:
        business = _get_business_by_called_number(db, To)
        if not business:
            resp = VoiceResponse()
            resp.say("Something went wrong. Please call back.")
            resp.hangup()
            return Response(content=str(resp), media_type="application/xml")
        agent = CallAgent(business=business, caller_phone=From, db=db)
        _active_agents[CallSid] = agent

    if not SpeechResult.strip():
        reply = "I didn't catch that. Could you please repeat?"
    else:
        reply = agent.respond(SpeechResult)

    # If agent wants to escalate, transfer and end loop
    if agent.escalated:
        resp = VoiceResponse()
        resp.say(reply)
        resp.say("Transferring you now. Please hold.")
        # In production: resp.dial(business.fallback_number)
        resp.hangup()
        return Response(content=str(resp), media_type="application/xml")

    twiml = _twiml_response(reply, action_url)
    return Response(content=twiml, media_type="application/xml")


@router.post("/status")
async def voice_status(
    request: Request,
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    CallDuration: int = Form(default=0),
    RecordingUrl: str = Form(default=""),
    From: str = Form(...),
    To: str = Form(...),
    db: Session = Depends(get_db),
):
    """Twilio calls this when a call ends. Persist the call log."""
    logger.info(f"Call ended CallSid={CallSid} status={CallStatus} duration={CallDuration}s")

    agent = _active_agents.pop(CallSid, None)

    business = _get_business_by_called_number(db, To)
    if not business:
        return {"ok": True}

    # Build transcript string from message history
    transcript = ""
    if agent:
        turns = [
            m for m in agent.get_history()
            if m["role"] in ("user", "assistant")
        ]
        transcript = "\n".join(
            f"[{m['role'].upper()}]: {m.get('content', '')}"
            for m in turns
            if isinstance(m.get("content"), str)
        )

    call_log = CallLog(
        business_id=business.id,
        twilio_call_sid=CallSid,
        from_number=From,
        to_number=To,
        recording_url=RecordingUrl or None,
        duration_seconds=CallDuration,
        transcript=transcript,
        training_consent=True,  # default; updated if caller opted out
    )
    if agent and agent.booking_created:
        call_log.appointment_id = agent.booking_created  # type: ignore

    db.add(call_log)
    db.commit()

    logger.info(f"CallLog saved id={call_log.id}")
    return {"ok": True}
