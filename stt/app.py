from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, Response, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from whisperlivekit import TranscriptionEngine, AudioProcessor
from openai import OpenAI
from typing import Dict, List
import asyncio
import logging
import os
import time
from pathlib import Path
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger().setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ═══════════════════════════════════════════════════════════════
# PROMETHEUS METRICS
# ═══════════════════════════════════════════════════════════════

# Latency metrics (in milliseconds)
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

# Real-Time Factor (RTF): processing_time / audio_duration
# RTF < 1.0 means faster than real-time
stt_rtf = Histogram(
    'stt_rtf',
    'STT Real-Time Factor (processing_time / audio_duration)',
    buckets=[0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0, 5.0]
)

# Request counters
stt_requests_total = Counter('stt_requests_total', 'Total STT requests')
stt_errors_total = Counter('stt_errors_total', 'Total STT errors')

# WebSocket metrics
websocket_connections_active = Gauge('websocket_connections_active', 'Active WebSocket connections')
websocket_messages_received = Counter('websocket_messages_received', 'Total WebSocket messages received')
websocket_messages_sent = Counter('websocket_messages_sent', 'Total WebSocket messages sent')

# Configuration from environment variables
MODEL = os.getenv("WHISPER_MODEL", "base")
LANGUAGE = os.getenv("WHISPER_LANGUAGE", "auto")
DIARIZATION = os.getenv("ENABLE_DIARIZATION", "true").lower() == "true"
TARGET_LANGUAGE = os.getenv("TARGET_LANGUAGE", "")  # For translation (e.g., "fr", "es")

logger.info(f"🚀 Starting WhisperLiveKit Service")
logger.info(f"📦 Model: {MODEL}")
logger.info(f"🌍 Language: {LANGUAGE}")
logger.info(f"👥 Diarization: {DIARIZATION}")
if TARGET_LANGUAGE:
    logger.info(f"🔄 Translation to: {TARGET_LANGUAGE}")

# Initialize OpenAI client for LLM + TTS
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
conversation_sessions: Dict[str, List[dict]] = {}

transcription_engine = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global transcription_engine
    logger.info("🔥 Initializing TranscriptionEngine...")

    # Try with diarization first
    try:
        transcription_engine = TranscriptionEngine(
            model=MODEL,
            language=LANGUAGE,
            diarization=DIARIZATION,
            target_language=TARGET_LANGUAGE,
            backend="simulstreaming",  # Use SimulStreaming for ultra-low latency
            # GPU optimizations
            preload_model_count=1,
            # VAD settings
            vad=True,
            vac=True,
            # PCM input for better quality
            pcm_input=False,  # Set to True if you want raw PCM
        )
        logger.info("✅ TranscriptionEngine ready with diarization!")
    except SystemExit as e:
        if "nemo_toolkit" in str(e) or "megatron" in str(e):
            logger.warning("⚠️  NeMo diarization not available, falling back without diarization...")
            transcription_engine = TranscriptionEngine(
                model=MODEL,
                language=LANGUAGE,
                diarization=False,  # Disable diarization
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

app = FastAPI(
    title="WhisperLiveKit STT",
    description="Real-time speech-to-text with speaker diarization",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the web UI
@app.get("/")
async def get():
    index_path = Path(__file__).parent / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text())
    else:
        return HTMLResponse("""
        <html>
            <head><title>WhisperLiveKit STT</title></head>
            <body>
                <h1>WhisperLiveKit is running!</h1>
                <p>WebSocket endpoint: <code>/asr</code></p>
                <p>Connect to: <code>ws://your-runpod-url:8000/asr</code></p>
            </body>
        </html>
        """)

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "model": MODEL,
        "language": LANGUAGE,
        "diarization": DIARIZATION,
        "translation": bool(TARGET_LANGUAGE)
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    logger.debug("📊 [METRICS] Metrics requested")
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/conversation")
async def conversation(request: Request):
    body = await request.json()
    user_text = body.get("text", "")
    session_id = body.get("session_id", "default")
    language = body.get("language", "en")
    
    logger.info(f"🗣️  [STT→LLM] Received transcription: '{user_text}' | Session: {session_id} | Language: {language}")
    
    # Initialize session if needed
    if session_id not in conversation_sessions:
        conversation_sessions[session_id] = []
        logger.info(f"🆕 [LLM] New session created: {session_id}")
    
    # System prompt for Concya
    system_prompt = (
        "You are Concya, an AI voice receptionist that makes reservations, "
        "answers politely, and detects language automatically. Keep responses "
        "concise and natural for voice conversation."
    )
    
    # Add user message to history
    conversation_sessions[session_id].append({"role": "user", "content": user_text})
    logger.info(f"📝 [LLM] Session history length: {len(conversation_sessions[session_id])} messages")
    
    # Build messages with system prompt + history
    messages = [{"role": "system", "content": system_prompt}] + conversation_sessions[session_id]
    
    try:
        # Get LLM response
        logger.info(f"🤖 [LLM] Sending to GPT-4o-mini...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=150
        )
        
        reply = response.choices[0].message.content
        logger.info(f"✅ [LLM] GPT-4o-mini replied: '{reply}'")
        
        # Add assistant response to history
        conversation_sessions[session_id].append({"role": "assistant", "content": reply})
        
        # Keep only last 10 messages to prevent context overflow
        if len(conversation_sessions[session_id]) > 10:
            conversation_sessions[session_id] = conversation_sessions[session_id][-10:]
            logger.info(f"🗑️  [LLM] Trimmed old messages, keeping last 10")
        
        return {"reply": reply, "session_id": session_id}
    
    except Exception as e:
        logger.error(f"❌ [LLM] Error: {str(e)}")
        return {"reply": "I apologize, I'm having trouble processing your request.", "session_id": session_id, "error": str(e)}

@app.post("/speak")
async def speak(request: Request):
    body = await request.json()
    text = body.get("text", "")
    voice = body.get("voice", "alloy")  # alloy, echo, fable, onyx, nova, shimmer
    
    logger.info(f"🔊 [LLM→TTS] Generating speech for: '{text[:50]}...' | Voice: {voice}")
    
    try:
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text
        )
        
        audio_size = len(response.content)
        logger.info(f"✅ [TTS] Generated {audio_size} bytes of audio")
        
        return Response(content=response.content, media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"❌ [TTS] Error: {str(e)}")
        return Response(content=b"", media_type="audio/mpeg", status_code=500)

@app.post("/clear_session")
async def clear_session(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "default")
    if session_id in conversation_sessions:
        del conversation_sessions[session_id]
    return {"status": "cleared"}

async def handle_websocket_results(websocket, results_generator):
    """Consumes results from the audio processor and sends them via WebSocket."""
    try:
        async for response in results_generator:
            await websocket.send_json(response.to_dict())
            websocket_messages_sent.inc()
            logger.debug(f"📤 [WS] Sent transcription result")
        # when the results_generator finishes it means all audio has been processed
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
        # Send config to client (tells frontend whether to use PCM or WebM)
        use_pcm = False  # Set to True if you want raw PCM input
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

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
