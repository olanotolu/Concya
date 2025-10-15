from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from whisperlivekit import TranscriptionEngine, AudioProcessor
from openai import OpenAI
from typing import Dict, List, Optional
from datetime import datetime
import asyncio
import logging
import os
import time
import json
from pathlib import Path
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger().setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ═══════════════════════════════════════════════════════════════
# PROMETHEUS METRICS - Unified (STT + LLM + TTS)
# ═══════════════════════════════════════════════════════════════

# STT Metrics
stt_latency_ms = Histogram(
    'stt_latency_ms',
    'STT transcription latency in milliseconds',
    buckets=[10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
)

stt_audio_duration_seconds = Histogram(
    'stt_audio_duration_seconds',
    'Duration of audio processed in seconds',
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120, 300]
)

stt_rtf = Histogram(
    'stt_rtf',
    'STT Real-Time Factor (processing_time / audio_duration)',
    buckets=[0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0, 5.0]
)

stt_requests_total = Counter('stt_requests_total', 'Total STT requests')
stt_errors_total = Counter('stt_errors_total', 'Total STT errors')

websocket_connections_active = Gauge('websocket_connections_active', 'Active WebSocket connections')
websocket_messages_received = Counter('websocket_messages_received', 'Total WebSocket messages received')
websocket_messages_sent = Counter('websocket_messages_sent', 'Total WebSocket messages sent')

# LLM Metrics
llm_latency_ms = Histogram(
    'llm_latency_ms',
    'LLM response generation latency in milliseconds',
    buckets=[50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000, 10000]
)

llm_tokens_used = Histogram(
    'llm_tokens_used',
    'Total tokens used per LLM request',
    buckets=[10, 50, 100, 200, 500, 1000, 2000, 4000]
)

llm_prompt_tokens = Histogram(
    'llm_prompt_tokens',
    'Prompt tokens per LLM request',
    buckets=[10, 50, 100, 200, 500, 1000, 2000]
)

llm_completion_tokens = Histogram(
    'llm_completion_tokens',
    'Completion tokens per LLM request',
    buckets=[5, 20, 50, 100, 200, 500, 1000]
)

llm_requests_total = Counter('llm_requests_total', 'Total LLM requests')
llm_errors_total = Counter('llm_errors_total', 'Total LLM errors')

# TTS Metrics
tts_latency_ms = Histogram(
    'tts_latency_ms',
    'TTS audio generation latency in milliseconds',
    buckets=[100, 250, 500, 1000, 1500, 2000, 3000, 5000, 10000]
)

tts_audio_bytes = Histogram(
    'tts_audio_bytes',
    'TTS audio size in bytes',
    buckets=[1000, 5000, 10000, 25000, 50000, 100000, 250000, 500000]
)

tts_requests_total = Counter('tts_requests_total', 'Total TTS requests')
tts_errors_total = Counter('tts_errors_total', 'Total TTS errors')

# Conversation & Reservation Metrics
active_conversations = Gauge('active_conversations', 'Number of active conversation sessions')
reservations_created_total = Counter('reservations_created_total', 'Total reservations created')
reservations_cancelled_total = Counter('reservations_cancelled_total', 'Total reservations cancelled')

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# STT Configuration
MODEL = os.getenv("WHISPER_MODEL", "base")
LANGUAGE = os.getenv("WHISPER_LANGUAGE", "auto")
DIARIZATION = os.getenv("ENABLE_DIARIZATION", "true").lower() == "true"
TARGET_LANGUAGE = os.getenv("TARGET_LANGUAGE", "")

logger.info(f"🚀 Starting Concya - Unified STT + LLM + TTS Service")
logger.info(f"📦 Whisper Model: {MODEL}")
logger.info(f"🌍 Language: {LANGUAGE}")
logger.info(f"👥 Diarization: {DIARIZATION}")
if TARGET_LANGUAGE:
    logger.info(f"🔄 Translation to: {TARGET_LANGUAGE}")

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# In-memory storage
conversations: Dict[str, List[dict]] = {}
reservations: List[dict] = []

# Global transcription engine
transcription_engine = None

# ═══════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════

class ConversationRequest(BaseModel):
    text: str
    session_id: str
    language: Optional[str] = "en"

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "alloy"

class ReservationCreate(BaseModel):
    customer_name: str
    date: str
    time: str
    party_size: int
    phone: Optional[str] = None
    notes: Optional[str] = None

# System prompt for Concya
RESERVATION_SYSTEM_PROMPT = """You are Concya, an AI reservation assistant for a restaurant.

Your goal is to:
1. Quickly collect: Name, Date, Time, Party size
2. Confirm the reservation details
3. Be friendly but concise (max 2-3 sentences per response)
4. Handle changes or cancellations efficiently

Current available times: 
- Lunch: 11:30 AM - 2:30 PM
- Dinner: 5:00 PM - 10:00 PM
- Closed Mondays

Response format examples:
- "Hi [Name]! I'd be happy to help. What date and time works for you?"
- "Perfect! [Date] at [Time] for [number] people. Can I get your name?"
- "Great! I've reserved [Date] at [Time] for [Name], party of [number]. See you then!"

Keep responses under 30 words. Be warm but efficient."""

# ═══════════════════════════════════════════════════════════════
# LIFESPAN - Initialize STT Engine
# ═══════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    global transcription_engine
    logger.info("🔥 Initializing TranscriptionEngine...")

    try:
        transcription_engine = TranscriptionEngine(
            model=MODEL,
            language=LANGUAGE,
            diarization=DIARIZATION,
            target_language=TARGET_LANGUAGE,
            backend="simulstreaming",
            preload_model_count=1,
            vad=True,
            vac=True,
            pcm_input=False,
        )
        logger.info("✅ TranscriptionEngine ready with diarization!")
    except SystemExit as e:
        if "nemo_toolkit" in str(e) or "megatron" in str(e):
            logger.warning("⚠️  NeMo diarization not available, falling back without diarization...")
            transcription_engine = TranscriptionEngine(
                model=MODEL,
                language=LANGUAGE,
                diarization=False,
                target_language=TARGET_LANGUAGE,
                backend="simulstreaming",
                preload_model_count=1,
                vad=True,
                vac=True,
                pcm_input=False,
            )
            logger.info("✅ TranscriptionEngine ready without diarization!")
        else:
            raise e
    except Exception as e:
        logger.error(f"❌ Failed to initialize TranscriptionEngine: {e}")
        raise e

    yield
    logger.info("🔌 Shutting down...")

# ═══════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="Concya - AI Reservation Assistant",
    description="Unified STT, LLM, and TTS service for voice-based reservations",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════
# ROUTES - General
# ═══════════════════════════════════════════════════════════════

@app.get("/")
async def get():
    """Serve the frontend web UI"""
    index_path = Path(__file__).parent / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text())
    else:
        return HTMLResponse("""
        <html>
            <head><title>Concya - AI Reservation Assistant</title></head>
            <body>
                <h1>Concya is running!</h1>
                <p>WebSocket endpoint: <code>/asr</code></p>
                <p>LLM endpoint: <code>/conversation</code></p>
                <p>TTS endpoint: <code>/speak</code></p>
            </body>
        </html>
        """)

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "concya-unified",
        "stt_model": MODEL,
        "language": LANGUAGE,
        "diarization": DIARIZATION,
        "translation": bool(TARGET_LANGUAGE)
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    logger.debug("📊 [METRICS] Metrics requested")
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

# ═══════════════════════════════════════════════════════════════
# ROUTES - LLM Conversation
# ═══════════════════════════════════════════════════════════════

@app.post("/conversation")
async def conversation(request: ConversationRequest):
    """Process conversation and generate LLM response"""
    
    llm_requests_total.inc()
    start_time = time.time()
    
    user_text_preview = request.text[:100] + "..." if len(request.text) > 100 else request.text
    logger.info(f"🗣️  [LLM] Received: '{user_text_preview}' | Session: {request.session_id[:8]}...")
    
    # Initialize conversation
    if request.session_id not in conversations:
        conversations[request.session_id] = []
        active_conversations.inc()
        logger.info(f"🆕 [LLM] New conversation: {request.session_id[:16]}...")
    
    # Add user message
    conversations[request.session_id].append({
        "role": "user",
        "content": request.text
    })
    
    # Build messages
    messages = [
        {"role": "system", "content": RESERVATION_SYSTEM_PROMPT}
    ] + conversations[request.session_id]
    
    try:
        logger.info(f"🤖 [LLM] Calling GPT-4o-mini (fast mode)...")
        llm_start = time.time()
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=80,
            temperature=0.7,
            stream=False
        )
        
        llm_duration_ms = (time.time() - llm_start) * 1000
        llm_latency_ms.observe(llm_duration_ms)
        
        reply = response.choices[0].message.content
        
        # Track token usage
        usage = response.usage
        if usage:
            llm_tokens_used.observe(usage.total_tokens)
            llm_prompt_tokens.observe(usage.prompt_tokens)
            llm_completion_tokens.observe(usage.completion_tokens)
            
            logger.info(f"✅ [LLM] Response in {llm_duration_ms:.0f}ms | Tokens: {usage.total_tokens} (prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens})")
        else:
            logger.info(f"✅ [LLM] Response in {llm_duration_ms:.0f}ms")
        
        logger.info(f"💬 [LLM] Reply: '{reply}'")
        
        # Add assistant response
        conversations[request.session_id].append({
            "role": "assistant",
            "content": reply
        })
        
        # Keep only last 8 messages for context
        if len(conversations[request.session_id]) > 8:
            conversations[request.session_id] = conversations[request.session_id][-8:]
            logger.debug(f"🗑️  [LLM] Trimmed conversation history to last 8 messages")
        
        # Try to extract reservation data
        reservation_data = extract_reservation_intent(conversations[request.session_id])
        
        total_duration_ms = (time.time() - start_time) * 1000
        logger.info(f"⏱️  [LLM] Total conversation endpoint latency: {total_duration_ms:.0f}ms")
        
        return {
            "reply": reply,
            "session_id": request.session_id,
            "reservation_data": reservation_data,
            "is_complete": is_reservation_complete(reservation_data)
        }
        
    except Exception as e:
        llm_errors_total.inc()
        error_duration_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ [LLM] Error after {error_duration_ms:.0f}ms: {str(e)}")
        logger.exception(e)
        return {
            "reply": "I apologize, let me try that again.",
            "session_id": request.session_id,
            "error": str(e)
        }

# ═══════════════════════════════════════════════════════════════
# ROUTES - TTS
# ═══════════════════════════════════════════════════════════════

@app.post("/speak")
async def speak(request: TTSRequest):
    """Generate speech audio (TTS)"""
    
    tts_requests_total.inc()
    start_time = time.time()
    
    text_preview = request.text[:80] + "..." if len(request.text) > 80 else request.text
    logger.info(f"🔊 [TTS] Generating audio for: '{text_preview}' | Voice: {request.voice}")
    
    try:
        tts_start = time.time()
        
        response = client.audio.speech.create(
            model="tts-1",
            voice=request.voice,
            input=request.text,
            speed=1.1
        )
        
        tts_duration_ms = (time.time() - tts_start) * 1000
        tts_latency_ms.observe(tts_duration_ms)
        
        audio_size = len(response.content)
        tts_audio_bytes.observe(audio_size)
        
        audio_size_kb = audio_size / 1024
        char_count = len(request.text)
        logger.info(f"✅ [TTS] Generated {audio_size_kb:.1f} KB in {tts_duration_ms:.0f}ms ({char_count} chars → {audio_size_kb/char_count:.2f} KB/char)")
        
        total_duration_ms = (time.time() - start_time) * 1000
        logger.info(f"⏱️  [TTS] Total speak endpoint latency: {total_duration_ms:.0f}ms")
        
        return Response(content=response.content, media_type="audio/mpeg")
        
    except Exception as e:
        tts_errors_total.inc()
        error_duration_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ [TTS] Error after {error_duration_ms:.0f}ms: {str(e)}")
        logger.exception(e)
        return Response(content=b"", media_type="audio/mpeg", status_code=500)

# ═══════════════════════════════════════════════════════════════
# ROUTES - Reservations
# ═══════════════════════════════════════════════════════════════

@app.post("/reservations")
async def create_reservation(reservation: ReservationCreate):
    """Create a new reservation"""
    
    logger.info(f"📝 [RESERVATION] Creating: {reservation.customer_name} on {reservation.date} at {reservation.time} (party of {reservation.party_size})")
    
    reservation_data = {
        "id": len(reservations) + 1,
        "customer_name": reservation.customer_name,
        "date": reservation.date,
        "time": reservation.time,
        "party_size": reservation.party_size,
        "phone": reservation.phone,
        "notes": reservation.notes,
        "created_at": datetime.now().isoformat(),
        "status": "confirmed"
    }
    
    reservations.append(reservation_data)
    reservations_created_total.inc()
    
    logger.info(f"✅ [RESERVATION] Created ID: {reservation_data['id']}")
    
    return reservation_data

@app.get("/reservations")
async def list_reservations():
    """Get all reservations"""
    return {
        "total": len(reservations),
        "reservations": reservations
    }

@app.delete("/reservations/{reservation_id}")
async def cancel_reservation(reservation_id: int):
    """Cancel a reservation"""
    
    for res in reservations:
        if res["id"] == reservation_id:
            res["status"] = "cancelled"
            reservations_cancelled_total.inc()
            logger.info(f"❌ [RESERVATION] Cancelled ID: {reservation_id} ({res['customer_name']} on {res['date']})")
            return {"message": "Reservation cancelled", "reservation": res}
    
    logger.warning(f"⚠️  [RESERVATION] Cancellation failed: ID {reservation_id} not found")
    raise HTTPException(status_code=404, detail="Reservation not found")

@app.post("/clear_session")
async def clear_session(request: Request):
    """Clear conversation session"""
    body = await request.json()
    session_id = body.get("session_id", "default")
    
    if session_id in conversations:
        message_count = len(conversations[session_id])
        del conversations[session_id]
        active_conversations.dec()
        logger.info(f"🗑️  [SESSION] Cleared: {session_id[:16]}... ({message_count} messages)")
    else:
        logger.debug(f"🗑️  [SESSION] Clear requested for non-existent session: {session_id[:16]}...")
    
    return {"status": "cleared", "session_id": session_id}

# ═══════════════════════════════════════════════════════════════
# ROUTES - STT WebSocket
# ═══════════════════════════════════════════════════════════════

async def handle_websocket_results(websocket, results_generator):
    """Consumes results from the audio processor and sends them via WebSocket."""
    try:
        async for response in results_generator:
            await websocket.send_json(response.to_dict())
            websocket_messages_sent.inc()
            logger.debug(f"📤 [WS] Sent transcription result")
        
        logger.info("✅ [STT] Results generator finished. Sending 'ready_to_stop' to client.")
        await websocket.send_json({"type": "ready_to_stop"})
        websocket_messages_sent.inc()
    except WebSocketDisconnect:
        logger.info("🔌 [WS] WebSocket disconnected while handling results (client likely closed connection).")
    except Exception as e:
        logger.exception(f"❌ [WS] Error in WebSocket results handler: {e}")
        stt_errors_total.inc()

@app.websocket("/asr")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time STT"""
    global transcription_engine
    
    websocket_connections_active.inc()
    connection_start = time.time()
    audio_chunks_received = 0
    audio_start_time = None
    total_audio_duration = 0.0
    
    logger.info("🔌 [WS] WebSocket connection opened")
    
    audio_processor = AudioProcessor(
        transcription_engine=transcription_engine,
    )
    
    await websocket.accept()

    try:
        use_pcm = False
        await websocket.send_json({"type": "config", "useAudioWorklet": use_pcm})
        websocket_messages_sent.inc()
        logger.debug("📤 [WS] Sent config to client")
    except Exception as e:
        logger.warning(f"⚠️  [WS] Failed to send config to client: {e}")
            
    results_generator = await audio_processor.create_tasks()
    websocket_task = asyncio.create_task(handle_websocket_results(websocket, results_generator))

    try:
        while True:
            stt_requests_total.inc()
            processing_start = time.time()
            
            message = await websocket.receive_bytes()
            websocket_messages_received.inc()
            audio_chunks_received += 1
            
            if audio_start_time is None:
                audio_start_time = time.time()
            
            message_size_kb = len(message) / 1024
            logger.debug(f"📥 [WS] Received audio chunk #{audio_chunks_received} ({message_size_kb:.1f} KB)")
            
            await audio_processor.process_audio(message)
            
            processing_time_ms = (time.time() - processing_start) * 1000
            stt_latency_ms.observe(processing_time_ms)
            
            logger.debug(f"⚡ [STT] Processed chunk in {processing_time_ms:.1f}ms")
            
    except KeyError as e:
        if 'bytes' in str(e):
            logger.info("🔌 [WS] Client has closed the connection")
        else:
            logger.error(f"❌ [WS] Unexpected KeyError: {e}", exc_info=True)
            stt_errors_total.inc()
    except WebSocketDisconnect:
        logger.info("🔌 [WS] WebSocket disconnected by client during message receiving loop")
    except Exception as e:
        logger.error(f"❌ [WS] Unexpected error in main loop: {e}", exc_info=True)
        stt_errors_total.inc()
    finally:
        # Calculate session metrics
        connection_duration = time.time() - connection_start
        if audio_start_time:
            total_audio_duration = time.time() - audio_start_time
            stt_audio_duration_seconds.observe(total_audio_duration)
            
            # Calculate Real-Time Factor
            rtf_value = connection_duration / total_audio_duration if total_audio_duration > 0 else 0
            stt_rtf.observe(rtf_value)
            
            logger.info(f"📊 [METRICS] Session complete:")
            logger.info(f"   ├─ Connection duration: {connection_duration:.2f}s")
            logger.info(f"   ├─ Audio duration: {total_audio_duration:.2f}s")
            logger.info(f"   ├─ RTF: {rtf_value:.3f} ({'✅ faster' if rtf_value < 1.0 else '⚠️  slower'} than real-time)")
            logger.info(f"   └─ Audio chunks: {audio_chunks_received}")
        
        logger.info("🧹 [WS] Cleaning up WebSocket endpoint...")
        websocket_connections_active.dec()
        
        if not websocket_task.done():
            websocket_task.cancel()
        try:
            await websocket_task
        except asyncio.CancelledError:
            logger.debug("🧹 [WS] Results handler task cancelled")
        except Exception as e:
            logger.warning(f"⚠️  [WS] Exception while awaiting task completion: {e}")
            
        await audio_processor.cleanup()
        logger.info("✅ [WS] WebSocket endpoint cleaned up successfully")

# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def extract_reservation_intent(messages: List[dict]) -> Optional[dict]:
    """Extract reservation details from conversation"""
    conversation_text = " ".join([msg["content"] for msg in messages if msg["role"] == "user"])
    data = {}
    # Placeholder - can be enhanced with GPT function calling or NER
    return data

def is_reservation_complete(data: Optional[dict]) -> bool:
    """Check if we have all required reservation info"""
    if not data:
        return False
    required = ["customer_name", "date", "time", "party_size"]
    return all(key in data and data[key] for key in required)

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )

