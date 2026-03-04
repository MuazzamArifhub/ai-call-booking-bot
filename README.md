# AI Call Booking Bot

An open-source AI receptionist that answers phone calls for small businesses (barber shops, salons, clinics, etc.), books appointments, answers FAQs, and uses every call to continuously improve itself — all for **free** using open-source tools.

---

## Features

- **Answers inbound calls** via Twilio (free trial covers development)
- **Books, reschedules, and cancels appointments** using natural conversation
- **Answers business FAQs** (hours, pricing, location, services)
- **Sends SMS confirmations** to customers after booking
- **Transcribes and stores every call** for analytics and training
- **Self-improving**: call transcripts feed into a RAG knowledge base
- **Multi-tenant**: one deployment supports multiple businesses
- **Web dashboard** for business owners to manage bookings and view call logs

---

## Tech Stack (100% Free for Development)

| Layer | Technology | Cost |
|---|---|---|
| Telephony | Twilio (free trial) | Free trial |
| Voice AI | OpenAI Whisper (STT) + GPT-4o-mini | Free tier / cheap |
| Backend | Python + FastAPI | Free |
| Database | SQLite (dev) / PostgreSQL (prod) | Free |
| Hosting | Render / Railway free tier | Free |
| SMS | Twilio (free trial) | Free trial |
| Training Data | Local JSONL files + ChromaDB (vector store) | Free |

---

## Project Structure

```
ai-call-booking-bot/
├── app/
│   ├── __init__.py          # App factory
│   ├── config.py            # Config from environment variables
│   ├── models.py            # SQLAlchemy DB models
│   ├── voice_handler.py     # Twilio webhook routes
│   ├── agent.py             # LLM conversation agent
│   ├── booking.py           # Appointment CRUD logic
│   ├── training.py          # Call data -> training pipeline
│   └── dashboard.py         # Business owner dashboard routes
├── data/
│   ├── transcripts/         # Raw call transcripts (gitignored)
│   └── training/            # Cleaned training JSONL files
├── tests/
│   ├── test_agent.py
│   ├── test_booking.py
│   └── test_voice.py
├── main.py                  # Application entry point
├── requirements.txt
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/MuazzamArifhub/ai-call-booking-bot.git
cd ai-call-booking-bot
```

### 2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set up environment variables
```bash
cp .env.example .env
# Edit .env with your API keys (see .env.example)
```

### 4. Initialize the database
```bash
python main.py init-db
```

### 5. Run locally
```bash
uvicorn main:app --reload --port 8000
```

### 6. Expose to internet (for Twilio webhooks)
```bash
ngrok http 8000
# Copy the https URL and set it as your Twilio webhook
```

---

## Twilio Setup (Free Trial)

1. Sign up at [twilio.com](https://twilio.com) — free trial gives you ~$15 credit
2. Get a free phone number
3. Set the Voice webhook to: `https://your-ngrok-url.ngrok.io/voice/incoming`
4. Add your Twilio credentials to `.env`

---

## How It Works

```
Customer calls business number
        ↓
Twilio forwards to your app (/voice/incoming)
        ↓
App greets caller (TTS via Twilio)
        ↓
Customer speaks → Twilio transcribes via Whisper
        ↓
LLM Agent processes intent:
  - FAQ? → answer from knowledge base
  - Booking? → check availability → confirm slot → write to DB
  - Cancel/Reschedule? → update DB → confirm
  - Confused? → transfer to human / take message
        ↓
SMS confirmation sent to customer
        ↓
Call transcript saved → fed into training pipeline
```

---

## Training Pipeline

Every call automatically improves the bot:

1. **Transcription**: Whisper converts audio to text
2. **PII Scrubbing**: Names, phone numbers masked before storage
3. **Intent Tagging**: Auto-tagged as booking/FAQ/escalation/etc.
4. **Vector Index**: Transcripts indexed in ChromaDB for RAG
5. **JSONL Export**: Periodic export of high-quality pairs for fine-tuning

Consent is requested at the start of every call. Callers who opt out are excluded from training data.

---

## Incremental Development Roadmap

- [x] Repository setup
- [ ] Phase 1: Basic call answering + hardcoded FAQ responses
- [ ] Phase 2: Appointment booking (SQLite backend)
- [ ] Phase 3: LLM agent with intent detection
- [ ] Phase 4: Call transcription + storage
- [ ] Phase 5: RAG pipeline (ChromaDB)
- [ ] Phase 6: Business owner dashboard
- [ ] Phase 7: Multi-tenant support
- [ ] Phase 8: SMS confirmations
- [ ] Phase 9: Fine-tuning pipeline

---

## Contributing

PRs welcome! Please open an issue first to discuss major changes.

## License

MIT
