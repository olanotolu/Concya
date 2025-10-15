# CUDA 12.3 + cuDNN 9 for L40S GPU
FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04

WORKDIR /app

# System dependencies (including sox for NeMo)
RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    git \
    python3-pip \
    python3-dev \
    build-essential \
    sox \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (install prerequisites first for sox compatibility)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir numpy typing_extensions && \
    pip install --no-cache-dir -r requirements.txt

# Note: Whisper model will be downloaded automatically on first startup
# This avoids build-time authentication issues

# Copy application code
COPY app.py .
COPY index.html .

# Environment variables (can be overridden in RunPod)
ENV WHISPER_MODEL=base
ENV WHISPER_LANGUAGE=auto
ENV ENABLE_DIARIZATION=true
ENV TARGET_LANGUAGE=""
ENV OPENAI_API_KEY=""
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

