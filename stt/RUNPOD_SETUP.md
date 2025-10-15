# RunPod Setup Guide for Concya

## ✅ Fixes Applied

The following issues have been resolved:
- ✅ CORS errors fixed - Frontend now uses full RunPod URLs
- ✅ LLM endpoint (`/conversation`) now accessible
- ✅ TTS endpoint (`/speak`) now accessible
- ✅ Docker image rebuilt and pushed: `olaoluwasubomi/concya:latest`

---

## 🚀 Deploy to RunPod

### Step 1: Update Your Pod

In your RunPod dashboard:

1. **Stop** your current pod: `mammoth_violet_firefly`
2. **Edit Template** or create a new pod with these settings:

**Container Image:**
```
olaoluwasubomi/concya:latest
```

**Environment Variables:**
```bash
WHISPER_MODEL=base
WHISPER_LANGUAGE=auto
ENABLE_DIARIZATION=false
TARGET_LANGUAGE=
OPENAI_API_KEY=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
```

**Note:** Diarization is disabled (`false`) because NeMo is not available in your current setup. This will reduce costs and improve performance.

**Container Disk:** 20 GB  
**GPU:** L40S (or any CUDA-compatible GPU)  
**Expose Ports:** 8000 (HTTP)

### Step 2: Start the Pod

After adding the environment variables, start your pod.

### Step 3: Access Your Service

Your RunPod will provide a URL like:
```
https://e6vvfmmklc6hzi-8000.proxy.runpod.net/
```

---

## 🧪 Test the Service

### Method 1: Web UI (Easiest)

1. **Open** `index.html` in your browser (locally or from RunPod URL)
2. **Click** the microphone button
3. **Speak** something like "Hello, I'd like to make a reservation"
4. **Watch** for:
   - ✅ Your speech transcribed (Speaker 1)
   - ✅ Concya's response (🤖 Concya badge)
   - ✅ Audio playback of the response

### Method 2: Test with french.wav

Upload `french.wav` to your RunPod instance and test transcription.

### Method 3: API Test

Test the endpoints directly:

```bash
# Test /conversation endpoint
curl -X POST https://e6vvfmmklc6hzi-8000.proxy.runpod.net/conversation \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello, I would like to make a reservation",
    "session_id": "test123",
    "language": "en"
  }'

# Test /speak endpoint
curl -X POST https://e6vvfmmklc6hzi-8000.proxy.runpod.net/speak \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello! I would be happy to help you with a reservation.",
    "voice": "alloy"
  }' \
  --output response.mp3
```

---

## 📊 Expected Behavior

### Before Fix (What You Saw)
```
❌ Access to fetch at 'file:///conversation' - CORS blocked
❌ LLM error: TypeError: Failed to fetch
```

### After Fix (What You Should See)
```
✅ Transcription: "Hello, what's going on"
✅ 🤖 Concya: "Hello! How can I assist you today?"
✅ [Audio plays automatically]
```

---

## 💰 Cost Optimization

Your current spend: **$0.86/hr** (~$20.64/day)

To reduce costs:
1. **Stop the pod** when not in use
2. Use **smaller GPU** (A4000 at $0.39/hr instead of L40S)
3. Set `WHISPER_MODEL=tiny` for faster/cheaper processing
4. **Disable diarization** (already done: `ENABLE_DIARIZATION=false`)

---

## 🐛 Troubleshooting

### Issue: Still getting CORS errors
- Make sure you're using the **latest** Docker image: `olaoluwasubomi/concya:latest`
- Restart your RunPod pod after updating

### Issue: LLM not responding
- Check RunPod logs for OpenAI API errors
- Verify `OPENAI_API_KEY` is set correctly
- Test API key: `curl https://api.openai.com/v1/models -H "Authorization: Bearer YOUR_KEY"`

### Issue: TTS not playing
- Check browser console for errors
- Ensure browser allows autoplay audio
- Try clicking the page first (browsers block autoplay until user interaction)

---

## 🎯 Next Steps

1. ✅ Deploy updated image to RunPod
2. ✅ Add OpenAI API key to environment variables
3. ✅ Test the conversation flow
4. Consider adding:
   - Custom system prompts for specific use cases
   - Session persistence (database)
   - User authentication
   - Voice selection UI
   - Conversation history display

---

**Your Image:** `olaoluwasubomi/concya:latest`  
**Current RunPod URL:** `https://e6vvfmmklc6hzi-8000.proxy.runpod.net/`  
**Status:** ✅ Ready to Deploy

