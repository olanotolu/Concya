from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from whisperlivekit import TranscriptionEngine, AudioProcessor
from openai import OpenAI
from supabase import create_client, Client
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import asyncio
import logging
import os
import time
import json
import re
import traceback
from pathlib import Path
try:
    from dateparser.search import search_dates
except ImportError:  # pragma: no cover - optional dependency
    search_dates = None  # type: ignore[assignment]
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

# Import metrics from centralized metrics module
from metrics import (
    # STT metrics
    stt_latency_ms, stt_audio_duration_seconds, stt_rtf,
    stt_requests_total, stt_errors_total,
    # WebSocket metrics
    websocket_connections_active, websocket_messages_received, websocket_messages_sent,
    # LLM metrics
    llm_latency_ms, llm_requests_total, llm_errors_total,
    llm_tokens_prompt, llm_tokens_completion,
    # TTS metrics
    tts_latency_ms, tts_audio_bytes, tts_requests_total, tts_errors_total,
    # Reservation metrics
    reservations_created_total, reservations_cancelled_total, reservations_active
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger().setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

if search_dates is None:
    logger.warning(
        "⚠️  dateparser is not installed. Reservation date parsing will fall back to basic heuristics."
    )

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# STT Configuration
MODEL = os.getenv("WHISPER_MODEL", "base")
LANGUAGE = os.getenv("WHISPER_LANGUAGE", "auto")
DIARIZATION = os.getenv("ENABLE_DIARIZATION", "true").lower() == "true"
TARGET_LANGUAGE = os.getenv("TARGET_LANGUAGE", "")

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")
supabase: Client = None

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
# DATABASE HELPERS
# ═══════════════════════════════════════════════════════════════

REQUIRED_RESERVATION_COLUMNS = [
    "id",
    "customer_name",
    "date",
    "time",
    "party_size",
    "phone",
    "notes",
    "created_at",
    "status",
]

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
RESERVATION_MIGRATION_FILE = MIGRATIONS_DIR / "001_create_reservations_table.sql"


def _log_reservation_migration_hint(reason: str) -> None:
    """Surface actionable instructions when schema checks fail."""
    logger.warning("⚠️  %s", reason)

    if RESERVATION_MIGRATION_FILE.exists():
        migration_sql = RESERVATION_MIGRATION_FILE.read_text().strip()
        logger.warning("   └─ Run the SQL migration at %s to create/update the table:", RESERVATION_MIGRATION_FILE)
        for line in migration_sql.splitlines():
            logger.warning("      %s", line)
    else:
        logger.warning(
            "   └─ Expected migration file missing at %s. Please create the reservations table manually.",
            RESERVATION_MIGRATION_FILE,
        )


async def create_reservations_table():
    """Ensure the reservations table exists and matches expected columns."""
    if not supabase:
        return

    try:
        # Check if table exists by trying to select from it
        supabase.table("reservations").select("id").limit(1).execute()
        logger.info("✅ Reservations table detected")
    except Exception as e:
        _log_reservation_migration_hint(
            "Reservations table not found or inaccessible in Supabase (error: %s)." % e
        )
        return

    try:
        supabase.table("reservations").select(",".join(REQUIRED_RESERVATION_COLUMNS)).limit(1).execute()
        logger.info("✅ Reservations table schema validated")
    except Exception as e:
        _log_reservation_migration_hint(
            "Reservations table schema check failed (missing columns or permissions). Error: %s" % e
        )

async def save_reservation_to_db(reservation_data: dict):
    """Save reservation to Supabase database"""
    if not supabase:
        return None

    try:
        result = supabase.table('reservations').insert(reservation_data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"❌ Failed to save reservation to database: {e}")
        return None

async def get_reservations_from_db():
    """Get all reservations from Supabase database"""
    if not supabase:
        return []

    try:
        result = supabase.table('reservations').select('*').execute()
        return result.data
    except Exception as e:
        logger.error(f"❌ Failed to fetch reservations from database: {e}")
        return []

async def update_reservation_status(reservation_id: int, status: str):
    """Update reservation status in Supabase database"""
    if not supabase:
        return False

    try:
        result = supabase.table('reservations').update({'status': status}).eq('id', reservation_id).execute()
        return len(result.data) > 0
    except Exception as e:
        logger.error(f"❌ Failed to update reservation status: {e}")
        return False

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
RESERVATION_SYSTEM_PROMPT = """You are Concya, a friendly AI reservation assistant for restaurants.

Your job is to:
- Greet the customer naturally and warmly
- Collect name, party size, preferred date, and time
- Confirm and summarize the booking politely
- Keep responses conversational, short, and friendly (under 30 words)
- Never mention being an AI or any technical details

Current available times:
- Lunch: 11:30 AM - 2:30 PM
- Dinner: 5:00 PM - 10:00 PM
- Closed Mondays

Always be welcoming, professional, and focused on creating a great dining experience."""

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

    # Initialize Supabase
    global supabase
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("✅ Supabase client initialized!")

            # Initialize database schema
            await create_reservations_table()
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase: {e}")
            supabase = None
    else:
        logger.warning("⚠️  Supabase credentials not provided - reservations will be stored in-memory only")
        supabase = None

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
    """API information and Twilio setup instructions"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
        <head>
            <title>Concya - AI Voice Reservation Assistant</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; 
                       max-width: 800px; margin: 50px auto; padding: 20px; line-height: 1.6; }
                h1 { color: #667eea; }
                h2 { color: #764ba2; margin-top: 30px; }
                code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }
                .endpoint { background: #e8f4f8; padding: 15px; margin: 10px 0; border-radius: 5px; }
                .status { color: #28a745; font-weight: bold; }
                a { color: #667eea; text-decoration: none; }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <h1>🎙️ Concya - AI Voice Reservation Assistant</h1>
            <p class="status">✅ Server is running!</p>
            
            <h2>📞 Twilio Voice Integration</h2>
            <p>Concya supports phone-based reservations via Twilio Voice.</p>
            
            <div class="endpoint">
                <strong>Twilio Webhook:</strong><br>
                <code>POST /twilio/voice</code> - Incoming call handler (TwiML)<br>
                <code>WS /twilio/stream</code> - Media Stream WebSocket<br>
                <code>POST /twilio/status</code> - Call status callbacks<br>
                <code>GET /twilio/health</code> - Health check
            </div>
            
            <h2>🔌 API Endpoints</h2>
            <div class="endpoint">
                <strong>STT:</strong> <code>WS /asr</code> - Real-time speech-to-text<br>
                <strong>LLM:</strong> <code>POST /conversation</code> - AI conversation<br>
                <strong>TTS:</strong> <code>POST /speak</code> - Text-to-speech<br>
                <strong>Metrics:</strong> <code>GET /metrics</code> - Prometheus metrics<br>
                <strong>Health:</strong> <code>GET /health</code> - System health check
            </div>
            
            <h2>📋 Setup Instructions</h2>
            <ol>
                <li>Configure environment variables (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, etc.)</li>
                <li>Set Twilio webhook to: <code>https://your-url.com/twilio/voice</code></li>
                <li>Call your Twilio number to test</li>
            </ol>
            
            <p>📖 See <a href="https://github.com/olanotolu/Concya/blob/master/TWILIO_SETUP.md">TWILIO_SETUP.md</a> for detailed instructions</p>
            
            <h2>🎯 Usage</h2>
            <p><strong>Terminal Client:</strong> Use <code>stt/client.py</code> for local testing</p>
            <p><strong>Phone Calls:</strong> Call your Twilio number and speak naturally</p>
            <p><strong>Web UI:</strong> Legacy interface archived in <code>archive/index.html</code></p>
            
            <p style="margin-top: 40px; color: #666; font-size: 14px;">
                Powered by WhisperLiveKit (STT) + OpenAI GPT-4o-mini (LLM) + OpenAI TTS-1
            </p>
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
    
    # Initialize conversation with welcome message if new
    if request.session_id not in conversations:
        conversations[request.session_id] = []
        logger.info(f"🆕 [LLM] New conversation: {request.session_id[:16]}...")

        # Add welcome message from assistant
        conversations[request.session_id].append({
            "role": "assistant",
            "content": "Hello! I'm Concya. I'd be delighted to help you make a reservation. What date and time would work for you?"
        })

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
            llm_tokens_prompt.observe(usage.prompt_tokens)
            llm_tokens_completion.observe(usage.completion_tokens)
            
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
async def speak(req: dict):
    """Generate speech audio from text."""

    tts_requests_total.inc()
    start_time = time.time()

    text = req.get("text", "")
    voice = req.get("voice", "alloy")

    if not text.strip():
        logger.warning("⚠️  [TTS] Empty text input")
        return JSONResponse(status_code=400, content={"error": "Empty text input"})

    text_preview = text[:80] + "..." if len(text) > 80 else text
    logger.info(f"🔊 [TTS] Generating audio for: '{text_preview}' | Voice: {voice}")

    try:
        tts_start = time.perf_counter()

        speech = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
            speed=1.1
        )

        audio_data = speech.read()

        tts_duration_ms = (time.perf_counter() - tts_start) * 1000
        tts_latency_ms.observe(tts_duration_ms)

        audio_size = len(audio_data)
        tts_audio_bytes.observe(audio_size)

        audio_size_kb = audio_size / 1024
        char_count = len(text)
        logger.info(f"✅ [TTS] Generated {audio_size_kb:.1f} KB in {tts_duration_ms:.1f}ms ({char_count} chars → {audio_size_kb/char_count:.2f} KB/char)")

        total_duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"⏱️  [TTS] Total speak endpoint latency: {total_duration_ms:.1f}ms")

        return Response(content=audio_data, media_type="audio/mpeg")

    except Exception as e:
        tts_errors_total.inc()
        error_duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(f"❌ [TTS] Error after {error_duration_ms:.1f}ms: {str(e)}")
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "trace": traceback.format_exc()},
        )

# ═══════════════════════════════════════════════════════════════
# ROUTES - Reservations
# ═══════════════════════════════════════════════════════════════

@app.post("/reservations")
async def create_reservation(reservation: ReservationCreate):
    """Create a new reservation"""

    logger.info(f"📝 [RESERVATION] Creating: {reservation.customer_name} on {reservation.date} at {reservation.time} (party of {reservation.party_size})")

    # Prepare reservation data for database
    reservation_data = {
        "customer_name": reservation.customer_name,
        "date": reservation.date,
        "time": reservation.time,
        "party_size": reservation.party_size,
        "phone": reservation.phone,
        "notes": reservation.notes,
        "created_at": datetime.now().isoformat(),
        "status": "confirmed"
    }

    # Try to save to database first
    db_result = await save_reservation_to_db(reservation_data)
    if db_result:
        # Use database ID and data
        reservation_data.update(db_result)
        logger.info(f"✅ [RESERVATION] Created in database with ID: {reservation_data['id']}")

        # Add confirmation message to response
        confirmation_msg = f"Perfect! I've reserved a table for {reservation_data['party_size']} on {reservation_data['date']} at {reservation_data['time']} under {reservation_data['customer_name']}. We're looking forward to seeing you!"
        reservation_data["confirmation_message"] = confirmation_msg

    else:
        # Fallback to in-memory storage
        reservation_data["id"] = len(reservations) + 1
        reservations.append(reservation_data)
        logger.warning(f"⚠️  [RESERVATION] Saved to memory only (ID: {reservation_data['id']})")

        # Add confirmation for in-memory storage too
        confirmation_msg = f"Great! I've noted your reservation for {reservation_data['party_size']} on {reservation_data['date']} at {reservation_data['time']}, {reservation_data['customer_name']}. Please call to confirm when you're ready!"
        reservation_data["confirmation_message"] = confirmation_msg

    reservations_created_total.inc()
    return reservation_data

@app.get("/reservations")
async def list_reservations():
    """Get all reservations"""

    # Try to fetch from database first
    db_reservations = await get_reservations_from_db()
    if db_reservations:
        return {
            "total": len(db_reservations),
            "reservations": db_reservations,
            "source": "database"
        }
    else:
        # Fallback to in-memory storage
        return {
            "total": len(reservations),
            "reservations": reservations,
            "source": "memory"
        }

@app.delete("/reservations/{reservation_id}")
async def cancel_reservation(reservation_id: int):
    """Cancel a reservation"""

    # Try to update in database first
    db_success = await update_reservation_status(reservation_id, "cancelled")
    if db_success:
        reservations_cancelled_total.inc()
        logger.info(f"❌ [RESERVATION] Cancelled in database - ID: {reservation_id}")
        return {"message": "Reservation cancelled", "id": reservation_id}

    # Fallback to in-memory storage
    for res in reservations:
        if res["id"] == reservation_id:
            res["status"] = "cancelled"
            reservations_cancelled_total.inc()
            logger.info(f"❌ [RESERVATION] Cancelled in memory - ID: {reservation_id} ({res['customer_name']} on {res['date']})")
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

NAME_PATTERNS = [
    re.compile(r"(?:my name is|i am|i'm called|this is|you're speaking with)\s+(?P<name>[A-Za-z][A-Za-z\-']*(?:\s+[A-Za-z][A-Za-z\-']*){0,2})", re.IGNORECASE),
    re.compile(r"name[:\s]+(?P<name>[A-Za-z][A-Za-z\-']*(?:\s+[A-Za-z][A-Za-z\-']*){0,2})", re.IGNORECASE),
]

PARTY_PATTERNS = [
    re.compile(r"(?:party of|for|table for|seating for)\s+(?P<count>\d{1,2}|[a-z\-]+)", re.IGNORECASE),
    re.compile(r"(?P<count>\d{1,2})\s+(?:people|persons?|guests?|heads|adults)", re.IGNORECASE),
]

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "couple": 2,
    "both": 2,
    "pair": 2,
}

DATE_HINT_PATTERN = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?|today|tonight|tomorrow|next|this|am|pm|noon|midnight|evening|morning)\b",
    re.IGNORECASE,
)

TIME_HINT_PATTERN = re.compile(r"\b(?:am|pm|a\.m\.|p\.m\.|o'clock|noon|midnight)\b", re.IGNORECASE)

PHONE_PATTERN = re.compile(r"(?:\+?\d[\d\s\-()]{6,}\d)")

NOTES_KEYWORDS = [
    "anniversary",
    "birthday",
    "wheelchair",
    "allerg",
    "gluten",
    "peanut",
    "quiet",
    "window",
    "booth",
    "high chair",
    "baby",
    "kids",
    "celebrat",
]

TIME_PATTERNS = [
    re.compile(
        r"(?:at\s*)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<period>am|pm|a\.m\.|p\.m\.)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:at\s*)?(?P<hour>\d{1,2}):(?P<minute>\d{2})"),
]


def _normalize_name(raw_name: str) -> str:
    parts = [part for part in re.split(r"\s+", raw_name) if part]
    return " ".join(part.capitalize() for part in parts)


def _extract_notes_from_text(full_text: str) -> Optional[str]:
    sentences = re.split(r"(?<=[.!?])\s+", full_text)
    relevant_sentences = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(keyword in lowered for keyword in NOTES_KEYWORDS):
            relevant_sentences.append(sentence.strip())
    if not relevant_sentences:
        return None
    # Preserve order while removing duplicates
    seen = []
    for sentence in relevant_sentences:
        if sentence not in seen:
            seen.append(sentence)
    return " ".join(seen)


def _normalize_phone(raw_phone: str) -> Optional[str]:
    digits = re.sub(r"\D", "", raw_phone)
    if len(digits) < 7:
        return None
    if raw_phone.strip().startswith("+"):
        return "+" + digits
    return digits


def extract_reservation_intent(messages: List[dict]) -> Optional[dict]:
    """Extract reservation details from conversation using richer heuristics."""

    user_messages = [msg["content"] for msg in messages if msg["role"] == "user"]
    if not user_messages:
        return None

    combined_text = " ".join(user_messages)
    combined_lower = combined_text.lower()
    data: Dict[str, Any] = {}

    # Extract customer name (prefer the latest mention)
    for message in reversed(user_messages):
        for pattern in NAME_PATTERNS:
            match = pattern.search(message)
            if match:
                normalized_name = _normalize_name(match.group("name"))
                if normalized_name:
                    data["customer_name"] = normalized_name
                    break
        if "customer_name" in data:
            break

    # Extract party size, supporting both numeric digits and words
    for message in reversed(user_messages):
        for pattern in PARTY_PATTERNS:
            match = pattern.search(message)
            if not match:
                continue

            count_raw = match.group("count")
            party_size: Optional[int] = None
            if count_raw.isdigit():
                party_size = int(count_raw)
            else:
                count_key = count_raw.lower().strip()
                party_size = NUMBER_WORDS.get(count_key)

            if party_size is None and "just me" in message.lower():
                party_size = 1

            if party_size and 1 <= party_size <= 20:
                data["party_size"] = party_size
                break
        if "party_size" in data:
            break

    now = datetime.now()

    if "tomorrow" in combined_lower and "date" not in data:
        data["date"] = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    elif any(keyword in combined_lower for keyword in ["today", "tonight", "later today"]) and "date" not in data:
        data["date"] = now.strftime("%Y-%m-%d")

    settings = {
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": now,
        "RETURN_AS_TIMEZONE_AWARE": False,
    }

    date_results = []
    if search_dates is not None:
        try:
            date_results = search_dates(combined_text, settings=settings) or []
        except Exception as e:
            logger.debug(f"🔍 Date parsing failed: {e}")

    for phrase, parsed in date_results:
        normalized_phrase = phrase.strip()
        normalized_lower = normalized_phrase.lower()

        digits_only = re.sub(r"\D", "", normalized_phrase)
        if len(digits_only) >= 7 and not DATE_HINT_PATTERN.search(normalized_lower):
            # Likely a phone number or reference that isn't a date/time
            continue

        if "date" not in data:
            data["date"] = parsed.strftime("%Y-%m-%d")

        if "time" not in data:
            has_time_hint = (
                parsed.time() != datetime.min.time()
                or TIME_HINT_PATTERN.search(normalized_lower)
                or any(keyword in normalized_lower for keyword in ["lunch", "dinner", "evening", "morning", "tonight"])
            )
            if has_time_hint:
                data["time"] = parsed.strftime("%H:%M")

        if "date" in data and "time" in data:
            break

    if "time" not in data:
        for pattern in TIME_PATTERNS:
            match = pattern.search(combined_lower)
            if not match:
                continue

            hour = int(match.group("hour"))
            minute = int(match.group("minute")) if match.group("minute") else 0
            period = match.groupdict().get("period")

            if period:
                period = period.lower()
                if period.startswith("p") and hour != 12:
                    hour += 12
                elif period.startswith("a") and hour == 12:
                    hour = 0
            if 0 <= hour <= 23:
                data["time"] = f"{hour:02d}:{minute:02d}"
                break

    if "time" not in data:
        if "noon" in combined_lower:
            data["time"] = "12:00"
        elif "midnight" in combined_lower:
            data["time"] = "00:00"
        elif any(keyword in combined_lower for keyword in ["lunch", "midday"]):
            data["time"] = "12:30"
        elif any(keyword in combined_lower for keyword in ["dinner", "evening", "tonight"]):
            data["time"] = "19:00"

    if "date" in data and "time" in data:
        # Normalize to ensure dinner fallback doesn't land outside restaurant hours
        try:
            parsed_time = datetime.strptime(data["time"], "%H:%M").time()
            if parsed_time < datetime.strptime("11:30", "%H:%M").time():
                note_text = "Requested time earlier than opening hours."
                existing_note = data.get("notes")
                if isinstance(existing_note, str) and existing_note:
                    if note_text not in existing_note:
                        data["notes"] = f"{existing_note} {note_text}".strip()
                else:
                    data["notes"] = note_text
        except ValueError:
            pass

    # Extract phone numbers if present
    phone_match = PHONE_PATTERN.search(combined_text)
    if phone_match:
        normalized_phone = _normalize_phone(phone_match.group())
        if normalized_phone:
            data["phone"] = normalized_phone

    notes = _extract_notes_from_text(combined_text)
    if notes:
        data["notes"] = notes

    if not data:
        return None

    return data

def is_reservation_complete(data: Optional[dict]) -> bool:
    """Check if we have all required reservation info"""
    if not data:
        return False
    required = ["customer_name", "date", "time", "party_size"]
    return all(key in data and data[key] for key in required)

# ═══════════════════════════════════════════════════════════════
# TWILIO VOICE INTEGRATION
# ═══════════════════════════════════════════════════════════════

try:
    from twilio_integration import router as twilio_router
    app.include_router(twilio_router, prefix="/twilio", tags=["twilio"])
    logger.info("✅ Twilio Voice integration loaded")
except ImportError as e:
    logger.warning(f"⚠️  Twilio integration not available: {e}")
except Exception as e:
    logger.error(f"❌ Failed to load Twilio integration: {e}")

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

