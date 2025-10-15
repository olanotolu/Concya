"""
Concya Metrics - Centralized Prometheus Metrics
Prevents duplicate metric registration by defining all metrics in one place
"""

from prometheus_client import Counter, Histogram, Gauge

# ═══════════════════════════════════════════════════════════════
# STT METRICS
# ═══════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════
# LLM METRICS
# ═══════════════════════════════════════════════════════════════

llm_requests_total = Counter('llm_requests_total', 'Total LLM conversation requests')
llm_errors_total = Counter('llm_errors_total', 'Total LLM errors')

llm_latency_ms = Histogram(
    'llm_latency_ms',
    'LLM response latency in milliseconds',
    buckets=[100, 250, 500, 1000, 2000, 5000, 10000, 20000, 30000]
)

llm_tokens_prompt = Histogram(
    'llm_tokens_prompt',
    'Number of tokens in LLM prompt',
    buckets=[10, 50, 100, 250, 500, 1000, 2000, 4000]
)

llm_tokens_completion = Histogram(
    'llm_tokens_completion',
    'Number of tokens in LLM completion',
    buckets=[10, 50, 100, 250, 500, 1000, 2000]
)

# ═══════════════════════════════════════════════════════════════
# TTS METRICS
# ═══════════════════════════════════════════════════════════════

tts_requests_total = Counter('tts_requests_total', 'Total TTS requests')
tts_errors_total = Counter('tts_errors_total', 'Total TTS errors')

tts_latency_ms = Histogram(
    'tts_latency_ms',
    'TTS generation latency in milliseconds',
    buckets=[100, 250, 500, 1000, 2000, 5000, 10000]
)

tts_audio_bytes = Histogram(
    'tts_audio_bytes',
    'Size of generated TTS audio in bytes',
    buckets=[1000, 5000, 10000, 50000, 100000, 500000, 1000000]
)

# ═══════════════════════════════════════════════════════════════
# WEBSOCKET METRICS
# ═══════════════════════════════════════════════════════════════

websocket_connections_active = Gauge(
    'websocket_connections_active',
    'Number of active WebSocket connections'
)

websocket_messages_received = Counter(
    'websocket_messages_received',
    'Total WebSocket messages received'
)

websocket_messages_sent = Counter(
    'websocket_messages_sent',
    'Total WebSocket messages sent'
)

# ═══════════════════════════════════════════════════════════════
# RESERVATION METRICS
# ═══════════════════════════════════════════════════════════════

reservations_created_total = Counter(
    'reservations_created_total',
    'Total reservations created'
)

reservations_cancelled_total = Counter(
    'reservations_cancelled_total',
    'Total reservations cancelled'
)

reservations_active = Gauge(
    'reservations_active',
    'Number of active reservations'
)

# ═══════════════════════════════════════════════════════════════
# TWILIO METRICS
# ═══════════════════════════════════════════════════════════════

twilio_calls_total = Counter(
    'twilio_calls_total',
    'Total Twilio voice calls received'
)

twilio_calls_active = Gauge(
    'twilio_calls_active',
    'Number of active Twilio calls'
)

twilio_call_duration_seconds = Histogram(
    'twilio_call_duration_seconds',
    'Duration of Twilio calls in seconds',
    buckets=[5, 15, 30, 60, 120, 300, 600]
)

twilio_audio_latency_ms = Histogram(
    'twilio_audio_latency_ms',
    'Twilio audio round-trip latency (STT + LLM + TTS) in milliseconds',
    buckets=[500, 1000, 1500, 2000, 3000, 5000, 10000]
)

