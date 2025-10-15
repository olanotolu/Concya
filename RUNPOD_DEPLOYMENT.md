# RunPod Deployment Guide - Concya Unified Service

Complete guide for deploying Concya (STT + LLM + TTS) as a single pod on RunPod.

## Overview

Concya v2.0 runs as a **single unified service** combining:
- Speech-to-Text (WhisperLiveKit + Diarization)
- LLM Conversation (GPT-4o-mini)
- Text-to-Speech (OpenAI TTS-1)

This reduces costs and simplifies deployment compared to separate microservices.

---

## Prerequisites

1. **RunPod Account** with payment method configured
2. **Docker Hub Account** (for image: `olaoluwasubomi/concya:latest`)
3. **OpenAI API Key** from https://platform.openai.com/api-keys
4. **Local Docker** with buildx support (for building images)

---

## Step 1: Build and Push Docker Image

From your local machine:

```bash
cd /path/to/Concya

# Build and push the unified image
./build-and-push.sh
```

This builds a single AMD64 image and pushes it to Docker Hub as `olaoluwasubomi/concya:latest`.

---

## Step 2: Create RunPod Pod

### 2.1 Go to RunPod

1. Visit https://www.runpod.io/
2. Log in and navigate to **"My Pods"**
3. Click **"+ Deploy"**

### 2.2 Configure Pod Settings

**Container Image:**
```
olaoluwasubomi/concya:latest
```

**GPU Selection:**
- **Recommended:** NVIDIA L40S (48GB VRAM, $0.86/hr)
- **Alternatives:** RTX 4090, A40, A6000

**Resources:**
- **Container Disk:** 20 GB
- **Container Memory:** 16 GB minimum
- **Volume:** Not required (models download on startup)

**Ports:**
- **Port 8000** → HTTP (Auto-assign public URL)

**Environment Variables:**
```bash
OPENAI_API_KEY=sk-proj-your-actual-key-here
WHISPER_MODEL=base
ENABLE_DIARIZATION=true
WHISPER_LANGUAGE=auto
```

### 2.3 Deploy

Click **"Deploy"** and wait for initialization (1-2 minutes).

---

## Step 3: Access Your Service

### 3.1 Get Pod URL

RunPod will assign a URL like:
```
https://abc123xyz-8000.proxy.runpod.net
```

### 3.2 Test the Frontend

Visit the URL in your browser. You should see the Concya web interface.

### 3.3 Test the Pipeline

1. Click the red record button
2. Allow microphone access
3. Speak: **"I need a reservation"**
4. Watch the full pipeline:
   - 🎤 STT transcribes in real-time
   - 🤖 LLM generates conversational response
   - 🔊 TTS plays audio reply

---

## Step 4: Monitor Performance

### 4.1 View Logs

Go to **Pod → Logs** tab to see:

```
🚀 Starting Concya - Unified STT + LLM + TTS Service
📦 Whisper Model: base
🌍 Language: auto
👥 Diarization: True
🔥 Initializing TranscriptionEngine...
✅ TranscriptionEngine ready with diarization!
INFO: Uvicorn running on http://0.0.0.0:8000
```

### 4.2 Check Metrics

Visit:
```
https://your-pod-url.proxy.runpod.net/metrics
```

You'll see Prometheus metrics:
```
# STT Metrics
stt_latency_ms{...}
stt_rtf{...}  # < 1.0 means faster than real-time!

# LLM Metrics
llm_latency_ms{...}
llm_tokens_used{...}

# TTS Metrics
tts_latency_ms{...}
tts_audio_bytes{...}

# Conversation Metrics
active_conversations{...}
reservations_created_total{...}
```

### 4.3 Health Check

```bash
curl https://your-pod-url.proxy.runpod.net/health
```

Response:
```json
{
  "status": "healthy",
  "service": "concya-unified",
  "stt_model": "base",
  "language": "auto",
  "diarization": true,
  "translation": false
}
```

---

## API Usage Examples

### 1. Real-Time Transcription (WebSocket)

```javascript
const ws = new WebSocket('wss://your-pod-url.proxy.runpod.net/asr');

ws.onopen = () => {
  // Send audio chunks as binary
  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => {
        ws.send(e.data);
      };
      mediaRecorder.start(100); // 100ms chunks
    });
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Transcription:', data);
};
```

### 2. LLM Conversation

```bash
curl -X POST https://your-pod-url.proxy.runpod.net/conversation \
  -H "Content-Type: application/json" \
  -d '{
    "text": "I need a reservation for 4 people",
    "session_id": "user123",
    "language": "en"
  }'
```

Response:
```json
{
  "reply": "I'd be happy to help! What date and time works for you?",
  "session_id": "user123",
  "reservation_data": {},
  "is_complete": false
}
```

### 3. Text-to-Speech

```bash
curl -X POST https://your-pod-url.proxy.runpod.net/speak \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Great! I've reserved Friday at 7pm for John, party of 4",
    "voice": "alloy"
  }' \
  --output response.mp3
```

### 4. Create Reservation

```bash
curl -X POST https://your-pod-url.proxy.runpod.net/reservations \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "John Doe",
    "date": "2025-10-15",
    "time": "19:00",
    "party_size": 4,
    "phone": "+1234567890"
  }'
```

### 5. List Reservations

```bash
curl https://your-pod-url.proxy.runpod.net/reservations
```

---

## Troubleshooting

### Pod Won't Start

**Symptom:** Pod status shows "Unhealthy" or crashes on startup

**Solutions:**
1. Check logs for OOM errors → Increase memory to 16GB+
2. Check GPU is available → Use L40S or similar NVIDIA GPU
3. Check OpenAI API key → Verify it's set correctly

### STT Not Transcribing

**Symptom:** WebSocket connects but no transcriptions appear

**Solutions:**
1. Check browser console for errors
2. Verify microphone permissions granted
3. Check RunPod logs for Whisper model download progress
4. Wait 30-60 seconds for model initialization

### LLM Returns Generic Errors

**Symptom:** "I apologize, I'm having trouble processing your request."

**Solutions:**
1. Check LLM logs in RunPod
2. Verify OPENAI_API_KEY is valid
3. Check OpenAI account has credits
4. Look for specific error in logs

### TTS Audio Not Playing

**Symptom:** LLM responds but no audio plays

**Solutions:**
1. Check browser console for 500 errors on /speak
2. Verify OPENAI_API_KEY has TTS access
3. Check audio blob size in console (should be > 0 bytes)
4. Try hard refresh (Cmd+Shift+R / Ctrl+Shift+R)

### High Latency

**Symptom:** Slow responses (> 3 seconds total)

**Metrics to check:**
```
stt_rtf > 1.0          → Need faster GPU or smaller model
llm_latency_ms > 2000  → Reduce max_tokens or check API
tts_latency_ms > 3000  → Check network or API quota
```

**Solutions:**
1. Use smaller Whisper model (`tiny` or `base`)
2. Reduce `max_tokens` in conversation endpoint
3. Check RunPod region (use closest to you)
4. Disable diarization if not needed

---

## Cost Analysis

### Single Pod (Unified Service)

**GPU Pod (L40S):**
- **Rate:** $0.86/hr
- **Daily:** $20.64
- **Monthly:** ~$620

**What you get:**
- STT with diarization
- Unlimited LLM conversations
- Unlimited TTS generations
- All metrics and monitoring

### Cost-Saving Tips

1. **Use smaller Whisper model** (`base` vs `large`)
2. **Stop pod when not in use** (RunPod charges only when running)
3. **Set auto-stop** after X minutes of inactivity
4. **Monitor token usage** via metrics to optimize prompts

---

## Updating the Service

### 1. Make Code Changes Locally

```bash
cd /path/to/Concya
# Edit app.py, index.html, etc.
```

### 2. Rebuild and Push

```bash
./build-and-push.sh
```

### 3. Restart Pod

Go to RunPod → Your Pod → **Stop** → Wait → **Start**

The pod will pull the fresh `olaoluwasubomi/concya:latest` image.

---

## Advanced Configuration

### Environment Variables

```bash
# Whisper Model
WHISPER_MODEL=base          # tiny, base, small, medium, large

# Language
WHISPER_LANGUAGE=auto       # auto, en, fr, es, de, etc.

# Diarization
ENABLE_DIARIZATION=true     # true/false

# Translation (optional)
TARGET_LANGUAGE=fr          # Translate to French

# OpenAI
OPENAI_API_KEY=sk-...       # Required
```

### Custom Whisper Model

For better accuracy, use larger models:
- `tiny` - Fastest, lowest quality
- `base` - **Recommended for most use cases**
- `small` - Better quality, slower
- `medium` - High quality, GPU intensive
- `large` - Best quality, requires 16GB+ VRAM

### Disable Diarization

If you don't need speaker identification:
```bash
ENABLE_DIARIZATION=false
```

This reduces latency and memory usage.

---

## Production Considerations

### 1. Persistent Storage

For production, add a persistent database:

```python
# Replace in-memory storage
# conversations: Dict[str, List[dict]] = {}
# reservations: List[dict] = []

# With PostgreSQL, Redis, or MongoDB
import psycopg2
# ... database connection logic
```

### 2. Authentication

Add API key authentication:

```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

@app.post("/conversation")
async def conversation(
    request: ConversationRequest,
    api_key: str = Security(api_key_header)
):
    if api_key != os.getenv("CONCYA_API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")
    # ... rest of logic
```

### 3. Rate Limiting

Protect against abuse:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/conversation")
@limiter.limit("10/minute")
async def conversation(request: Request, ...):
    # ... logic
```

### 4. Monitoring

Set up Grafana dashboards:

1. Install Prometheus + Grafana
2. Configure scraping from `/metrics` endpoint
3. Create dashboards for:
   - STT RTF over time
   - LLM latency percentiles
   - Token usage trends
   - Error rates

---

## Support

For issues or questions:
1. Check the logs first
2. Review this guide
3. Open an issue on GitHub
4. Check RunPod community forums

---

**Happy deploying! 🚀**
