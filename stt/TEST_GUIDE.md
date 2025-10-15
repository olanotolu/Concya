# Testing Concya Terminal Client

Quick guide to test the complete Concya setup locally.

## Prerequisites

Ensure you have:
- Python 3.8+ with `concya` conda environment activated
- OpenAI API key set in environment
- All dependencies installed

## Step-by-Step Testing

### 1. Verify Environment

```bash
# Activate conda environment
conda activate concya

# Check Python version
python --version  # Should be 3.8+

# Verify OpenAI API key is set
echo $OPENAI_API_KEY  # Should show your key
```

### 2. Install Terminal Client Dependencies

```bash
cd /Users/term_/Documents/Concya/stt
pip install -r requirements.txt
```

**Platform-specific PyAudio installation:**

**macOS:**
```bash
brew install portaudio
pip install pyaudio
```

**Linux:**
```bash
sudo apt-get install portaudio19-dev python3-pyaudio mpg123
pip install pyaudio
```

### 3. Start the Server

In Terminal 1:

```bash
cd /Users/term_/Documents/Concya
export OPENAI_API_KEY="your-key-here"  # If not already set
python app.py
```

**Expected output:**
```
INFO:__main__:🚀 Starting Concya - Unified STT + LLM + TTS Service
INFO:__main__:📦 Whisper Model: base
INFO:__main__:🌍 Language: auto
INFO:__main__:👥 Diarization: True
INFO:app:🔥 Initializing TranscriptionEngine...
INFO:app:✅ TranscriptionEngine ready without diarization!
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 4. Test Server Connection

In Terminal 2:

```bash
cd /Users/term_/Documents/Concya/stt
python test_connection.py
```

**Expected output:**
```
Testing Concya Server: http://localhost:8000

✓ Health Check: OK (HTTP 200)
✓ Metrics: OK (HTTP 200)

✓ All tests passed! Server is ready.
```

### 5. List Audio Devices (Optional)

```bash
python client.py --list-devices
```

**Example output:**
```
Available Audio Devices:
  [0] MacBook Air Microphone
  [1] External USB Microphone
  [2] AirPods Pro
```

### 6. Run the Terminal Client

```bash
python client.py
```

**Expected output:**
```
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🎙️  Concya Terminal Client - Conversational AI 🤖      ║
║                                                           ║
║   Server: http://localhost:8000                           ║
║   Session: terminal_1729012345                            ║
║                                                           ║
║   Press Ctrl+C to exit                                    ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝

[LISTENING] Connecting to ws://localhost:8000/asr...
[LISTENING] Connected! Config: {'type': 'config', 'useAudioWorklet': False}
[LISTENING] 🎤 Microphone active - speak now!
```

### 7. Test Conversation

Speak into your microphone:

**Example conversation:**

```
[LISTENING] 🎤 Microphone active - speak now!
Listening: Hi I'd like to make a reservation...

👤 You: Hi I'd like to make a reservation for 4 people tomorrow at 7pm

[THINKING] 🤔 Processing with AI...

🤖 Concya: Perfect! I've reserved a table for 4 tomorrow at 7:00 PM. May I have your name for the reservation?

[SPEAKING] 🔊 Playing response...
[LISTENING] 👂 Listening...

👤 You: Yes it's John Smith

[THINKING] 🤔 Processing with AI...

🤖 Concya: Wonderful, John! Your reservation for 4 people tomorrow at 7:00 PM is confirmed. We look forward to seeing you!

[SPEAKING] 🔊 Playing response...
```

### 8. Exit Gracefully

Press `Ctrl+C` to exit:

```
^C
[LISTENING] Shutting down...
[LISTENING] Goodbye! 👋
```

## Troubleshooting

### Server Won't Start

**Error: `ModuleNotFoundError: No module named 'supabase'`**
```bash
pip install supabase>=2.0.0
```

**Error: `ModuleNotFoundError: No module named 'whisperlivekit'`**
```bash
pip install whisperlivekit
```

**Error: `Duplicated timeseries in CollectorRegistry`**
- This should be fixed with the metrics.py refactoring
- If it persists, restart the server

### Client Connection Issues

**Error: `Connection refused`**
- Ensure server is running in Terminal 1
- Check server is on http://localhost:8000
- Verify firewall settings

**Error: `No module named 'pyaudio'`**
- Follow platform-specific PyAudio installation above
- On macOS: `brew install portaudio && pip install pyaudio`

### Audio Issues

**No microphone input:**
- Check system microphone permissions
- List devices: `python client.py --list-devices`
- Use specific device: `python client.py --device 1`

**No TTS playback:**
- **macOS**: Check system volume, `afplay` should work
- **Linux**: Install mpg123: `sudo apt-get install mpg123`
- **Windows**: Check audio drivers

**Choppy audio or cutoff speech:**
- Adjust `CHUNK_SIZE` in client.py (default: 200ms)
- Check network latency to server
- Ensure stable microphone connection

### LLM/TTS Errors

**Error: `TTS error: 500`**
- Check OPENAI_API_KEY is set correctly
- Verify API key has credits
- Check server logs for detailed error

**Error: `LLM request timed out`**
- Default timeout is 30 seconds
- Check internet connection
- Verify OpenAI API status

## Performance Tips

1. **Use a good microphone** - Better audio = better transcription
2. **Speak clearly** - Pause between sentences for natural flow
3. **Check latency** - Watch server logs for timing metrics
4. **Monitor metrics** - Visit http://localhost:8000/metrics

## Next Steps

Once testing is successful:

1. Deploy to RunPod for production use
2. Connect terminal client to RunPod URL
3. Integrate with your restaurant booking system
4. Customize LLM prompts for your use case

## Monitoring

While the system is running, you can:

**Check server health:**
```bash
curl http://localhost:8000/health
```

**View Prometheus metrics:**
```bash
curl http://localhost:8000/metrics
```

**Monitor server logs:**
Watch Terminal 1 for real-time logs with emoji indicators:
- 🎤 STT events
- 🤖 LLM processing
- 🔊 TTS generation
- ✅ Success
- ❌ Errors

Enjoy your conversational AI! 🎉

