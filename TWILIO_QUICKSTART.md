# Twilio Voice - Quick Start Guide

Get your AI phone assistant running in 10 minutes!

## 1. Install Dependencies

```bash
pip install twilio pydub scipy soundfile
```

**System dependencies:**
```bash
# macOS
brew install ffmpeg

# Linux
sudo apt-get install ffmpeg libsndfile1
```

## 2. Set Environment Variables

```bash
export TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export TWILIO_AUTH_TOKEN="your_auth_token"
export TWILIO_PHONE_NUMBER="+1234567890"
export PUBLIC_WEBHOOK_URL="https://your-runpod-id.proxy.runpod.net"
export OPENAI_API_KEY="sk-..."
```

## 3. Start Server

```bash
python app.py
```

Expected output:
```
✅ Twilio Voice integration loaded
INFO: Uvicorn running on http://0.0.0.0:8000
```

## 4. Configure Twilio Webhook

1. Go to [Twilio Console](https://console.twilio.com)
2. **Phone Numbers** → Select your number
3. **Voice Configuration** → **A CALL COMES IN**:
   ```
   https://your-url.com/twilio/voice
   ```
4. Method: **POST**
5. **Save**

## 5. Test It!

Call your Twilio number from any phone:

**You hear:** "Hi, this is Concya, your AI reservation assistant!"

**You say:** "I need a table for 4 tomorrow at 7pm"

**AI responds:** "Perfect! I've reserved a table for 4..."

## Verify It's Working

### Check health endpoint:
```bash
curl https://your-url.com/twilio/health
```

### Monitor logs:
```
📞 [TWILIO] Incoming call
🔌 [TWILIO-WS] Media Stream connected
📝 [STT] Transcription: 'I need a table...'
🤔 [LLM] Processing...
💬 [LLM] Reply: 'Perfect! I've reserved...'
🔊 [TTS] Generating audio...
📤 [TWILIO] Streaming audio back
```

## Troubleshooting

**No audio?**
- Check ffmpeg is installed: `ffmpeg -version`
- Verify environment variables are set

**Call drops?**
- Check webhook URL is HTTPS (not HTTP)
- Verify PUBLIC_WEBHOOK_URL matches your server

**High latency?**
- Use faster Whisper model: `WHISPER_MODEL=base`
- Check `/metrics` for timing data

## Costs

- Twilio phone: $1.15/month
- Calls: $0.0085/minute
- **100 calls × 3 min = $3.70/month**

## Next Steps

See [TWILIO_SETUP.md](TWILIO_SETUP.md) for:
- Detailed configuration
- Advanced features
- Production deployment
- Monitoring setup

**Ready for production!** 🚀📞

