# Concya Terminal Client - Quick Start

Get up and running with the terminal client in 5 minutes!

## Prerequisites

- Python 3.8+
- Working microphone
- Working speakers/headphones

## Step 1: Install Dependencies

```bash
cd stt
pip install -r requirements.txt
```

### Platform-Specific Audio Setup

**macOS:**
```bash
brew install portaudio
pip install pyaudio
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install portaudio19-dev python3-pyaudio mpg123
pip install pyaudio
```

**Windows:**
```bash
pip install pipwin
pipwin install pyaudio
```

## Step 2: Start the Server

In a separate terminal:

```bash
cd /Users/term_/Documents/Concya
python app.py
```

Wait for:
```
✅ TranscriptionEngine ready!
INFO: Uvicorn running on http://0.0.0.0:8000
```

## Step 3: Test Connection (Optional)

```bash
python test_connection.py
```

Should show:
```
✓ Health Check: OK (HTTP 200)
✓ Metrics: OK (HTTP 200)
✓ All tests passed! Server is ready.
```

## Step 4: Run the Client

```bash
python client.py
```

You should see:
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

## Step 5: Start Talking!

Just speak naturally:

```
👤 You: Hi, I'd like to make a reservation for 4 people tomorrow at 7pm
[THINKING] 🤔 Processing with AI...
🤖 Concya: Perfect! I've reserved a table for 4 tomorrow at 7:00 PM. May I have your name for the reservation?
[SPEAKING] 🔊 Playing response...
[LISTENING] 👂 Listening...
```

## Troubleshooting

### "No module named 'pyaudio'"

Install PyAudio for your platform (see Step 1).

### "Connection refused"

Make sure the server is running:
```bash
python app.py
```

### "No audio devices found"

List available devices:
```bash
python client.py --list-devices
```

Then use specific device:
```bash
python client.py --device 1
```

### "Permission denied" (microphone)

Grant microphone permissions in System Preferences (macOS) or System Settings.

### No sound during TTS playback

**macOS:** Check system volume
**Linux:** Install mpg123: `sudo apt-get install mpg123`
**Windows:** Check audio drivers

## Advanced Usage

### Connect to Remote Server

```bash
python client.py --server https://your-pod.proxy.runpod.net
```

### Use Specific Microphone

```bash
python client.py --device 2
```

### Debug Mode

Check console output for detailed logs.

## Next Steps

- Read full documentation: [README.md](README.md)
- Customize audio settings in `client.py`
- Deploy to RunPod for production use

## Getting Help

If you encounter issues:

1. Check server logs in the terminal running `app.py`
2. Check client output for error messages
3. Run connection test: `python test_connection.py`
4. Verify audio devices: `python client.py --list-devices`

Enjoy your conversational AI! 🎉

