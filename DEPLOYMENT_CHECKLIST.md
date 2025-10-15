# Concya Deployment Checklist

Complete checklist for deploying Concya with Twilio Voice integration to RunPod.

## ✅ Pre-Deployment

### 1. Local Verification
- [ ] Test server locally: `python app.py`
- [ ] Verify all dependencies install: `pip install -r requirements.txt`
- [ ] Check for hardcoded secrets (should be NONE)
- [ ] Confirm Twilio integration loads: Check logs for "✅ Twilio Voice integration loaded"

### 2. Git Repository
- [ ] All changes committed
- [ ] Pushed to GitHub: `git push origin master`
- [ ] No secrets in git history
- [ ] `.gitignore` configured properly

### 3. API Keys Ready
- [ ] OpenAI API Key (for LLM and TTS)
- [ ] Twilio Account SID
- [ ] Twilio Auth Token
- [ ] Twilio Phone Number
- [ ] Supabase URL (optional)
- [ ] Supabase Anon Key (optional)

## 🚀 Docker Build & Push

### 1. Build Image
```bash
./build-and-push.sh
```

Expected output:
- ✅ Image built successfully
- ✅ Pushed to `olaoluwasubomi/concya:latest`

### 2. Verify Image
```bash
docker images | grep concya
```

Should show: `olaoluwasubomi/concya    latest`

## ☁️ RunPod Deployment

### 1. Create/Edit Pod

**Template:**
- Name: Concya AI Voice Assistant
- Image: `olaoluwasubomi/concya:latest`
- GPU: L40S (or similar NVIDIA GPU)
- Memory: 16GB minimum
- Storage: 20GB minimum
- Port: 8000 (HTTP)

### 2. Environment Variables

**Required:**
```bash
OPENAI_API_KEY=sk-...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1...
PUBLIC_WEBHOOK_URL=https://YOUR-POD-ID.proxy.runpod.net
```

**Optional:**
```bash
WHISPER_MODEL=base
ENABLE_DIARIZATION=true
SUPABASE_URL=https://...
SUPABASE_ANON_KEY=...
```

### 3. Start Pod
- [ ] Click "Deploy"
- [ ] Wait for pod to start (2-5 minutes)
- [ ] Note your pod URL: `https://YOUR-POD-ID.proxy.runpod.net`

## 🔍 Post-Deployment Verification

### 1. Check Server Health
```bash
curl https://YOUR-POD-ID.proxy.runpod.net/health
```

Expected:
```json
{
  "status": "healthy",
  "stt": "ready",
  "llm": "ready", 
  "tts": "ready"
}
```

### 2. Check Twilio Integration
```bash
curl https://YOUR-POD-ID.proxy.runpod.net/twilio/health
```

Expected:
```json
{
  "status": "healthy",
  "active_calls": 0,
  "config": {
    "twilio_configured": true,
    "webhook_url": "https://YOUR-POD-ID.proxy.runpod.net"
  }
}
```

### 3. View Root Page
Open in browser: `https://YOUR-POD-ID.proxy.runpod.net/`

Should see:
- ✅ Server is running!
- 📞 Twilio Voice Integration info
- 🔌 API Endpoints
- 📋 Setup Instructions

### 4. Check Logs
In RunPod pod logs, verify:
```
INFO:__main__:🚀 Starting Concya - Unified STT + LLM + TTS Service
INFO:__main__:📦 Whisper Model: base
INFO:__main__:👥 Diarization: True
INFO:app:✅ Twilio Voice integration loaded
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## 📞 Twilio Configuration

### 1. Log into Twilio Console
Go to: [console.twilio.com](https://console.twilio.com)

### 2. Configure Phone Number
- Navigate to: **Phone Numbers → Manage → Active Numbers**
- Click on your Twilio number
- Scroll to **Voice Configuration**

### 3. Set Webhook URL
**A CALL COMES IN:**
```
https://YOUR-POD-ID.proxy.runpod.net/twilio/voice
```
- Method: **HTTP POST**
- Save configuration

### 4. (Optional) Set Status Callback
```
https://YOUR-POD-ID.proxy.runpod.net/twilio/status
```
- Method: **HTTP POST**

## 🧪 End-to-End Testing

### 1. Test Webhook (Manual)
```bash
curl -X POST https://YOUR-POD-ID.proxy.runpod.net/twilio/voice \
  -d "CallSid=TEST123" \
  -d "From=+15551234567" \
  -d "To=+15559876543"
```

Expected: TwiML XML response with `<Say>` and `<Stream>` tags

### 2. Make Test Call
- [ ] Call your Twilio number from your phone
- [ ] Hear greeting: "Hi, this is Concya..."
- [ ] Speak: "I need a table for 4 tomorrow at 7pm"
- [ ] Hear AI response
- [ ] Verify natural conversation flow

### 3. Monitor Logs
Watch RunPod logs during call:
```
📞 [TWILIO] Incoming call: CAxxxxx
🔌 [TWILIO-WS] Media Stream connected
📝 [STT] Transcription: 'I need a table...'
🤔 [LLM] Processing...
💬 [LLM] Reply: 'Perfect! I've reserved...'
🔊 [TTS] Generating audio...
📤 [TWILIO] Streaming audio back
```

### 4. Check Metrics
```bash
curl https://YOUR-POD-ID.proxy.runpod.net/metrics | grep twilio
```

Should show:
- `twilio_calls_total`
- `twilio_calls_active`
- `twilio_call_duration_seconds`
- `twilio_audio_latency_ms`

## 🔧 Troubleshooting

### Issue: Pod Won't Start
- [ ] Check environment variables are set
- [ ] Verify OpenAI API key is valid
- [ ] Check RunPod logs for errors
- [ ] Ensure GPU is available

### Issue: Health Check Fails
- [ ] Wait 2-3 minutes for Whisper model download
- [ ] Check logs for initialization errors
- [ ] Verify port 8000 is exposed
- [ ] Test with curl from another server

### Issue: Twilio Webhook Error
- [ ] Verify webhook URL is HTTPS (not HTTP)
- [ ] Check `PUBLIC_WEBHOOK_URL` matches actual pod URL
- [ ] Test webhook with curl
- [ ] Check Twilio Console → Monitor → Logs

### Issue: No Audio on Call
- [ ] Verify environment variables are set
- [ ] Check server logs for STT/TTS errors
- [ ] Test `/asr` endpoint separately
- [ ] Ensure OpenAI API key has credits

### Issue: High Latency
- [ ] Use `WHISPER_MODEL=base` (not large)
- [ ] Check `/metrics` for timing data
- [ ] Verify GPU is being used
- [ ] Consider deploying closer to Twilio servers

## 📊 Monitoring

### Prometheus Metrics
Access: `https://YOUR-POD-ID.proxy.runpod.net/metrics`

**Key Metrics:**
- `twilio_calls_total` - Total calls
- `twilio_calls_active` - Active calls
- `twilio_audio_latency_ms` - Round-trip latency
- `stt_latency_ms` - STT processing time
- `llm_latency_ms` - LLM response time
- `tts_latency_ms` - TTS generation time

### Health Checks
Schedule regular checks:
```bash
*/5 * * * * curl https://YOUR-POD-ID.proxy.runpod.net/health
```

## 📱 Production Considerations

### 1. Scaling
- [ ] Monitor `twilio_calls_active` metric
- [ ] Consider multiple pods for high volume
- [ ] Set up load balancing if needed

### 2. Monitoring
- [ ] Set up Grafana dashboard
- [ ] Configure alerts for errors
- [ ] Monitor costs (RunPod + OpenAI + Twilio)

### 3. Backup
- [ ] Configure Supabase for persistent storage
- [ ] Set up database backups
- [ ] Document recovery procedures

### 4. Security
- [ ] Rotate API keys regularly
- [ ] Use Twilio webhook validation (optional)
- [ ] Monitor for unusual call patterns
- [ ] Set up rate limiting

## ✨ Success Criteria

- [x] Docker image built and pushed
- [x] RunPod pod running without errors
- [x] Health checks passing
- [x] Twilio webhook configured
- [x] Test call works end-to-end
- [x] Metrics are being collected
- [x] Logs show successful processing

## 🎉 You're Live!

Your Concya AI Voice Assistant is now deployed and ready to take calls!

**Next Steps:**
1. Share your Twilio number with customers
2. Monitor metrics and logs
3. Adjust prompts and settings as needed
4. Scale as needed

---

**Support:**
- TWILIO_SETUP.md - Detailed setup guide
- TWILIO_QUICKSTART.md - Quick reference
- GitHub Issues - Report problems

