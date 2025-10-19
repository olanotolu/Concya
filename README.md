# Concya

AI restaurant reservation assistant with real-time voice processing.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables in `.env`

3. Run server:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Components

- `app.py` - Main FastAPI server
- `stt/` - Speech-to-text (WhisperLive)
- `llm/` - Language model (GPT-4o-mini)
- `tts/` - Text-to-speech (OpenAI)
- `restaurant/` - Booking logic and database
- `twilio_gateway/` - Phone integration

## Deployment

Use `Dockerfile` for containerized deployment.
