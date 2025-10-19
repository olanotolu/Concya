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

# Import WhisperLiveKit
try:
    from whisper_live.client import WhisperLiveClient
    from whisper_live.server import TranscriptionServer
    WHISPER_AVAILABLE = True
    print("✅ WhisperLiveKit available")
except ImportError:
    WHISPER_AVAILABLE = False
    print("⚠️  WhisperLiveKit not available - using fallback")

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

            # Add to audio buffer for transcription
            self.audio_buffer.extend(pcm_data)

            # Keep buffer size manageable (last 3 seconds at 16kHz for better transcription)
            if len(self.audio_buffer) > 48000:  # 3 seconds at 16kHz
                self.audio_buffer = self.audio_buffer[-48000:]

        except Exception as e:
            logger.error(f"❌ Error processing audio chunk: {e}")

    async def send_transcription(self):
        """Send current transcription to Twilio"""
        try:
            # Check if we have enough audio data (at least 1 second at 16kHz)
            if len(self.audio_buffer) < 16000:  # 1 second at 16kHz
                return

            if WHISPER_AVAILABLE and whisper_client:
                try:
                    # Convert buffer to numpy array for Whisper
                    import numpy as np
                    audio_array = np.frombuffer(bytes(self.audio_buffer), dtype=np.int16)
                    audio_float = audio_array.astype(np.float32) / 32768.0

                    # Resample to 16kHz if needed (Whisper expects 16kHz)
                    import librosa
                    if len(audio_float) > 0:
                        audio_float = librosa.resample(audio_float, orig_sr=8000, target_sr=16000)

                    # Get transcription from WhisperLiveKit
                    result = await whisper_client.transcribe(audio_float)
                    transcription = result.get('text', '').strip()

                    if transcription and transcription != self.last_transcription:
                        self.last_transcription = transcription

                        # Send real transcription back to Twilio
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
                        logger.info(f"🎤 Real Whisper transcription: {transcription}")

                        # Clear buffer after successful transcription
                        self.audio_buffer.clear()

                except Exception as e:
                    logger.error(f"❌ WhisperLiveKit transcription error: {e}")
                    # Fall back to placeholder transcription
                    self._send_placeholder_transcription()
            else:
                # Send placeholder transcription
                self._send_placeholder_transcription()

        except Exception as e:
            logger.error(f"❌ Error in send_transcription: {e}")

    def _send_placeholder_transcription(self):
        """Send placeholder transcription when WhisperLiveKit is unavailable"""
        try:
            transcription = f"Transcription at {time.time():.1f}"

            if transcription != self.last_transcription:
                self.last_transcription = transcription

                response = {
                    "event": "transcription",
                    "streamSid": self.stream_sid,
                    "transcription": {
                        "text": transcription,
                        "confidence": 0.95,
                        "is_final": False
                    }
                }

                # Use asyncio to send JSON
                import asyncio
                asyncio.create_task(self.websocket.send_json(response))
                logger.info(f"📝 Sent placeholder transcription: {transcription}")

        except Exception as e:
            logger.error(f"❌ Error sending placeholder transcription: {e}")

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
    global whisper_client, WHISPER_AVAILABLE

    if WHISPER_AVAILABLE:
        try:
            logger.info("🚀 Initializing WhisperLiveKit...")
            # Initialize WhisperLive client for transcription
            whisper_client = WhisperLiveClient(
                host="localhost",
                port=9090,
                backend="faster_whisper",
                model_size="base",
                lang="en"
            )

            logger.info("✅ WhisperLiveKit client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize WhisperLiveKit: {e}")
            logger.warning("⚠️  Falling back to placeholder transcription")
            WHISPER_AVAILABLE = False
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
