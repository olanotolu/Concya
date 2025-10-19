from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from twilio.twiml.voice_response import VoiceResponse, Gather, Start, Stream
from dotenv import load_dotenv
from llm import ConcyaLLMClient
from tts import ConcyaTTSClient
from restaurant import RestaurantBookingSystem, ConversationManager
import os
from datetime import datetime
import time
import uuid
import logging
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("concya")

# Timing utilities
class TimingContext:
    def __init__(self, operation_name, conversation_id=None):
        self.operation_name = operation_name
        self.conversation_id = conversation_id or str(uuid.uuid4())[:8]
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.time()
        logger.info(f"⏱️ [{self.conversation_id}] START {self.operation_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        logger.info(".3f")

def log_latency(operation_name, duration, conversation_id=None):
    """Log latency with consistent formatting"""
    conv_id = conversation_id or "unknown"
    logger.info(".3f")

def get_conversation_id(request):
    """Extract or generate conversation ID from request"""
    # Try to get from Twilio CallSid, or generate new
    call_sid = request.headers.get('X-Twilio-CallSid') or getattr(request, 'headers', {}).get('X-Twilio-CallSid')
    if call_sid:
        return call_sid[-8:]  # Last 8 chars of CallSid
    return str(uuid.uuid4())[:8]

load_dotenv()

app = FastAPI(title="Concya Twilio Gateway", version="1.0.0")

# Mount static files for audio serving
app.mount("/audio", StaticFiles(directory="audio_cache"), name="audio")

# Initialize clients
llm_client = ConcyaLLMClient()
tts_client = ConcyaTTSClient()
booking_system = RestaurantBookingSystem()
conversation_manager = ConversationManager()

# WebSocket connection to WhisperLiveKit server
whisper_ws_url = os.getenv("WHISPER_SERVER_URL", "wss://your-runpod-url.proxy.runpod.net/media")
active_whisper_connections = {}

@app.get("/")
async def root():
    return {
        "status": "healthy",
        "service": "Concya Twilio Gateway",
        "version": "1.0.0",
        "active_connections": 0
    }

@app.post("/twilio")
async def handle_call(request: Request):
    conversation_id = get_conversation_id(request)
    total_start = time.time()

    logger.info(f"📞 [{conversation_id}] INCOMING CALL - Webhook received")

    response = VoiceResponse()

    # Use TTS for the restaurant greeting
    greeting_text = "Hello! Welcome to Bella Vista, where authentic Italian meets modern elegance. How can I help you with your reservation today?"

    with TimingContext("Greeting TTS Generation", conversation_id):
        greeting_audio_path = tts_client.generate_speech(greeting_text, voice="alloy")

    if greeting_audio_path:
        greeting_audio_url = f"https://53453cec9732.ngrok-free.app/audio/{os.path.basename(greeting_audio_path)}"
        response.play(greeting_audio_url)
        logger.info(f"🎵 [{conversation_id}] Playing greeting TTS: {greeting_audio_url}")
    else:
        # Fallback to text-to-speech
        response.say(greeting_text)

    # Connect to WhisperLiveKit Media Stream instead of using Gather
    # This will stream audio in real-time to our Whisper server
    start = Start()
    start.stream(url=whisper_ws_url)
    response.append(start)

    total_duration = time.time() - total_start
    logger.info(f"🏁 [{conversation_id}] END Webhook Processing ({total_duration:.3f}s)")

    return Response(content=str(response), media_type="text/xml")

@app.websocket("/ws/transcription/{call_sid}")
async def transcription_bridge(websocket: WebSocket, call_sid: str):
    """Bridge between Twilio and WhisperLiveKit - receives transcriptions"""
    await websocket.accept()
    conversation_id = call_sid[-8:]
    logger.info(f"🔗 [{conversation_id}] Transcription bridge connected")
    
    # Store connection
    active_whisper_connections[call_sid] = {
        "websocket": websocket,
        "connected_at": time.time()
    }
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("event") == "transcription":
                transcription_text = data["transcription"]["text"]
                logger.info(f"📝 [{conversation_id}] Received: {transcription_text}")
                
                # Get phone number from stored connection or default
                phone_number = data.get("phone_number", "unknown")
                
                # Process with conversation manager
                with TimingContext("LLM Processing", conversation_id):
                    ai_response, state = conversation_manager.process_conversation_turn(
                        phone_number, transcription_text, booking_system
                    )
                
                logger.info(f"🤖 [{conversation_id}] AI response: '{ai_response[:100]}...'")
                
                # Generate TTS and send back
                with TimingContext("Response TTS Generation", conversation_id):
                    audio_path = tts_client.generate_speech(ai_response, voice="alloy")
                
                if audio_path:
                    # Get ngrok URL from environment or use default
                    ngrok_url = os.getenv("PUBLIC_WEBHOOK_URL", "https://53453cec9732.ngrok-free.app")
                    audio_url = f"{ngrok_url}/audio/{os.path.basename(audio_path)}"
                    
                    await websocket.send_json({
                        "event": "response",
                        "audio_url": audio_url,
                        "text": ai_response
                    })
                    logger.info(f"🎵 [{conversation_id}] Sent response audio: {audio_url}")
                    
    except WebSocketDisconnect:
        logger.info(f"🔌 [{conversation_id}] Transcription bridge disconnected")
    except Exception as e:
        logger.error(f"❌ [{conversation_id}] Transcription bridge error: {e}")
    finally:
        # Cleanup connection
        if call_sid in active_whisper_connections:
            del active_whisper_connections[call_sid]

@app.post("/process_speech")
async def process_speech(request: Request):
    conversation_id = get_conversation_id(request)
    total_turn_start = time.time()

    logger.info(f"🎤 [{conversation_id}] SPEECH PROCESSING - Webhook received")

    form = await request.form()
    user_text = form.get("SpeechResult", "")
    stt_processing_time = time.time() - total_turn_start

    logger.info(f"🗣️ [{conversation_id}] User said: '{user_text}' (STT: {stt_processing_time:.3f}s)")

    # Check if user wants to end the call
    end_call_phrases = ["goodbye", "bye", "see you", "talk to you later", "hang up", "end call", "that's all"]
    if any(phrase in user_text.lower() for phrase in end_call_phrases):
        response = VoiceResponse()

        # Try TTS for goodbye message
        goodbye_text = "Goodbye! It was nice talking to you."
        audio_path = tts_client.generate_speech(goodbye_text, voice="alloy")

        if audio_path:
            audio_url = f"https://53453cec9732.ngrok-free.app/audio/{os.path.basename(audio_path)}"
            response.play(audio_url)
            print(f"🎵 Playing goodbye TTS: {audio_url}")
        else:
            response.say(goodbye_text)

        response.hangup()
        return Response(content=str(response), media_type="text/xml")

    # Use conversation manager to process the user's input
    # For now, assume we can extract phone number from request or use a default
    # In production, you'd get this from Twilio's request data
    phone_number = "+15551234567"  # Placeholder - should come from Twilio

    # Process through conversation manager
    with TimingContext("LLM Processing", conversation_id):
        ai_response, conversation_state = conversation_manager.process_conversation_turn(phone_number, user_text, booking_system)

    llm_processing_time = time.time() - (total_turn_start + stt_processing_time)
    logger.info(f"🤖 [{conversation_id}] AI response: '{ai_response[:100]}...' (LLM: {llm_processing_time:.3f}s)")
    logger.info(f"📊 [{conversation_id}] Conversation state: {conversation_state}")

    # Continue the conversation by gathering more speech
    response = VoiceResponse()

    # Try to generate TTS audio, fallback to text-to-speech if it fails
    with TimingContext("Response TTS Generation", conversation_id):
        audio_path = tts_client.generate_speech(ai_response, voice="alloy")

    if audio_path:
        # Use TTS audio with Play verb
        audio_url = f"https://53453cec9732.ngrok-free.app/audio/{os.path.basename(audio_path)}"
        response.play(audio_url)
        print(f"🎵 Playing TTS audio: {audio_url}")
    else:
        # Fallback to Twilio's text-to-speech
        response.say(ai_response)
        print("⚠️ TTS failed, using fallback text-to-speech")

    # Add another gather to continue the conversation with varied prompts
    gather = Gather(
        input="speech",
        action="/process_speech",
        language="en-US",
        speech_timeout="auto"
    )

    # Smart conversation continuation - adapt prompts based on context
    import random

    # Analyze the AI response to determine appropriate follow-up
    ai_lower = ai_response.lower()

    # Different prompt strategies based on response type
    if any(word in ai_lower for word in ["?", "what", "how", "tell me"]):
        # If AI asked a question, be very brief
        prompts = ["", "Go ahead", "I'm listening"]
        selected_prompt = random.choice(prompts + [""] * 4)  # Mostly silent
    elif any(word in ai_lower for word in ["!", "great", "wonderful", "amazing"]):
        # If AI is excited/positive, encourage more sharing
        prompts = ["Tell me more", "What else?", "Go on"]
        selected_prompt = random.choice(prompts)
    elif len(ai_response.split()) > 30:  # Long response
        # After detailed response, give space
        prompts = ["", "What do you think?", "Any questions?"]
        selected_prompt = random.choice(prompts + [""] * 3)
    else:
        # Default varied prompts for natural flow
        prompts = [
            "Go ahead",
            "I'm listening",
            "What would you like to know?",
            "Yes?",
            "Tell me more"
        ]
        selected_prompt = random.choice(prompts)

    # Use TTS for listening prompts too - consistent voice throughout
    if selected_prompt:
        with TimingContext("Prompt TTS Generation", conversation_id):
            prompt_audio_path = tts_client.generate_speech(selected_prompt, voice="alloy")
        if prompt_audio_path:
            prompt_audio_url = f"https://53453cec9732.ngrok-free.app/audio/{os.path.basename(prompt_audio_path)}"
            gather.play(prompt_audio_url)
            print(f"🎵 Playing prompt TTS: {prompt_audio_url}")
        else:
            # Fallback if TTS fails
            gather.say(selected_prompt)
    else:
        # For "silent" listening, use a very brief, subtle TTS sound
        with TimingContext("Silent Prompt TTS Generation", conversation_id):
            silent_audio_path = tts_client.generate_speech("...", voice="alloy")
        if silent_audio_path:
            silent_audio_url = f"https://53453cec9732.ngrok-free.app/audio/{os.path.basename(silent_audio_path)}"
            gather.play(silent_audio_url)
        else:
            # Ultimate fallback
            gather.say("...")

    response.append(gather)

    total_turn_duration = time.time() - total_turn_start
    logger.info(f"🏁 [{conversation_id}] TOTAL TURN: {total_turn_duration:.3f}s")

    return Response(content=str(response), media_type="text/xml")

@app.post("/test")
async def test_endpoint(request: Request):
    return {"message": "Test endpoint working", "method": request.method}

@app.post("/cleanup_audio")
async def cleanup_audio():
    """Clean up old audio files"""
    try:
        tts_client.cleanup_old_files()
        return {"message": "Audio cleanup completed"}
    except Exception as e:
        return {"error": f"Cleanup failed: {str(e)}"}

# Notification API Endpoints
@app.post("/api/send_reminder")
async def send_reminder(request: Request):
    """Send reminder for a booking"""
    try:
        data = await request.json()
        booking_id = data.get('booking_id')
        hours_before = data.get('hours_before', 24)

        if not booking_id:
            return {"error": "Booking ID required"}

        # Get booking details
        booking_result = booking_system.supabase_client.get_booking(booking_id)
        if not booking_result:
            return {"error": "Booking not found"}

        # Send reminder
        from restaurant.notifications import RestaurantNotificationService
        notification_service = RestaurantNotificationService()
        result = notification_service.send_booking_reminder(booking_result, hours_before)

        return {
            "success": result['email_sent'] or result['sms_sent'],
            "email_sent": result['email_sent'],
            "sms_sent": result['sms_sent'],
            "errors": result.get('errors', [])
        }

    except Exception as e:
        print(f"Send reminder API error: {e}")
        return {"error": str(e)}

# Dashboard API Endpoints
@app.get("/api/dashboard")
async def get_dashboard_data():
    """Get dashboard overview data"""
    try:
        # Get all bookings from Supabase
        result = booking_system.supabase_client.get_all_bookings()

        if not result.get('success', False):
            return {"error": "Failed to fetch bookings"}

        bookings = result.get('data', [])

        # Calculate stats
        total_bookings = len(bookings)
        total_guests = sum(booking.get('party_size', 0) for booking in bookings)
        avg_party_size = total_guests / total_bookings if total_bookings > 0 else 0

        # Today's bookings
        today = datetime.now().strftime('%Y-%m-%d')
        today_bookings = len([b for b in bookings if b.get('date') == today and b.get('status') == 'confirmed'])

        # Recent bookings (last 10, sorted by date/time)
        recent_bookings = sorted(
            [b for b in bookings if b.get('status') == 'confirmed'],
            key=lambda x: f"{x.get('date')} {x.get('time')}",
            reverse=True
        )[:10]

        return {
            "stats": {
                "total_bookings": total_bookings,
                "total_guests": total_guests,
                "today_bookings": today_bookings,
                "avg_party_size": avg_party_size
            },
            "recent_bookings": recent_bookings,
            "all_bookings": bookings
        }

    except Exception as e:
        print(f"Dashboard API error: {e}")
        return {"error": str(e)}

@app.get("/api/analytics")
async def get_analytics_data():
    """Get analytics data for charts"""
    try:
        result = booking_system.supabase_client.get_all_bookings()

        if not result.get('success', False):
            return {"error": "Failed to fetch bookings"}

        bookings = result.get('data', [])

        # Bookings by day of week
        dow_counts = [0] * 7  # Mon-Sun
        for booking in bookings:
            if booking.get('date') and booking.get('status') == 'confirmed':
                try:
                    date_obj = datetime.strptime(booking['date'], '%Y-%m-%d')
                    dow_counts[date_obj.weekday()] += 1
                except:
                    pass

        # Bookings by time slot
        time_slots = ['17:00', '18:00', '19:00', '20:00', '21:00', '22:00']
        time_counts = [0] * len(time_slots)

        for booking in bookings:
            if booking.get('time') and booking.get('status') == 'confirmed':
                booking_time = booking['time'][:5]  # Take HH:MM part
                if booking_time in time_slots:
                    idx = time_slots.index(booking_time)
                    time_counts[idx] += 1

        return {
            "bookings_by_dow": dow_counts,
            "bookings_by_time": time_counts,
            "time_slots": time_slots
        }

    except Exception as e:
        print(f"Analytics API error: {e}")
        return {"error": str(e)}

@app.put("/api/bookings")
async def update_booking(request: Request):
    """Update a booking"""
    try:
        data = await request.json()
        booking_id = data.get('id')

        if not booking_id:
            return {"error": "Booking ID required"}

        # Get original booking before update
        original_booking = booking_system.supabase_client.get_booking(booking_id)

        # Update booking in Supabase
        result = booking_system.supabase_client.update_booking(booking_id, data)

        if result.get('success'):
            # Send update notifications if status changed or important details changed
            try:
                from restaurant.notifications import RestaurantNotificationService
                notification_service = RestaurantNotificationService()

                change_type = 'modified'
                if data.get('status') == 'cancelled':
                    change_type = 'cancelled'
                elif original_booking and original_booking.get('status') != data.get('status'):
                    change_type = f"status changed to {data.get('status')}"

                updated_booking = {**original_booking, **data} if original_booking else data
                notification_result = notification_service.send_booking_update(updated_booking, change_type)

                print(f"📧 Update notifications sent: Email={notification_result['email_sent']}, SMS={notification_result['sms_sent']}")

            except Exception as e:
                print(f"⚠️ Update notification error: {e}")

            return {"success": True, "message": "Booking updated"}
        else:
            return {"error": result.get('message', 'Update failed')}

    except Exception as e:
        print(f"Update booking API error: {e}")
        return {"error": str(e)}

@app.delete("/api/bookings/{booking_id}")
async def cancel_booking(booking_id: str):
    """Cancel a booking"""
    try:
        result = booking_system.supabase_client.cancel_booking(booking_id)

        if result.get('success'):
            return {"success": True, "message": "Booking cancelled"}
        else:
            return {"error": result.get('message', 'Cancellation failed')}

    except Exception as e:
        print(f"Cancel booking API error: {e}")
        return {"error": str(e)}

# Serve dashboard
@app.get("/dashboard")
async def dashboard():
    """Serve the restaurant dashboard"""
    return FileResponse("restaurant/dashboard.html", media_type="text/html")
