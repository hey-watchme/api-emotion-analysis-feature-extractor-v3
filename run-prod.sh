#!/bin/bash

# Hume AI Emotion Recognition API - Production deployment script

set -e  # Exit on error

echo "🚀 Starting Hume AI API deployment..."

# Check current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "📍 Current directory: $(pwd)"

# Check .env file exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found!"
    echo "Please create .env file with required environment variables."
    exit 1
fi

echo "✅ .env file found"

# ECR authentication
echo "🔐 Logging into Amazon ECR..."
aws ecr get-login-password --region ap-southeast-2 | docker login --username AWS --password-stdin 754724220380.dkr.ecr.ap-southeast-2.amazonaws.com

echo "📥 Pulling latest image from ECR (forced)..."
docker pull --platform linux/arm64 754724220380.dkr.ecr.ap-southeast-2.amazonaws.com/watchme-emotion-analysis-hume:latest

# Verify pulled image
echo "✅ Image pulled successfully:"
docker images | grep watchme-emotion-analysis-hume | head -1

# Remove existing containers
echo "🗑️ Removing existing containers..."

# 1. Remove running containers
RUNNING_CONTAINERS=$(docker ps -q --filter "name=emotion-analysis-hume")
if [ ! -z "$RUNNING_CONTAINERS" ]; then
    echo "  Stopping running containers (emotion-analysis-hume)..."
    docker stop $RUNNING_CONTAINERS
fi

ALL_CONTAINERS=$(docker ps -aq --filter "name=emotion-analysis-hume")
if [ ! -z "$ALL_CONTAINERS" ]; then
    echo "  Removing all containers (emotion-analysis-hume)..."
    docker rm -f $ALL_CONTAINERS
fi

# 2. docker-compose cleanup
echo "  Running docker-compose down..."
docker-compose -f docker-compose.prod.yml down || true

echo "✅ Container cleanup completed"

# Start new container
echo "🚀 Starting new container..."
docker-compose -f docker-compose.prod.yml up -d

# Wait for container to start
echo "⏳ Waiting for container to start..."
sleep 10

# Check container status
if docker ps | grep -q emotion-analysis-hume; then
    echo "✅ Container is running"
    docker ps | grep emotion-analysis-hume
else
    echo "❌ Container failed to start"
    echo "Recent logs:"
    docker logs emotion-analysis-hume --tail 50 || true
    exit 1
fi

# Health check (Hume API is lightweight, should be quick)
echo "🏥 Running health check..."
echo "⏳ Waiting for API to be ready..."
for i in {1..12}; do
    if curl -f http://localhost:8019/health > /dev/null 2>&1; then
        echo "✅ Health check passed"
        echo "🎉 Deployment completed successfully!"
        exit 0
    fi
    echo "  Attempt $i/12 failed, retrying in 5 seconds..."
    sleep 5
done

echo "⚠️ Health check failed after 12 attempts (60 seconds)"
echo "Container logs:"
docker logs emotion-analysis-hume --tail 50
exit 1