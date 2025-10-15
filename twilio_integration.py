"""
Twilio Voice Integration for Concya
Enables phone-based interaction with AI reservation assistant

Architecture:
    Caller → Twilio → TwiML → Media Stream WebSocket
    → Audio Bridge (8kHz µ-law ↔ 16kHz PCM)
    → /asr WebSocket → STT → /conversation (LLM) → /speak (TTS)
    → Audio Bridge (MP3 → 8kHz µ-law) → Back to Twilio
"""

import asyncio
import base64
import audioop
import json
import logging
import os
import time
import io
from typing import Dict, Optional
from datetime import datetime

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Response
from pydub import AudioSegment
import soundfile as sf
from scipy import signal
import requests

# Import metrics
from metrics import (
    twilio_calls_total,
    twilio_calls_active,
    twilio_call_duration_seconds,
    twilio_audio_latency_ms
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
PUBLIC_WEBHOOK_URL = os.getenv("PUBLIC_WEBHOOK_URL", "https://your-server.com")

# Audio configuration
TWILIO_SAMPLE_RATE = 8000  # Twilio uses 8kHz
CONCYA_SAMPLE_RATE = 16000  # Concya STT expects 16kHz
AUDIO_CHUNK_DURATION_MS = 20  # Twilio sends 20ms chunks

# Session management
active_calls: Dict[str, 'CallSession'] = {}
CALL_TIMEOUT_SECONDS = 600  # 10 minutes max call duration

router = APIRouter()

# ═══════════════════════════════════════════════════════════════
# AUDIO CONVERSION UTILITIES
# ═══════════════════════════════════════════════════════════════

def decode_mulaw_base64(base64_audio: str) -> bytes:
    """
    Decode base64-encoded µ-law audio from Twilio
    
    Args:
        base64_audio: Base64-encoded µ-law audio string
        
    Returns:
        Raw µ-law audio bytes
    """
    try:
        return base64.b64decode(base64_audio)
    except Exception as e:
        logger.error(f"❌ [AUDIO] Failed to decode base64: {e}")
        return b''


def mulaw_to_pcm(mulaw_data: bytes) -> bytes:
    """
    Convert µ-law encoded audio to PCM
    
    Args:
        mulaw_data: µ-law encoded audio bytes
        
    Returns:
        PCM audio bytes (16-bit signed)
    """
    try:
        # Python's audioop.ulaw2lin converts µ-law to 16-bit PCM
        pcm_data = audioop.ulaw2lin(mulaw_data, 2)  # 2 = 16-bit
        return pcm_data
    except Exception as e:
        logger.error(f"❌ [AUDIO] µ-law to PCM conversion failed: {e}")
        return b''


def pcm_to_mulaw(pcm_data: bytes) -> bytes:
    """
    Convert PCM audio to µ-law encoding
    
    Args:
        pcm_data: PCM audio bytes (16-bit signed)
        
    Returns:
        µ-law encoded audio bytes
    """
    try:
        mulaw_data = audioop.lin2ulaw(pcm_data, 2)  # 2 = 16-bit
        return mulaw_data
    except Exception as e:
        logger.error(f"❌ [AUDIO] PCM to µ-law conversion failed: {e}")
        return b''


def resample_audio(audio_data: bytes, orig_rate: int, target_rate: int, channels: int = 1) -> bytes:
    """
    Resample audio from one sample rate to another
    
    Args:
        audio_data: Input audio bytes (16-bit PCM)
        orig_rate: Original sample rate (Hz)
        target_rate: Target sample rate (Hz)
        channels: Number of audio channels (default: 1 for mono)
        
    Returns:
        Resampled audio bytes
    """
    try:
        # Convert bytes to numpy array (int16)
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        
        # Reshape for multichannel if needed
        if channels > 1:
            audio_array = audio_array.reshape(-1, channels)
        
        # Calculate resampling ratio
        num_samples = int(len(audio_array) * target_rate / orig_rate)
        
        # Resample using scipy
        resampled = signal.resample(audio_array, num_samples)
        
        # Convert back to int16 and bytes
        resampled_int16 = resampled.astype(np.int16)
        return resampled_int16.tobytes()
        
    except Exception as e:
        logger.error(f"❌ [AUDIO] Resampling failed: {e}")
        return audio_data  # Return original if resampling fails


def mp3_to_mulaw_8khz(mp3_data: bytes) -> bytes:
    """
    Convert MP3 audio to 8kHz µ-law for Twilio
    
    Args:
        mp3_data: MP3 audio bytes from TTS
        
    Returns:
        Base64-encoded µ-law audio at 8kHz
    """
    try:
        # Decode MP3 using pydub
        audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
        
        # Convert to mono if stereo
        if audio.channels > 1:
            audio = audio.set_channels(1)
        
        # Resample to 8kHz
        audio = audio.set_frame_rate(TWILIO_SAMPLE_RATE)
        
        # Get raw PCM data (16-bit)
        pcm_data = audio.raw_data
        
        # Convert to µ-law
        mulaw_data = pcm_to_mulaw(pcm_data)
        
        # Encode as base64
        return base64.b64encode(mulaw_data).decode('utf-8')
        
    except Exception as e:
        logger.error(f"❌ [AUDIO] MP3 to µ-law conversion failed: {e}")
        return ''


def twilio_to_concya_audio(base64_mulaw: str) -> bytes:
    """
    Convert Twilio's base64 µ-law 8kHz audio to Concya's 16kHz PCM format
    
    Args:
        base64_mulaw: Base64-encoded µ-law audio from Twilio
        
    Returns:
        16kHz PCM audio bytes ready for /asr WebSocket
    """
    try:
        # Step 1: Decode base64
        mulaw_data = decode_mulaw_base64(base64_mulaw)
        if not mulaw_data:
            return b''
        
        # Step 2: Convert µ-law to PCM
        pcm_8khz = mulaw_to_pcm(mulaw_data)
        if not pcm_8khz:
            return b''
        
        # Step 3: Resample 8kHz → 16kHz
        pcm_16khz = resample_audio(pcm_8khz, TWILIO_SAMPLE_RATE, CONCYA_SAMPLE_RATE)
        
        return pcm_16khz
        
    except Exception as e:
        logger.error(f"❌ [AUDIO] Twilio→Concya conversion failed: {e}")
        return b''


# ═══════════════════════════════════════════════════════════════
# CALL SESSION MANAGEMENT
# ═══════════════════════════════════════════════════════════════

class CallSession:
    """Manages a single Twilio call session"""
    
    def __init__(self, call_sid: str, stream_sid: str, caller_number: str):
        self.call_sid = call_sid
        self.stream_sid = stream_sid
        self.caller_number = caller_number
        self.concya_session_id = f"twilio_{call_sid}_{int(time.time())}"
        self.start_time = time.time()
        self.last_activity = time.time()
        
        # WebSocket connections
        self.twilio_ws: Optional[WebSocket] = None
        self.concya_ws: Optional[WebSocket] = None
        
        # Audio buffers
        self.audio_buffer = bytearray()
        self.transcription_queue = asyncio.Queue()
        self.tts_queue = asyncio.Queue()
        
        # State management
        self.state = "listening"  # listening, thinking, speaking
        self.is_active = True
        
        logger.info(f"📞 [CALL] New session: {call_sid} from {caller_number}")
        logger.info(f"   └─ Concya session: {self.concya_session_id}")
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = time.time()
    
    def is_timeout(self) -> bool:
        """Check if call has timed out"""
        return (time.time() - self.last_activity) > CALL_TIMEOUT_SECONDS
    
    def get_duration(self) -> float:
        """Get call duration in seconds"""
        return time.time() - self.start_time
    
    async def cleanup(self):
        """Clean up resources"""
        logger.info(f"🧹 [CALL] Cleaning up session {self.call_sid}")
        self.is_active = False
        
        # Close WebSocket connections
        if self.concya_ws:
            try:
                await self.concya_ws.close()
            except:
                pass
        
        # Record metrics
        duration = self.get_duration()
        twilio_call_duration_seconds.observe(duration)
        twilio_calls_active.dec()
        
        logger.info(f"✅ [CALL] Session ended. Duration: {duration:.1f}s")


# ═══════════════════════════════════════════════════════════════
# TWILIO WEBHOOK HANDLERS
# ═══════════════════════════════════════════════════════════════

@router.post("/voice")
async def handle_incoming_call(request: Request):
    """
    Twilio webhook for incoming voice calls
    Returns TwiML to greet caller and start Media Stream
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "unknown")
    from_number = form_data.get("From", "unknown")
    to_number = form_data.get("To", "unknown")
    
    logger.info(f"📞 [TWILIO] Incoming call: {call_sid}")
    logger.info(f"   ├─ From: {from_number}")
    logger.info(f"   └─ To: {to_number}")
    
    twilio_calls_total.inc()
    
    # Construct WebSocket URL for Media Stream
    ws_url = PUBLIC_WEBHOOK_URL.replace("http://", "ws://").replace("https://", "wss://")
    stream_url = f"{ws_url}/twilio/stream"
    
    # Generate TwiML response
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">
        Hi, this is Concya, your AI reservation assistant! How can I help you today?
    </Say>
    <Connect>
        <Stream url="{stream_url}" />
    </Connect>
</Response>"""
    
    logger.info(f"📤 [TWILIO] Sending TwiML with Stream URL: {stream_url}")
    
    return Response(content=twiml, media_type="application/xml")


@router.post("/status")
async def handle_call_status(request: Request):
    """
    Optional: Handle call status callbacks from Twilio
    Tracks call lifecycle: ringing, in-progress, completed, failed
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "unknown")
    call_status = form_data.get("CallStatus", "unknown")
    duration = form_data.get("CallDuration", "0")
    
    logger.info(f"📊 [TWILIO] Call status update: {call_sid}")
    logger.info(f"   ├─ Status: {call_status}")
    logger.info(f"   └─ Duration: {duration}s")
    
    # Clean up session if call completed
    if call_status in ["completed", "failed", "busy", "no-answer"]:
        if call_sid in active_calls:
            session = active_calls[call_sid]
            await session.cleanup()
            del active_calls[call_sid]
    
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════
# TWILIO MEDIA STREAM WebSocket HANDLER
# ═══════════════════════════════════════════════════════════════

@router.websocket("/stream")
async def handle_media_stream(websocket: WebSocket):
    """
    WebSocket endpoint for Twilio Media Streams
    Handles bidirectional audio streaming between Twilio and Concya
    """
    await websocket.accept()
    logger.info("🔌 [TWILIO-WS] Media Stream connected")
    
    session: Optional[CallSession] = None
    
    try:
        # Wait for stream start event from Twilio
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            event = msg.get("event")
            
            if event == "connected":
                logger.info("✅ [TWILIO-WS] Stream connected")
                logger.debug(f"   Protocol: {msg.get('protocol')}, Version: {msg.get('version')}")
                continue
            
            elif event == "start":
                # Extract call information
                stream_sid = msg.get("streamSid")
                call_sid = msg.get("start", {}).get("callSid")
                media_format = msg.get("start", {}).get("mediaFormat", {})
                custom_params = msg.get("start", {}).get("customParameters", {})
                
                logger.info(f"🎬 [TWILIO-WS] Stream started")
                logger.info(f"   ├─ Stream SID: {stream_sid}")
                logger.info(f"   ├─ Call SID: {call_sid}")
                logger.info(f"   └─ Format: {media_format}")
                
                # Create call session
                caller_number = custom_params.get("from", "unknown")
                session = CallSession(call_sid, stream_sid, caller_number)
                session.twilio_ws = websocket
                active_calls[call_sid] = session
                twilio_calls_active.inc()
                
                # Connect to Concya /asr WebSocket
                await connect_to_concya_stt(session)
                
                # Start conversation handling tasks
                asyncio.create_task(process_transcriptions(session))
                asyncio.create_task(handle_tts_playback(session))
                
                break
        
        # Main loop: Handle incoming audio from Twilio
        if session:
            await handle_twilio_audio_stream(websocket, session)
            
    except WebSocketDisconnect:
        logger.info("🔌 [TWILIO-WS] Client disconnected")
    except Exception as e:
        logger.error(f"❌ [TWILIO-WS] Error: {e}", exc_info=True)
    finally:
        # Cleanup
        if session:
            await session.cleanup()
            if session.call_sid in active_calls:
                del active_calls[session.call_sid]


async def handle_twilio_audio_stream(websocket: WebSocket, session: CallSession):
    """
    Process incoming audio chunks from Twilio Media Stream
    Convert and forward to Concya STT engine
    """
    audio_chunk_count = 0
    
    try:
        while session.is_active:
            # Receive audio message from Twilio
            data = await websocket.receive_text()
            msg = json.loads(data)
            event = msg.get("event")
            
            if event == "media":
                audio_chunk_count += 1
                session.update_activity()
                
                # Extract audio payload
                media = msg.get("media", {})
                payload = media.get("payload", "")
                timestamp = media.get("timestamp", "0")
                
                if not payload:
                    continue
                
                # Log every 50 chunks to avoid spam
                if audio_chunk_count % 50 == 0:
                    logger.debug(f"🎤 [TWILIO] Received {audio_chunk_count} audio chunks")
                
                # Convert Twilio audio to Concya format
                start_time = time.time()
                pcm_16khz = twilio_to_concya_audio(payload)
                conversion_time_ms = (time.time() - start_time) * 1000
                
                if conversion_time_ms > 10:  # Log slow conversions
                    logger.warning(f"⚠️  [AUDIO] Slow conversion: {conversion_time_ms:.1f}ms")
                
                # Forward to Concya STT WebSocket
                if pcm_16khz and session.concya_ws:
                    try:
                        await session.concya_ws.send_bytes(pcm_16khz)
                    except Exception as e:
                        logger.error(f"❌ [STT] Failed to send audio: {e}")
                        break
            
            elif event == "stop":
                logger.info(f"🛑 [TWILIO] Stream stopped by Twilio")
                break
            
            elif event == "mark":
                # Mark events are acknowledgments we sent
                mark_name = msg.get("mark", {}).get("name")
                logger.debug(f"✓ [TWILIO] Mark acknowledged: {mark_name}")
            
            else:
                logger.debug(f"❓ [TWILIO] Unknown event: {event}")
            
    except Exception as e:
        logger.error(f"❌ [TWILIO] Audio stream error: {e}", exc_info=True)
    finally:
        logger.info(f"📊 [TWILIO] Processed {audio_chunk_count} audio chunks")


async def connect_to_concya_stt(session: CallSession):
    """
    Establish WebSocket connection to Concya's /asr endpoint
    """
    try:
        # Determine WebSocket URL
        base_url = os.getenv("CONCYA_STT_URL", "ws://localhost:8000")
        ws_url = f"{base_url}/asr"
        
        logger.info(f"🔗 [STT] Connecting to Concya STT: {ws_url}")
        
        # Use websockets library for client connection
        import websockets
        session.concya_ws = await websockets.connect(ws_url)
        
        logger.info(f"✅ [STT] Connected to Concya STT")
        
        # Start task to receive transcriptions
        asyncio.create_task(receive_stt_transcriptions(session))
        
    except Exception as e:
        logger.error(f"❌ [STT] Connection failed: {e}")


async def receive_stt_transcriptions(session: CallSession):
    """
    Receive transcription results from Concya STT WebSocket
    Queue complete sentences for LLM processing
    """
    try:
        while session.is_active and session.concya_ws:
            # Receive transcription message
            message = await session.concya_ws.recv()
            data = json.loads(message)
            
            msg_type = data.get("type")
            
            if msg_type == "config":
                logger.debug(f"📝 [STT] Config received: {data}")
                continue
            
            elif msg_type == "ready_to_stop":
                logger.info(f"🛑 [STT] STT ready to stop")
                break
            
            # Extract transcription lines
            lines = data.get("lines", [])
            buffer_text = data.get("buffer_transcription", "")
            
            if lines:
                for line in lines:
                    text = line.get("text", "").strip()
                    if text:
                        logger.info(f"📝 [STT] Transcription: '{text}'")
                        # Queue for LLM processing
                        await session.transcription_queue.put({
                            "text": text,
                            "language": line.get("detected_language", "en"),
                            "timestamp": time.time()
                        })
            
            # Show buffer (partial transcription) for debugging
            if buffer_text:
                logger.debug(f"🔄 [STT] Buffer: '{buffer_text}'")
    
    except Exception as e:
        logger.error(f"❌ [STT] Transcription receiver error: {e}", exc_info=True)


async def process_transcriptions(session: CallSession):
    """
    Process transcriptions and send to LLM for response generation
    Implements debouncing to wait for complete sentences
    """
    last_process_time = 0
    DEBOUNCE_DELAY = 1.5  # Wait 1.5s after last transcription
    
    try:
        while session.is_active:
            try:
                # Get transcription with timeout
                transcription = await asyncio.wait_for(
                    session.transcription_queue.get(),
                    timeout=0.5
                )
            except asyncio.TimeoutError:
                continue
            
            text = transcription["text"]
            language = transcription["language"]
            
            # Debounce: Wait for pauses between speech
            current_time = time.time()
            if current_time - last_process_time < DEBOUNCE_DELAY:
                logger.debug(f"⏳ [LLM] Debouncing...")
                await asyncio.sleep(0.5)
                continue
            
            # Update state
            session.state = "thinking"
            logger.info(f"🤔 [LLM] Processing: '{text}'")
            
            # Send to LLM
            try:
                llm_url = os.getenv("CONCYA_LLM_URL", "http://localhost:8000")
                response = requests.post(
                    f"{llm_url}/conversation",
                    json={
                        "text": text,
                        "session_id": session.concya_session_id,
                        "language": language
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    reply = data.get("reply", "")
                    
                    if reply:
                        logger.info(f"💬 [LLM] Reply: '{reply}'")
                        
                        # Queue for TTS
                        await session.tts_queue.put(reply)
                else:
                    logger.error(f"❌ [LLM] Error: HTTP {response.status_code}")
            
            except Exception as e:
                logger.error(f"❌ [LLM] Request failed: {e}")
            
            last_process_time = time.time()
            session.state = "listening"
    
    except Exception as e:
        logger.error(f"❌ [LLM] Transcription processor error: {e}", exc_info=True)


async def handle_tts_playback(session: CallSession):
    """
    Generate TTS audio and stream back to Twilio
    """
    try:
        while session.is_active:
            # Get next TTS text
            try:
                tts_text = await asyncio.wait_for(
                    session.tts_queue.get(),
                    timeout=0.5
                )
            except asyncio.TimeoutError:
                continue
            
            # Update state
            session.state = "speaking"
            logger.info(f"🔊 [TTS] Generating audio for: '{tts_text[:50]}...'")
            
            # Request TTS audio
            start_time = time.time()
            try:
                tts_url = os.getenv("CONCYA_TTS_URL", "http://localhost:8000")
                response = requests.post(
                    f"{tts_url}/speak",
                    json={"text": tts_text, "voice": "alloy"},
                    timeout=30
                )
                
                if response.status_code == 200:
                    mp3_data = response.content
                    tts_latency_ms = (time.time() - start_time) * 1000
                    
                    logger.info(f"✅ [TTS] Generated {len(mp3_data)} bytes in {tts_latency_ms:.0f}ms")
                    
                    # Convert MP3 to Twilio format
                    mulaw_base64 = mp3_to_mulaw_8khz(mp3_data)
                    
                    if mulaw_base64 and session.twilio_ws:
                        # Stream audio back to Twilio
                        await stream_audio_to_twilio(session, mulaw_base64)
                    
                    # Track total latency
                    total_latency_ms = (time.time() - start_time) * 1000
                    twilio_audio_latency_ms.observe(total_latency_ms)
                    
                else:
                    logger.error(f"❌ [TTS] Error: HTTP {response.status_code}")
            
            except Exception as e:
                logger.error(f"❌ [TTS] Request failed: {e}")
            
            session.state = "listening"
    
    except Exception as e:
        logger.error(f"❌ [TTS] Playback handler error: {e}", exc_info=True)


async def stream_audio_to_twilio(session: CallSession, mulaw_base64: str):
    """
    Stream audio chunks back to Twilio Media Stream
    Splits large audio into smaller chunks for streaming
    """
    try:
        # Twilio expects chunks, so split audio if needed
        # Each chunk should be ~20ms of audio
        CHUNK_SIZE = 320  # bytes (20ms at 8kHz µ-law = 160 samples = 160 bytes base64-encoded)
        
        # Decode base64 to get actual audio size
        audio_bytes = base64.b64decode(mulaw_base64)
        total_chunks = (len(audio_bytes) + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        logger.info(f"📤 [TWILIO] Streaming {len(audio_bytes)} bytes ({total_chunks} chunks)")
        
        for i in range(total_chunks):
            start_idx = i * CHUNK_SIZE
            end_idx = min((i + 1) * CHUNK_SIZE, len(audio_bytes))
            chunk = audio_bytes[start_idx:end_idx]
            
            # Re-encode chunk as base64
            chunk_base64 = base64.b64encode(chunk).decode('utf-8')
            
            # Send media message to Twilio
            media_message = {
                "event": "media",
                "streamSid": session.stream_sid,
                "media": {
                    "payload": chunk_base64
                }
            }
            
            await session.twilio_ws.send_text(json.dumps(media_message))
            
            # Small delay to maintain streaming pace (~20ms per chunk)
            await asyncio.sleep(0.02)
        
        # Send mark to indicate audio complete
        mark_message = {
            "event": "mark",
            "streamSid": session.stream_sid,
            "mark": {
                "name": "audio_complete"
            }
        }
        await session.twilio_ws.send_text(json.dumps(mark_message))
        
        logger.info(f"✅ [TWILIO] Audio streaming complete")
    
    except Exception as e:
        logger.error(f"❌ [TWILIO] Audio streaming failed: {e}", exc_info=True)


# ═══════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════

@router.get("/health")
async def twilio_health():
    """Health check endpoint for Twilio integration"""
    return {
        "status": "healthy",
        "active_calls": len(active_calls),
        "config": {
            "twilio_configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN),
            "webhook_url": PUBLIC_WEBHOOK_URL
        }
    }

