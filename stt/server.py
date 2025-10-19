#!/usr/bin/env python3
"""
WhisperLiveKit Server for Concya
Real-time speech recognition for Twilio Media Streams
"""

import os
import json
import base64
import asyncio
import audioop
import numpy as np
from scipy.signal import resample_poly

from fastapi import FastAPI, WebSocket
from whisperlivekit import TranscriptionEngine, AudioProcessor

PUBLIC_HOST = os.getenv("PUBLIC_HOST", "your.domain.com")  # for TwiML

app = FastAPI()
engine = TranscriptionEngine(model="small", diarization=False, language="en")  # tweak as needed

# Configure logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whisper")

@app.websocket("/media")
async def twilio_media_stream(ws: WebSocket):
    """Handle Twilio Media Stream WebSocket connections"""
    await ws.accept()
    processor = AudioProcessor(transcription_engine=engine)
    results_gen = await processor.create_tasks()

    async def handle_results():
        async for result in results_gen:
            # Forward transcription results to your LLM/agent bus
            # result includes partial/final transcripts
            logger.info(f"🎤 STT: {result}")

    asyncio.create_task(handle_results())

    try:
        while True:
            # Twilio sends TEXT frames with JSON {event, media, ...}
            msg = await ws.receive_text()
            data = json.loads(msg)

            event = data.get("event")
            if event == "media":
                b64 = data["media"]["payload"]
                mulaw = base64.b64decode(b64)                 # μ-law @ 8k
                lin8k = audioop.ulaw2lin(mulaw, 2)            # -> int16 PCM @ 8k
                s8 = np.frombuffer(lin8k, dtype=np.int16)
                s16 = resample_poly(s8, up=2, down=1)         # -> 16k
                await processor.process_audio(s16.astype(np.int16).tobytes())
            elif event == "stop":
                break
            # handle "start"/"connected"/DTMF if needed
    finally:
        await processor.cleanup()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "whisper_available": True,
        "active_streams": 0  # Could track this if needed
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8765))
    logger.info(f"🎤 Starting WhisperLiveKit server on port {port}")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)
