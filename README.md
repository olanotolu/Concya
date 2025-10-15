# Concya - AI Reservation Assistant

**Unified real-time voice-based reservation system with STT, LLM, and TTS**

![Version](https://img.shields.io/badge/version-2.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Overview

Concya is a complete voice-based AI reservation assistant that combines:

- **Speech-to-Text (STT)**: Real-time transcription using WhisperLiveKit with speaker diarization
- **Large Language Model (LLM)**: Conversational AI powered by OpenAI GPT-4o-mini
- **Text-to-Speech (TTS)**: Natural voice responses using OpenAI TTS-1

All services run in a **single Docker container** for simplified deployment and reduced costs.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Concya (Single Pod)                   │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │     STT      │  │     LLM      │  │     TTS      │  │
│  │ WhisperLive  │→ │  GPT-4o-mini │→ │   OpenAI     │  │
│  │  + Diarize   │  │ Reservation  │  │   TTS-1      │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                          │
│  📊 Unified Prometheus Metrics                          │
│  🔄 WebSocket + REST API                                │
│  💾 In-memory conversations & reservations              │
└─────────────────────────────────────────────────────────┘
```

## Features

- ✅ **Real-time transcription** with SimulStreaming (ultra-low latency)
- ✅ **Speaker diarization** using NVIDIA NeMo Sortformer
- ✅ **Multi-language support** with automatic detection
- ✅ **Conversational AI** for natural reservation flow
- ✅ **Voice responses** with natural-sounding TTS
- ✅ **Comprehensive metrics** via Prometheus
- ✅ **Single-pod deployment** for cost efficiency
- ✅ **Full emoji logging** for easy debugging

## Quick Start

### 1. Deploy to RunPod

```bash
# Build and push Docker image
./build-and-push.sh

# Create a new pod on RunPod with:
# - Image: olaoluwasubomi/concya:latest
# - GPU: L40S (or similar NVIDIA GPU)
# - Memory: 16GB minimum
# - Port: 8000/http
# - Environment: OPENAI_API_KEY=sk-...
```

### 2. Access the Service

Visit your RunPod pod URL (e.g., `https://your-pod-id.proxy.runpod.net/`)

The web interface will automatically connect to all services on the same server.

### 3. Test the Full Pipeline

1. Click the red record button
2. Speak: *"I need a reservation for 4 people tomorrow at 7 PM"*
3. Watch the magic:
   - STT transcribes your voice in real-time
   - LLM generates a conversational response
   - TTS speaks the response back to you

## API Endpoints

### General

- `GET /` - Web UI
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics

### STT

- `WS /asr` - WebSocket for real-time transcription

### LLM

- `POST /conversation` - Send text, get conversational response
- `POST /clear_session` - Clear conversation history

### TTS

- `POST /speak` - Generate speech audio from text

### Reservations

- `POST /reservations` - Create a reservation
- `GET /reservations` - List all reservations
- `DELETE /reservations/{id}` - Cancel a reservation

## Configuration

Environment variables:

```bash
# Required
OPENAI_API_KEY=sk-...           # Your OpenAI API key

# Optional
WHISPER_MODEL=base              # Whisper model size (tiny, base, small, medium, large)
WHISPER_LANGUAGE=auto           # Language code (auto, en, fr, es, etc.)
ENABLE_DIARIZATION=true         # Speaker diarization on/off
TARGET_LANGUAGE=                # Translation target (e.g., "fr", "es")
```

## Metrics

Access Prometheus metrics at `/metrics`:

**STT Metrics:**
- `stt_latency_ms` - Processing latency per audio chunk
- `stt_rtf` - Real-Time Factor (< 1.0 = faster than real-time)
- `stt_audio_duration_seconds` - Total audio processed
- `websocket_connections_active` - Active connections

**LLM Metrics:**
- `llm_latency_ms` - Response generation time
- `llm_tokens_used` - Total tokens per request
- `llm_prompt_tokens` - Prompt tokens
- `llm_completion_tokens` - Completion tokens

**TTS Metrics:**
- `tts_latency_ms` - Audio generation time
- `tts_audio_bytes` - Audio size in bytes

**Conversation Metrics:**
- `active_conversations` - Active sessions
- `reservations_created_total` - Total reservations
- `reservations_cancelled_total` - Cancellations

## Development

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY=sk-...

# Run locally
python app.py

# Access at http://localhost:8000
```

### Build Docker Image

```bash
# Build for local testing (ARM64 for Mac M1/M2)
docker build -t concya:local .

# Build for RunPod (AMD64)
docker buildx build --platform linux/amd64 -t olaoluwasubomi/concya:latest --push .
```

## Cost Optimization

Running all services in one pod significantly reduces costs:

**Before (Microservices):**
- STT Pod (GPU): $0.86/hr
- LLM Pod (CPU): $0.10/hr
- **Total: $0.96/hr** = ~$700/month

**After (Unified):**
- Single Pod (GPU): $0.86/hr
- **Total: $0.86/hr** = ~$620/month

**Savings: ~11% + simplified management**

## Architecture Benefits

1. **Cost Efficiency**: Pay for only one pod
2. **No Network Latency**: All services communicate in-process
3. **Simplified Deployment**: Single Docker image
4. **Easier Debugging**: All logs in one place
5. **Unified Metrics**: Single metrics endpoint

## Project Structure

```
Concya/
├── app.py                      # Unified FastAPI app (STT + LLM + TTS)
├── index.html                  # Web UI
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker image
├── build-and-push.sh          # Build script
├── README.md                   # This file
└── RUNPOD_DEPLOYMENT.md       # Deployment guide
```

## Troubleshooting

### STT not working

- Check GPU is available: L40S, A40, RTX 4090, etc.
- Increase memory to 16GB minimum
- Check logs for Whisper model download progress

### LLM/TTS returning errors

- Verify `OPENAI_API_KEY` is set correctly
- Check OpenAI API quota and billing
- Review logs for detailed error messages

### Frontend can't connect

- Ensure port 8000 is exposed
- Hard refresh browser (Cmd+Shift+R / Ctrl+Shift+R)
- Check browser console for errors

## Credits

- **WhisperLiveKit** - Real-time STT engine
- **OpenAI** - GPT-4o-mini & TTS-1
- **NVIDIA NeMo** - Speaker diarization
- **FastAPI** - Web framework
- **Prometheus** - Metrics & monitoring

## License

MIT License - See LICENSE file for details

## Support

For issues, questions, or contributions, please open an issue on GitHub.

---

**Built with ❤️  for seamless voice-based reservations**
