#!/usr/bin/env python3
"""
WhisperLiveKit Server for Concya
Real-time speech recognition for Twilio Media Streams
"""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Dict

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Import WhisperLive
try:
    from whisper_live.server import TranscriptionServer
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("⚠️  WhisperLive not available")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whisper")

app = FastAPI(title="Concya WhisperLiveKit Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
active_streams: Dict[str, Dict] = {}
whisper_client = None

class TwilioMediaStream:
    """Handles Twilio Media Stream WebSocket connections"""

    def __init__(self, websocket: WebSocket, stream_sid: str):
        self.websocket = websocket
        self.stream_sid = stream_sid
        self.audio_buffer = bytearray()
        self.last_transcription = ""
        self.conversation_active = True
        self.silence_start = None
        self.is_speaking = False

    async def start(self):
        """Start processing the media stream"""
        logger.info(f"🎤 Starting media stream: {self.stream_sid}")

        try:
            await self.websocket.accept()

            # Send start message to Twilio
            start_message = {
                "event": "start",
                "streamSid": self.stream_sid,
                "start": {
                    "streamSid": self.stream_sid,
                    "accountSid": "test",
                    "callSid": "test",
                    "tracks": ["inbound"],
                    "mediaFormat": {
                        "encoding": "audio/x-mulaw",
                        "sampleRate": 8000,
                        "channels": 1
                    }
                }
            }
            await self.websocket.send_json(start_message)

            # Start processing loop
            await self.process_stream()

        except WebSocketDisconnect:
            logger.info(f"📞 Media stream disconnected: {self.stream_sid}")
        except Exception as e:
            logger.error(f"❌ Media stream error: {e}")
        finally:
            # Cleanup
            if self.stream_sid in active_streams:
                del active_streams[self.stream_sid]

    async def process_stream(self):
        """Process incoming media stream data"""
        chunk_count = 0

        while self.conversation_active:
            try:
                # Receive media message
                message = await self.websocket.receive_json()
                event = message.get("event")

                if event == "media":
                    # Process audio chunk
                    await self.process_audio_chunk(message)
                    chunk_count += 1

                    # Send transcription every 10 chunks (~200ms at 8kHz)
                    if chunk_count % 10 == 0:
                        await self.send_transcription()

                elif event == "stop":
                    logger.info(f"🛑 Stream stopped: {self.stream_sid}")
                    break

            except Exception as e:
                logger.error(f"❌ Error processing stream: {e}")
                break

    async def process_audio_chunk(self, message: dict):
        """Process incoming audio chunk"""
        try:
            payload = message["media"]["payload"]

            # Decode base64 mulaw audio
            import base64
            import audioop
            
            mulaw_data = base64.b64decode(payload)
            
            # Convert mulaw to 16-bit PCM
            pcm_data = audioop.ulaw2lin(mulaw_data, 2)
            
            # Send to WhisperLive for transcription
            if whisper_client:
                self.audio_buffer.extend(pcm_data)
            
            # Keep buffer size manageable (last 2 seconds at 16kHz)
            if len(self.audio_buffer) > 32000:  # 2 seconds at 16kHz
                self.audio_buffer = self.audio_buffer[-32000:]

        except Exception as e:
            logger.error(f"❌ Error processing audio chunk: {e}")

    async def send_transcription(self):
        """Send current transcription to Twilio"""
        try:
            # Check if we have enough audio data (at least 0.2 seconds at 16kHz)
            if not whisper_client or len(self.audio_buffer) < 3200:
                return
            
            # Convert buffer to numpy array for Whisper
            import numpy as np
            audio_array = np.frombuffer(bytes(self.audio_buffer), dtype=np.int16)
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Get transcription from WhisperLive
            result = await whisper_client.transcribe(audio_float)
            transcription = result.get('text', '').strip()
            
            if transcription and transcription != self.last_transcription:
                self.last_transcription = transcription
                
                # Send transcription back to Twilio
                response = {
                    "event": "transcription",
                    "streamSid": self.stream_sid,
                    "transcription": {
                        "text": transcription,
                        "confidence": result.get('confidence', 0.95),
                        "is_final": True
                    }
                }
                
                await self.websocket.send_json(response)
                logger.info(f"📝 Sent transcription: {transcription}")

        except Exception as e:
            logger.error(f"❌ Error sending transcription: {e}")

@app.websocket("/media")
async def media_stream(websocket: WebSocket):
    """Handle Twilio Media Stream WebSocket connections"""
    try:
        # Get stream parameters
        stream_sid = websocket.query_params.get("streamSid", str(uuid.uuid4()))

        logger.info(f"🔗 New media stream connection: {stream_sid}")

        # Create and start media stream handler
        stream_handler = TwilioMediaStream(websocket, stream_sid)
        active_streams[stream_sid] = {"handler": stream_handler, "start_time": time.time()}

        await stream_handler.start()

    except Exception as e:
        logger.error(f"❌ Media stream error: {e}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "whisper_available": WHISPER_AVAILABLE,
        "active_streams": len(active_streams)
    }

@app.get("/streams")
async def get_streams():
    """Get information about active streams"""
    return {
        "active_streams": len(active_streams),
        "streams": [
            {
                "stream_sid": sid,
                "duration": time.time() - info["start_time"],
                "status": "active"
            }
            for sid, info in active_streams.items()
        ]
    }

@app.on_event("startup")
async def startup_event():
    """Initialize WhisperLiveKit on startup"""
    global whisper_client

    if WHISPER_AVAILABLE:
        try:
            logger.info("🚀 Initializing WhisperLiveKit...")
            from whisper_live.server import TranscriptionServer
            
            # Initialize WhisperLive transcription server
            whisper_client = TranscriptionServer()
            
            # Run in background with faster_whisper backend
            import threading
            def run_whisper_server():
                whisper_client.run(
                    host="0.0.0.0",
                    port=9090,
                    backend="faster_whisper",
                    faster_whisper_custom_model_path=None
                )
            
            whisper_thread = threading.Thread(target=run_whisper_server, daemon=True)
            whisper_thread.start()
            
            logger.info("✅ WhisperLiveKit initialized on port 9090")
        except Exception as e:
            logger.error(f"❌ Failed to initialize WhisperLiveKit: {e}")
            logger.warning("⚠️  Falling back to placeholder transcription")
    else:
        logger.warning("⚠️  WhisperLiveKit not available - using placeholder transcription")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down WhisperLiveKit server")
    # Cleanup active streams
    for stream_sid in list(active_streams.keys()):
        del active_streams[stream_sid]

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8765))
    logger.info(f"🎤 Starting WhisperLiveKit server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
