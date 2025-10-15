#!/bin/bash

# Concya - Unified Build & Push Script
# Builds and pushes the unified STT + LLM + TTS service

set -e

echo "🚀 Concya - Unified Build & Push Script"
echo "======================================"

# Docker Hub username
DOCKER_USER="olaoluwasubomi"
IMAGE_NAME="concya"
TAG="latest"

echo "📦 Building unified Concya service..."
echo ""

# Build for AMD64 (RunPod compatibility)
echo "🔨 Building Docker image..."
docker buildx build \
    --platform linux/amd64 \
    -t ${DOCKER_USER}/${IMAGE_NAME}:${TAG} \
    --push \
    .

echo ""
echo "✅ Image built and pushed successfully!"
echo ""
echo "🎉 Deployment ready!"
echo ""
echo "📋 Next steps:"
echo "1. Go to RunPod and create/update your pod"
echo "2. Use image: ${DOCKER_USER}/${IMAGE_NAME}:${TAG}"
echo "3. GPU: L40S (or similar)"
echo "4. Memory: 16GB minimum"
echo "5. Port: 8000"
echo "6. Environment variables:"
echo "   - OPENAI_API_KEY=your-key-here"
echo "   - WHISPER_MODEL=base (optional)"
echo "   - ENABLE_DIARIZATION=true (optional)"
echo ""
echo "7. Access your pod URL to use Concya!"
echo ""
echo "✨ Done!"
