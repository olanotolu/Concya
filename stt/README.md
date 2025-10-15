# Concya Terminal Client

A Python-based terminal client for real-time conversational AI with Concya. Streams audio from your microphone to the server for speech-to-text, processes responses with GPT-4o-mini, and plays back text-to-speech audio.

## Features

- 🎤 **Real-time Speech Recognition** - Streams audio to server via WebSocket
- 🤖 **AI Conversation** - Natural language understanding with GPT-4o-mini
- 🔊 **Text-to-Speech** - Plays AI responses through your speakers
- 🎨 **Colored Terminal Output** - Visual feedback for conversation states
- ⚡ **Low Latency** - Optimized for real-time interaction

## Installation

### 1. Install Python Dependencies

```bash
cd stt
pip install -r requirements.txt
```

### 2. Install PyAudio (Platform-Specific)

#### macOS
```bash
brew install portaudio
pip install pyaudio
```

#### Ubuntu/Debian Linux
```bash
sudo apt-get install portaudio19-dev python3-pyaudio
pip install pyaudio
```

#### Windows
```bash
pip install pipwin
pipwin install pyaudio
```

### 3. Install Audio Playback Tools

#### macOS
Already included (`afplay`)

#### Linux
```bash
sudo apt-get install mpg123
```

#### Windows
Already included (PowerShell)

## Usage

### Basic Usage

Start the Concya server (in another terminal):
```bash
cd /Users/term_/Documents/Concya
python app.py
```

Run the terminal client:
```bash
cd stt
python client.py
```

### With Custom Server URL

```bash
python client.py --server http://your-server:8000
```

Or for RunPod deployment:
```bash
python client.py --server https://your-pod-id.proxy.runpod.net
```

### List Audio Devices

```bash
python client.py --list-devices
```

### Use Specific Microphone

```bash
python client.py --device 2
```

## How It Works

### Conversation Flow

1. **Listening** 👂 - Client records audio from microphone
2. **Transcribing** - Audio streams to server via WebSocket
3. **Thinking** 🤔 - Transcribed text sent to GPT-4o-mini
4. **Speaking** 🔊 - AI response converted to speech and played

### Visual States

- 🟢 **GREEN** - Your speech (user input)
- 🔵 **BLUE** - AI responses
- 🟡 **YELLOW** - System status messages
- 🔴 **RED** - Errors

### Keyboard Shortcuts

- `Ctrl+C` - Exit gracefully

## Troubleshooting

### PyAudio Installation Issues

**macOS Error: "portaudio.h not found"**
```bash
brew install portaudio
export CFLAGS="-I/opt/homebrew/include"
export LDFLAGS="-L/opt/homebrew/lib"
pip install pyaudio
```

**Linux Error: "portaudio.h: No such file"**
```bash
sudo apt-get install portaudio19-dev
pip install pyaudio
```

**Windows Error: "Microsoft Visual C++ required"**
```bash
pip install pipwin
pipwin install pyaudio
```

### Audio Device Issues

**List available devices:**
```bash
python client.py --list-devices
```

**Use specific device:**
```bash
python client.py --device 1
```

### Connection Issues

**Server not responding:**
- Ensure server is running: `python app.py`
- Check server URL is correct
- Verify firewall settings

**WebSocket connection failed:**
- Check if port 8000 is accessible
- For HTTPS servers, use `wss://` protocol
- Verify server has STT endpoint at `/asr`

### Audio Playback Issues

**No sound on Linux:**
```bash
# Install mpg123
sudo apt-get install mpg123

# Or use alternative
sudo apt-get install sox libsox-fmt-mp3
```

**No sound on macOS:**
- Check system sound settings
- Ensure volume is not muted
- Try: `afplay /System/Library/Sounds/Ping.aiff`

## Configuration

### Audio Settings

Edit `client.py` to adjust:
- `SAMPLE_RATE` - Default: 16000 Hz
- `CHUNK_SIZE` - Default: 200ms chunks
- Debounce timing - Default: 1.5 seconds

### Server Endpoints

The client uses these endpoints:
- `ws://server/asr` - WebSocket for STT streaming
- `POST /conversation` - LLM conversation
- `POST /speak` - TTS audio generation

## Example Session

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

[LISTENING] 🎤 Microphone active - speak now!
👤 You: Hi, I'd like to make a reservation for 4 people tomorrow at 7pm
[THINKING] 🤔 Processing with AI...
🤖 Concya: Perfect! I've reserved a table for 4 tomorrow at 7:00 PM. May I have your name for the reservation?
[SPEAKING] 🔊 Playing response...
[LISTENING] 👂 Listening...
👤 You: Yes, it's John Smith
[THINKING] 🤔 Processing with AI...
🤖 Concya: Wonderful, John! Your reservation for 4 people tomorrow at 7:00 PM is confirmed. We look forward to seeing you!
[SPEAKING] 🔊 Playing response...
```

## Development

### Running in Development Mode

```bash
# Terminal 1: Start server
python app.py

# Terminal 2: Run client
cd stt
python client.py
```

### Testing with Different Servers

```bash
# Local development
python client.py --server http://localhost:8000

# RunPod deployment
python client.py --server https://your-pod.proxy.runpod.net

# Custom deployment
python client.py --server https://your-domain.com
```

## Requirements

- Python 3.8+
- Working microphone
- Working speakers/headphones
- Internet connection (for server communication)
- Concya server running

## License

Part of the Concya project.

