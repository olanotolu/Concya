from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from typing import Dict, List, Optional
from datetime import datetime
import logging
import os
import json
import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# PROMETHEUS METRICS
# ═══════════════════════════════════════════════════════════════

# LLM Latency (ms)
llm_latency_ms = Histogram(
    'llm_latency_ms',
    'LLM response generation latency in milliseconds',
    buckets=[50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000, 10000]
)

# TTS Latency (ms)
tts_latency_ms = Histogram(
    'tts_latency_ms',
    'TTS audio generation latency in milliseconds',
    buckets=[100, 250, 500, 1000, 1500, 2000, 3000, 5000, 10000]
)

# Token metrics
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

# Request counters
llm_requests_total = Counter('llm_requests_total', 'Total LLM requests')
llm_errors_total = Counter('llm_errors_total', 'Total LLM errors')
tts_requests_total = Counter('tts_requests_total', 'Total TTS requests')
tts_errors_total = Counter('tts_errors_total', 'Total TTS errors')

# TTS audio size
tts_audio_bytes = Histogram(
    'tts_audio_bytes',
    'TTS audio size in bytes',
    buckets=[1000, 5000, 10000, 25000, 50000, 100000, 250000, 500000]
)

# Conversation metrics
active_conversations = Gauge('active_conversations', 'Number of active conversation sessions')
reservations_created_total = Counter('reservations_created_total', 'Total reservations created')
reservations_cancelled_total = Counter('reservations_cancelled_total', 'Total reservations cancelled')

# Initialize OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# In-memory conversation storage (use Redis/database for production)
conversations: Dict[str, List[dict]] = {}
reservations: List[dict] = []

app = FastAPI(
    title="Concya Reservation Assistant",
    description="Fast AI reservation assistant with voice capabilities",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
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

# System prompt optimized for fast reservations
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

@app.get("/")
async def root():
    return {
        "service": "Concya Reservation Assistant",
        "status": "running",
        "endpoints": ["/conversation", "/speak", "/reservations"]
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "llm"}

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    logger.debug("📊 [METRICS] Metrics requested")
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/conversation")
async def conversation(request: ConversationRequest):
    """Process conversation and extract reservation intent"""
    
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
        # Fast GPT call with low max_tokens for speed
        logger.info(f"🤖 [LLM] Calling GPT-4o-mini (fast mode)...")
        llm_start = time.time()
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=80,  # Keep responses short for speed
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
            model="tts-1",  # Fast TTS model
            voice=request.voice,
            input=request.text,
            speed=1.1  # Slightly faster for efficiency
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
async def clear_session(session_id: str):
    """Clear conversation session"""
    
    if session_id in conversations:
        message_count = len(conversations[session_id])
        del conversations[session_id]
        active_conversations.dec()
        logger.info(f"🗑️  [SESSION] Cleared: {session_id[:16]}... ({message_count} messages)")
    else:
        logger.debug(f"🗑️  [SESSION] Clear requested for non-existent session: {session_id[:16]}...")
    
    return {"status": "cleared", "session_id": session_id}

def extract_reservation_intent(messages: List[dict]) -> Optional[dict]:
    """Extract reservation details from conversation"""
    
    conversation_text = " ".join([msg["content"] for msg in messages if msg["role"] == "user"])
    
    # Simple extraction (can be improved with NER or GPT function calling)
    data = {}
    
    # This is a placeholder - in production, use GPT function calling or NER
    # For now, return None (GPT will handle it conversationally)
    
    return data

def is_reservation_complete(data: Optional[dict]) -> bool:
    """Check if we have all required reservation info"""
    
    if not data:
        return False
    
    required = ["customer_name", "date", "time", "party_size"]
    return all(key in data and data[key] for key in required)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

