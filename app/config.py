"""Configuration management via environment variables."""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────
    app_name: str = "AI Call Booking Bot"
    debug: bool = False
    secret_key: str = Field(default="change-me-in-production")

    # ── Database ─────────────────────────────────────────────
    # SQLite for development, PostgreSQL for production
    database_url: str = Field(default="sqlite:///./ai_booking.db")

    # ── Twilio ───────────────────────────────────────────────
    twilio_account_sid: str = Field(default="")
    twilio_auth_token: str = Field(default="")
    twilio_phone_number: str = Field(default="")  # e.g. +12065551234

    # ── OpenAI ───────────────────────────────────────────────
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")  # cheapest capable model
    openai_whisper_model: str = Field(default="whisper-1")

    # ── ChromaDB (local vector store for RAG) ────────────────
    chroma_persist_dir: str = Field(default="./data/chroma")
    chroma_collection_name: str = Field(default="call_transcripts")

    # ── Training pipeline ────────────────────────────────────
    transcripts_dir: str = Field(default="./data/transcripts")
    training_output_dir: str = Field(default="./data/training")
    # Minimum confidence score (0-1) to include a call in training data
    training_min_quality_score: float = Field(default=0.7)

    # ── Consent & recording ──────────────────────────────────
    # Set True to record calls (requires explicit caller consent prompt)
    record_calls: bool = Field(default=False)
    recording_retention_days: int = Field(default=90)

    # ── Ngrok / public URL (dev only) ────────────────────────
    # Used to build callback URLs for Twilio webhooks
    public_base_url: str = Field(default="http://localhost:8000")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (reads .env once)."""
    return Settings()


# Convenience alias used throughout the app
settings = get_settings()
