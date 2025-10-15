# WhisperLiveKit STT Service

Real-time speech-to-text with speaker diarization, powered by WhisperLiveKit on RunPod L40S.

## Features

✅ **Real-time transcription** with SimulStreaming (ultra-low latency)  
✅ **Speaker diarization** using Sortformer (identifies who's speaking)  
✅ **Multi-language support** (auto-detect or specify)  
✅ **Translation** to 200+ languages (optional)  
✅ **Conversational AI** with OpenAI GPT-4o-mini (auto-responds to transcriptions)  
✅ **Text-to-Speech** with OpenAI TTS (natural voice responses)  
✅ **Web UI** with microphone support  
✅ **GPU-optimized** for RunPod L40S  

---

## 🚀 Quick Start on RunPod

### 1. Deploy to RunPod

```bash
# Build Docker image
docker build -t whisperlivekit-stt .

# Push to Docker Hub (or RunPod's registry)
docker tag whisperlivekit-stt your-dockerhub-username/whisperlivekit-stt
docker push your-dockerhub-username/whisperlivekit-stt
```

### 2. RunPod Configuration

**Container Image:**
```
your-dockerhub-username/whisperlivekit-stt
```

**Container Disk:** 20 GB minimum  
**GPU:** L40S (recommended) or any CUDA-compatible GPU  
**Expose HTTP Ports:** `8000`  
**Expose TCP Ports:** `8000`

**Environment Variables:**
```bash
WHISPER_MODEL=base              # Model: tiny, base, small, medium, large-v3
WHISPER_LANGUAGE=auto           # Language: auto, en, fr, es, etc.
ENABLE_DIARIZATION=true         # Enable speaker identification
TARGET_LANGUAGE=                # Leave empty or set to "es" for translation
OPENAI_API_KEY=                 # OpenAI API key for LLM + TTS features
```

### 3. Access Your Service

Once deployed, RunPod will give you a URL like:
```
https://your-pod-id-8000.proxy.runpod.net
```

**Open in browser:** Visit the URL to use the web UI  
**WebSocket endpoint:** `wss://your-pod-id-8000.proxy.runpod.net/asr`

---

## 📊 Model Options

| Model | VRAM | Speed | Accuracy | Best For |
|-------|------|-------|----------|----------|
| `tiny` | ~1GB | Fastest | Basic | Quick tests |
| `base` | ~1GB | Fast | Good | **Real-time (recommended)** |
| `small` | ~2GB | Medium | Better | Quality + speed balance |
| `medium` | ~5GB | Slow | High | High quality |
| `large-v3` | ~10GB | Slowest | Excellent | Maximum accuracy |

---

## 🎯 Usage Examples

### Web UI
1. Open the RunPod URL in your browser
2. Click the microphone button
3. Start speaking
4. Watch real-time transcription with speaker labels!

### Custom WebSocket Client

```javascript
const ws = new WebSocket('wss://your-pod-id-8000.proxy.runpod.net/asr');

ws.onopen = () => {
    console.log('Connected!');
    // Send audio as WebM chunks from MediaRecorder
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'config') {
        console.log('Server config:', data);
    } else {
        console.log('Transcription:', data);
        // data.lines contains speaker-separated text
        // data.buffer_transcription contains unvalidated text
    }
};
```

---

## 🔧 Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `WHISPER_MODEL` | `base` | Whisper model size |
| `WHISPER_LANGUAGE` | `auto` | Source language (auto-detect or ISO code) |
| `ENABLE_DIARIZATION` | `true` | Enable speaker identification |
| `TARGET_LANGUAGE` | `""` | Target language for translation (e.g., `es`) |
| `OPENAI_API_KEY` | `""` | OpenAI API key for LLM + TTS |

---

## 🐛 Troubleshooting

### Issue: "No audio detected"
- Ensure microphone permissions are granted in browser
- Check browser console for errors
- Try a different browser (Chrome/Edge recommended)

### Issue: "Connection failed"
- Verify RunPod pod is running
- Check that port 8000 is exposed
- Use `wss://` (not `ws://`) for RunPod URLs

### Issue: "Model loading slow"
- First startup downloads the model (~1-2 minutes)
- Subsequent startups are faster
- Consider using smaller model for faster loading

### Issue: "Diarization not working"
- Diarization requires NeMo installation (included in requirements)
- Check logs for NeMo loading errors
- Disable with `ENABLE_DIARIZATION=false` if needed

---

## 📝 API Response Format

```json
{
  "status": "active_transcription",
  "lines": [
    {
      "speaker": 1,
      "text": "Hello, how are you?",
      "start": "00:00:00",
      "end": "00:00:02",
      "detected_language": "en"
    },
    {
      "speaker": 2,
      "text": "I'm doing great, thanks!",
      "start": "00:00:03",
      "end": "00:00:05"
    }
  ],
  "buffer_transcription": "And you?",
  "buffer_diarization": "",
  "remaining_time_transcription": 0.5,
  "remaining_time_diarization": 0.2
}
```

---

## 🎓 Advanced Configuration

### Disable Diarization (Faster)
```bash
ENABLE_DIARIZATION=false
```

### Enable Translation to French
```bash
TARGET_LANGUAGE=fr
```

### Use Large Model for Maximum Accuracy
```bash
WHISPER_MODEL=large-v3
```

### English-Only Mode (Faster)
```bash
WHISPER_MODEL=base.en
WHISPER_LANGUAGE=en
```

---

## 📚 Credits

Built with:
- [WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit) - Real-time STT framework
- [SimulStreaming](https://github.com/ufalSimulStreaming) - Ultra-low latency transcription
- [Sortformer](https://github.com/NVIDIA/NeMo) - Speaker diarization
- [NLLB](https://huggingface.co/facebook/nllb-200-distilled-600M) - Translation
- [OpenAI](https://openai.com) - GPT-4o-mini LLM and TTS-1 voice synthesis

---

## 📄 License

MIT License - See WhisperLiveKit repository for details

