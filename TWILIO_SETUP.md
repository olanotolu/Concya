# Twilio Voice Integration Setup Guide

Complete guide to configure Twilio Voice with Concya AI Reservation Assistant.

## Overview

Twilio Voice integration allows callers to interact with Concya via phone calls. The system streams audio bidirectionally between Twilio and your Concya server, providing real-time STT, LLM, and TTS services.

## Architecture

```
Caller → Twilio Phone Number
         ↓
    Twilio Voice API (webhook: /twilio/voice)
         ↓
    TwiML Response with <Say> + <Connect><Stream>
         ↓
    Twilio Media Stream WebSocket (/twilio/stream)
         ↓
    Audio Bridge (8kHz µ-law ↔ 16kHz PCM)
         ↓
    Concya STT (/asr) → LLM (/conversation) → TTS (/speak)
         ↓
    Audio Back to Caller
```

## Prerequisites

1. **Twilio Account**: [Sign up at twilio.com](https://www.twilio.com/try-twilio)
2. **Twilio Phone Number**: Purchase a phone number with Voice capabilities
3. **Concya Server**: Running on publicly accessible HTTPS URL (RunPod recommended)
4. **Dependencies**: Installed via `pip install -r requirements.txt`

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages for Twilio integration:
- `twilio>=8.0.0` - Twilio Python SDK
- `pydub>=0.25.1` - Audio format conversion (MP3 handling)
- `scipy>=1.10.0` - Audio resampling
- `soundfile>=0.12.1` - Audio file I/O

**Additional system dependencies:**

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Linux:**
```bash
sudo apt-get update
sudo apt-get install ffmpeg libsndfile1
```

**Windows:**
Download ffmpeg from [ffmpeg.org](https://ffmpeg.org/) and add to PATH.

## Step 2: Configure Environment Variables

Add these to your environment (e.g., RunPod template environment variables):

```bash
# Twilio Configuration
export TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export TWILIO_AUTH_TOKEN="your_auth_token_here"
export TWILIO_PHONE_NUMBER="+1234567890"
export PUBLIC_WEBHOOK_URL="https://your-runpod-id.proxy.runpod.net"

# Concya Service URLs (usually same as PUBLIC_WEBHOOK_URL)
export CONCYA_STT_URL="ws://localhost:8000"  # or wss:// for production
export CONCYA_LLM_URL="http://localhost:8000"
export CONCYA_TTS_URL="http://localhost:8000"

# OpenAI API Key (required for LLM and TTS)
export OPENAI_API_KEY="sk-..."
```

### Getting Twilio Credentials

1. **Log in to Twilio Console**: [console.twilio.com](https://console.twilio.com)
2. **Find Account SID and Auth Token**: 
   - Dashboard → Account Info → Account SID
   - Click "Show" to reveal Auth Token
3. **Buy Phone Number**:
   - Phone Numbers → Buy a Number
   - Select country and search
   - Choose number with "Voice" capability
   - Purchase ($1-2/month typically)

## Step 3: Configure Twilio Phone Number Webhooks

1. Go to **Phone Numbers → Manage → Active Numbers**
2. Click on your purchased phone number
3. Scroll to **Voice Configuration**
4. Set **A CALL COMES IN** webhook:
   ```
   https://your-runpod-id.proxy.runpod.net/twilio/voice
   ```
   - Method: **HTTP POST**
   - Save configuration

5. **(Optional)** Set **STATUS CALLBACK URL** for call tracking:
   ```
   https://your-runpod-id.proxy.runpod.net/twilio/status
   ```
   - Method: **HTTP POST**

## Step 4: Deploy to RunPod

### Update Dockerfile

The existing Dockerfile should work. Ensure it includes the new dependencies:

```dockerfile
# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
```

### Build and Push

```bash
./build-and-push.sh
```

### Configure RunPod Pod

1. **Create or Edit Pod** with image: `olaoluwasubomi/concya:latest`
2. **Environment Variables** - Add all required variables:
   ```
   OPENAI_API_KEY=sk-...
   TWILIO_ACCOUNT_SID=AC...
   TWILIO_AUTH_TOKEN=...
   TWILIO_PHONE_NUMBER=+1...
   PUBLIC_WEBHOOK_URL=https://YOUR-POD-ID.proxy.runpod.net
   ```
3. **Expose Port**: 8000 (HTTP)
4. **GPU**: L40S or similar NVIDIA GPU
5. **Storage**: 20GB minimum

### Get RunPod URL

After deployment, your pod URL will be:
```
https://YOUR-POD-ID.proxy.runpod.net
```

Use this URL for `PUBLIC_WEBHOOK_URL`.

## Step 5: Test the Integration

### Health Check

```bash
curl https://your-pod-id.proxy.runpod.net/twilio/health
```

Expected response:
```json
{
  "status": "healthy",
  "active_calls": 0,
  "config": {
    "twilio_configured": true,
    "webhook_url": "https://your-pod-id.proxy.runpod.net"
  }
}
```

### Test Webhook

```bash
curl -X POST https://your-pod-id.proxy.runpod.net/twilio/voice \
  -d "CallSid=CA1234567890" \
  -d "From=+15551234567" \
  -d "To=+15559876543"
```

Expected: TwiML XML response with `<Say>` and `<Stream>` tags.

### Test Phone Call

1. Call your Twilio phone number from your mobile phone
2. You should hear: "Hi, this is Concya, your AI reservation assistant!"
3. Speak naturally: "I need a table for 4 people tomorrow at 7pm"
4. Wait for AI response

### Monitor Logs

Watch server logs for activity:
```bash
# In RunPod pod logs or local terminal
📞 [TWILIO] Incoming call: CAxxxxxxxx
   ├─ From: +15551234567
   └─ To: +15559876543
🔌 [TWILIO-WS] Media Stream connected
✅ [TWILIO-WS] Stream connected
🎬 [TWILIO-WS] Stream started
🔗 [STT] Connecting to Concya STT
✅ [STT] Connected to Concya STT
📝 [STT] Transcription: 'I need a table for 4 tomorrow at 7pm'
🤔 [LLM] Processing: 'I need a table for 4 tomorrow at 7pm'
💬 [LLM] Reply: 'Perfect! I have reserved...'
🔊 [TTS] Generating audio...
✅ [TTS] Generated 15234 bytes in 523ms
📤 [TWILIO] Streaming audio back to caller
```

## Troubleshooting

### Issue: Call connects but no audio

**Symptoms**: Call connects, greeting plays, but no response to speech.

**Solutions**:
1. Check ffmpeg is installed: `ffmpeg -version`
2. Verify environment variables are set
3. Check server logs for audio conversion errors
4. Test STT endpoint directly: `curl http://localhost:8000/health`

### Issue: TwiML webhook fails

**Symptoms**: Call drops immediately or error message.

**Solutions**:
1. Verify webhook URL is publicly accessible
2. Check HTTPS (not HTTP) for production
3. Test webhook manually: `curl -X POST https://your-url/twilio/voice`
4. Check Twilio Console → Monitor → Logs for error details

### Issue: Poor audio quality

**Symptoms**: Garbled audio, choppy playback, incorrect transcriptions.

**Solutions**:
1. Check network latency between Twilio and your server
2. Verify audio resampling is working (should see 8kHz → 16kHz in logs)
3. Increase audio buffer size if needed (edit `twilio_integration.py`)
4. Use better quality Whisper model: `WHISPER_MODEL=medium`

### Issue: High latency

**Symptoms**: Long delays between speech and AI response.

**Solutions**:
1. Use faster Whisper model: `WHISPER_MODEL=tiny` or `base`
2. Check Prometheus metrics: `/metrics` → `twilio_audio_latency_ms`
3. Optimize LLM: Use `gpt-4o-mini` (already default)
4. Deploy closer to Twilio servers (US-based RunPod)

### Issue: Call drops after 10 minutes

**Behavior**: This is expected - calls timeout after 10 minutes.

**Solution**: Adjust `CALL_TIMEOUT_SECONDS` in `twilio_integration.py` if needed.

## Monitoring

### Prometheus Metrics

Access metrics at: `https://your-url/metrics`

**Twilio-specific metrics:**
- `twilio_calls_total` - Total calls received
- `twilio_calls_active` - Currently active calls
- `twilio_call_duration_seconds` - Call duration histogram
- `twilio_audio_latency_ms` - Round-trip latency (STT+LLM+TTS)

### Example Grafana Dashboard

Query examples:
```promql
# Active calls
twilio_calls_active

# Call rate (per minute)
rate(twilio_calls_total[1m])

# Average latency
histogram_quantile(0.95, rate(twilio_audio_latency_ms_bucket[5m]))

# Call duration percentiles
histogram_quantile(0.50, rate(twilio_call_duration_seconds_bucket[1h]))
```

## Advanced Configuration

### Custom Greeting

Edit `twilio_integration.py`, line ~450:

```python
twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">
        Welcome to Restaurant Name! I'm Concya, your reservation assistant.
    </Say>
    <Connect>
        <Stream url="{stream_url}" />
    </Connect>
</Response>"""
```

Available voices: [Twilio Voice List](https://www.twilio.com/docs/voice/twiml/say#voice)

### Audio Quality Settings

In `twilio_integration.py`:

```python
# Increase buffer for better quality (more latency)
AUDIO_CHUNK_DURATION_MS = 40  # Default: 20

# Adjust resampling method
# In resample_audio() function, change:
resampled = signal.resample(audio_array, num_samples)
# To higher quality:
resampled = signal.resample_poly(audio_array, target_rate, orig_rate)
```

### Call Recording

Enable in Twilio Console:
1. Phone Numbers → Your Number → Voice
2. **Call Recording**: Enable
3. **Record**: Record from Answer

Recordings saved in Twilio Console → Monitor → Logs → Recordings.

## Cost Estimation

**Twilio Voice Costs** (US, as of 2024):
- Phone number: $1.15/month
- Inbound calls: $0.0085/min
- Outbound calls (if needed): $0.0130/min

**Example Monthly Cost:**
- 100 calls/month × 3 min average = 300 minutes
- Cost: $1.15 + (300 × $0.0085) = $3.70/month

**OpenAI API Costs:**
- STT: Included in Whisper (local)
- LLM (GPT-4o-mini): $0.15/1M input tokens, $0.60/1M output
- TTS: $15/1M characters

**RunPod Costs:**
- L40S GPU: ~$0.80/hour
- 24/7 operation: ~$576/month

## Security Considerations

1. **Validate Twilio Requests** (Optional):
   ```python
   from twilio.request_validator import RequestValidator
   validator = RequestValidator(TWILIO_AUTH_TOKEN)
   # Validate signature in webhook
   ```

2. **Rate Limiting**: Implement to prevent abuse
3. **HTTPS Only**: Never use HTTP in production
4. **Environment Variables**: Never commit credentials to git
5. **Call Limits**: Set max concurrent calls if needed

## Testing with ngrok (Local Development)

For local testing before deploying to RunPod:

```bash
# Terminal 1: Start Concya
python app.py

# Terminal 2: Start ngrok
ngrok http 8000

# Copy ngrok HTTPS URL (e.g., https://abc123.ngrok.io)
# Update Twilio webhook to: https://abc123.ngrok.io/twilio/voice
```

**Note**: ngrok URLs change on restart. Use paid ngrok for static URLs.

## Support

- **Twilio Docs**: [twilio.com/docs/voice](https://www.twilio.com/docs/voice)
- **Twilio Support**: Open ticket in Console
- **Concya Issues**: Check server logs and `/metrics`

## Next Steps

1. ✅ Configure production webhooks
2. ✅ Test with real phone calls
3. ✅ Monitor metrics and latency
4. ✅ Customize greeting and prompts
5. ✅ Set up call recording (optional)
6. ✅ Implement call analytics dashboard

Enjoy your voice-enabled AI reservation assistant! 📞🤖

