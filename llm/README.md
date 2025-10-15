# Concya LLM Service

Fast AI reservation assistant with voice capabilities.

## Features

- 🤖 **GPT-4o-mini** - Fast, efficient language model
- 🎯 **Reservation-focused** - Optimized prompts for quick bookings
- 🔊 **Text-to-Speech** - Natural voice responses
- 📝 **Reservation Management** - Create, view, cancel reservations
- 💾 **Session Memory** - Maintains conversation context
- ⚡ **Optimized for Speed** - Short responses, fast inference

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
export OPENAI_API_KEY="your-key-here"

# Run server
python app.py
# or
uvicorn app:app --reload --port 8001
```

### Docker

```bash
# Build
docker build -t concya-llm .

# Run
docker run -p 8001:8001 \
  -e OPENAI_API_KEY="your-key" \
  concya-llm
```

## API Endpoints

### POST `/conversation`
Process user input and generate response.

```json
{
  "text": "I need a table for 4 people",
  "session_id": "session_123",
  "language": "en"
}
```

Response:
```json
{
  "reply": "I'd be happy to help! What date and time works for you?",
  "session_id": "session_123",
  "reservation_data": {},
  "is_complete": false
}
```

### POST `/speak`
Generate voice audio from text.

```json
{
  "text": "Your reservation is confirmed!",
  "voice": "alloy"
}
```

Returns: `audio/mpeg` file

### POST `/reservations`
Create a reservation.

```json
{
  "customer_name": "John Doe",
  "date": "2024-12-25",
  "time": "19:00",
  "party_size": 4,
  "phone": "+1234567890"
}
```

### GET `/reservations`
List all reservations.

### DELETE `/reservations/{id}`
Cancel a reservation.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for LLM and TTS |
| `PORT` | Server port (default: 8001) |

## Architecture

**Microservices Setup:**
```
STT Service (port 8000) → Transcription only
LLM Service (port 8001) → Conversation + TTS
```

**Flow:**
1. User speaks → STT service transcribes
2. Text sent to LLM service → GPT processes
3. LLM returns reply + audio URL
4. Browser plays audio response

## Optimization Notes

- **max_tokens=80** - Keeps responses brief for speed
- **temperature=0.7** - Balance between creative and consistent
- **speed=1.1** - Slightly faster TTS playback
- **Last 8 messages** - Efficient context window
- **In-memory storage** - Fast for development (use DB for production)

## Production Improvements

1. **Database** - Replace in-memory with PostgreSQL/MongoDB
2. **Redis** - Cache sessions and frequent queries
3. **Rate Limiting** - Prevent API abuse
4. **Authentication** - Secure endpoints
5. **Monitoring** - Add Prometheus/Grafana
6. **Load Balancing** - Handle multiple concurrent users

## License

MIT

