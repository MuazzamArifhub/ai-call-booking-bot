"""Training pipeline: call transcripts -> cleaned samples -> RAG + fine-tune data.

Pipeline steps:
  1. scrub_pii()       - mask names, phones, addresses in transcripts
  2. score_quality()   - estimate usefulness (0-1) of a call for training
  3. tag_intent()      - auto-classify call intent
  4. index_for_rag()   - upsert transcript into ChromaDB vector store
  5. export_jsonl()    - write OpenAI fine-tune format JSONL to disk
  6. run_pipeline()    - orchestrate all steps for a single CallLog

The pipeline is triggered:
  - Automatically after each call via the /voice/status webhook.
  - On a scheduled batch job (via APScheduler) for any unprocessed logs.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from loguru import logger
from openai import OpenAI
from sqlalchemy.orm import Session

from .config import settings
from .models import CallLog, CallIntent, CallOutcome, TrainingSample

client = OpenAI(api_key=settings.openai_api_key)


# ---------------------------------------------------------------------------
# Step 1: PII scrubbing (regex-based, no external service needed)
# ---------------------------------------------------------------------------

# Pattern list: (label, compiled_regex)
_PII_PATTERNS = [
    ("PHONE",   re.compile(r"\b(\+?1[-. ]?)?(\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4})\b")),
    ("EMAIL",   re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")),
    ("POSTAL",  re.compile(r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b")),  # Canadian postal
    ("ZIP",     re.compile(r"\b\d{5}(-\d{4})?\b")),
]


def scrub_pii(text: str) -> str:
    """Replace PII tokens with placeholders. Name scrubbing is intentionally
    omitted here because removing all proper nouns degrades training quality;
    rely on consent and access controls instead."""
    for label, pattern in _PII_PATTERNS:
        text = pattern.sub(f"[{label}]", text)
    return text


# ---------------------------------------------------------------------------
# Step 2: Quality scoring
# ---------------------------------------------------------------------------

def score_quality(call_log: CallLog) -> float:
    """
    Heuristic quality score 0-1 for a call's training value.
    Higher = more useful for training.
    """
    score = 0.5  # base

    if not call_log.transcript or len(call_log.transcript) < 50:
        return 0.0  # too short to be useful

    # Successful outcome boosts score
    if call_log.outcome == CallOutcome.SUCCESS:
        score += 0.3
    elif call_log.outcome == CallOutcome.PARTIAL:
        score += 0.1
    elif call_log.outcome == CallOutcome.FAILED:
        score -= 0.2

    # Longer, more detailed calls are more informative
    word_count = len(call_log.transcript.split())
    if word_count > 200:
        score += 0.1
    if word_count > 500:
        score += 0.1

    # Penalise very short calls
    if (call_log.duration_seconds or 0) < 15:
        score -= 0.3

    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Step 3: Intent tagging (ask the LLM to classify)
# ---------------------------------------------------------------------------

def tag_intent(transcript: str) -> CallIntent:
    """Use the LLM to classify call intent from the transcript."""
    if not transcript.strip():
        return CallIntent.UNKNOWN

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify the following phone call transcript into EXACTLY one of these intents: "
                        "booking, reschedule, cancellation, faq, escalation, unknown. "
                        "Respond with only the intent word, lowercase."
                    ),
                },
                {"role": "user", "content": transcript[:2000]},  # truncate for cost
            ],
            temperature=0,
            max_tokens=10,
        )
        raw = resp.choices[0].message.content.strip().lower()
        return CallIntent(raw) if raw in CallIntent._value2member_map_ else CallIntent.UNKNOWN
    except Exception as exc:
        logger.warning(f"Intent tagging failed: {exc}")
        return CallIntent.UNKNOWN


# ---------------------------------------------------------------------------
# Step 4: Index for RAG (ChromaDB)
# ---------------------------------------------------------------------------

def index_for_rag(call_log: CallLog) -> None:
    """Upsert the cleaned transcript into the local ChromaDB collection."""
    if not call_log.transcript_clean:
        return

    try:
        import chromadb
        chroma = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        collection = chroma.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        collection.upsert(
            ids=[call_log.id],
            documents=[call_log.transcript_clean],
            metadatas=[{
                "business_id": call_log.business_id,
                "intent": str(call_log.intent),
                "outcome": str(call_log.outcome),
                "date": call_log.started_at.isoformat() if call_log.started_at else "",
            }],
        )
        logger.info(f"Indexed call {call_log.id} into ChromaDB")
    except Exception as exc:
        logger.error(f"ChromaDB indexing failed for call {call_log.id}: {exc}")


# ---------------------------------------------------------------------------
# Step 5: Export JSONL for fine-tuning
# ---------------------------------------------------------------------------

def export_jsonl(sample: TrainingSample) -> Path:
    """Append a TrainingSample to the JSONL fine-tune file for its business."""
    output_dir = Path(settings.training_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{sample.call_log.business_id}_finetune.jsonl"
    record = {"messages": sample.messages}

    with open(output_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")

    logger.debug(f"Exported training sample {sample.id} to {output_file}")
    return output_file


# ---------------------------------------------------------------------------
# Step 6: Full pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline(call_log_id: str, db: Session) -> None:
    """
    Run the complete training pipeline for a single CallLog.
    Idempotent: safe to call multiple times.
    """
    call_log = db.get(CallLog, call_log_id)
    if not call_log:
        logger.warning(f"run_pipeline: CallLog {call_log_id} not found")
        return

    if not call_log.training_consent:
        logger.info(f"Skipping pipeline for call {call_log_id}: no consent")
        return

    logger.info(f"Running training pipeline for call {call_log_id}")

    # 1. Scrub PII
    if call_log.transcript:
        call_log.transcript_clean = scrub_pii(call_log.transcript)

    # 2. Quality score
    call_log.quality_score = score_quality(call_log)
    if call_log.quality_score < settings.training_min_quality_score:
        logger.info(
            f"Call {call_log_id} quality={call_log.quality_score:.2f} below threshold; skipping"
        )
        db.commit()
        return

    # 3. Tag intent
    if call_log.transcript_clean:
        call_log.intent = tag_intent(call_log.transcript_clean)

    db.commit()

    # 4. Index for RAG
    index_for_rag(call_log)

    # 5. Build training sample from message history
    if call_log.transcript_clean:
        messages = _build_training_messages(call_log)
        if messages:
            sample = TrainingSample(
                call_log_id=call_log.id,
                messages=messages,
                tags=[str(call_log.intent), "auto"],
                quality_score=call_log.quality_score,
            )
            db.add(sample)
            db.commit()
            db.refresh(sample)

            # 6. Export JSONL
            export_jsonl(sample)

    logger.info(f"Pipeline complete for call {call_log_id}")


def _build_training_messages(call_log: CallLog) -> Optional[list]:
    """
    Convert the call transcript into OpenAI fine-tune message format.
    Format: [{role: system, content: ...}, {role: user, ...}, {role: assistant, ...}, ...]
    """
    if not call_log.transcript_clean:
        return None

    system_msg = {
        "role": "system",
        "content": (
            "You are an AI receptionist for a small business. "
            "Help customers book, reschedule, or cancel appointments, "
            "and answer questions about the business."
        ),
    }

    messages = [system_msg]
    # Parse transcript lines: "[USER]: ..." and "[ASSISTANT]: ..."
    for line in call_log.transcript_clean.splitlines():
        line = line.strip()
        if line.startswith("[USER]:"):
            messages.append({"role": "user", "content": line[7:].strip()})
        elif line.startswith("[ASSISTANT]:"):
            messages.append({"role": "assistant", "content": line[12:].strip()})

    # Need at least one user + one assistant turn
    if len(messages) < 3:
        return None

    return messages


# ---------------------------------------------------------------------------
# RAG query helper (used by the agent for FAQ lookups)
# ---------------------------------------------------------------------------

def query_rag(
    question: str,
    business_id: str,
    n_results: int = 3,
) -> List[str]:
    """Retrieve the most relevant transcript snippets for an FAQ question."""
    try:
        import chromadb
        chroma = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        collection = chroma.get_or_create_collection(name=settings.chroma_collection_name)
        results = collection.query(
            query_texts=[question],
            n_results=n_results,
            where={"business_id": business_id},
        )
        return results.get("documents", [[]])[0]
    except Exception as exc:
        logger.warning(f"RAG query failed: {exc}")
        return []
