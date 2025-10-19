#!/bin/bash
# Simple deployment script for Concya

echo "🚀 Deploying Concya..."

# Build and run
docker build -t concya .
docker run -p 8000:8000 --env-file .env concya

echo "✅ Concya deployed on http://localhost:8000"
