"""
Hume AI Emotion Recognition API v3
Main FastAPI application
"""

import os
import json
import asyncio
import logging
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError

from app.models import (
    HealthResponse,
    AsyncProcessRequest,
    AsyncProcessResponse,
    ErrorResponse
)
from app.hume_provider import HumeProvider
from supabase_service import SupabaseService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# FastAPI application
app = FastAPI(
    title="Hume AI Emotion Recognition API",
    description="48-emotion analysis using Hume AI Speech Prosody, Vocal Burst, and Language models",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
hume_provider: Optional[HumeProvider] = None
supabase_service: Optional[SupabaseService] = None
sqs_client = None
s3_client = None

# SQS Queue URL
FEATURE_COMPLETED_QUEUE_URL = os.getenv(
    'FEATURE_COMPLETED_QUEUE_URL',
    'https://sqs.ap-southeast-2.amazonaws.com/754724220380/watchme-feature-completed-queue'
)

# S3 configuration
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'watchme-vault')
AWS_REGION = os.getenv('AWS_REGION', 'ap-southeast-2')


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global hume_provider, supabase_service, sqs_client, s3_client

    try:
        # Initialize Hume Provider
        hume_api_key = os.getenv('HUME_API_KEY')
        hume_secret_key = os.getenv('HUME_SECRET_KEY')

        if not hume_api_key or not hume_secret_key:
            logger.error("Hume API credentials not found in environment variables")
            raise ValueError("HUME_API_KEY and HUME_SECRET_KEY must be set")

        hume_provider = HumeProvider(hume_api_key, hume_secret_key)
        logger.info("Hume Provider initialized successfully")

        # Initialize Supabase
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')

        if supabase_url and supabase_key:
            supabase_service = SupabaseService(supabase_url, supabase_key)
            logger.info(f"Supabase initialized: {supabase_url}")
        else:
            logger.warning("Supabase credentials not found - running without database")

        # Initialize AWS clients
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')

        if aws_access_key and aws_secret_key:
            # S3 client
            s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=AWS_REGION
            )

            # SQS client
            sqs_client = boto3.client(
                'sqs',
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=AWS_REGION
            )
            logger.info("AWS clients initialized successfully")
        else:
            logger.warning("AWS credentials not found - running without AWS services")

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        # Continue running even if some services fail to initialize


@app.get("/", response_model=dict)
async def root():
    """Root endpoint with API information"""
    return {
        "service": "Hume AI Emotion Recognition API",
        "version": "3.0.0",
        "models": {
            "speech_prosody": "48 emotions from voice prosody",
            "vocal_burst": "48 emotions from non-linguistic vocalizations",
            "language": "53 emotions from text content"
        },
        "endpoints": {
            "health": "/health",
            "async_process": "/async-process",
            "docs": "/docs"
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    try:
        # Check service status
        is_healthy = hume_provider is not None

        return HealthResponse(
            status="healthy" if is_healthy else "degraded",
            service="Hume AI Emotion Recognition API",
            version="3.0.0",
            provider_loaded=hume_provider is not None,
            supabase_connected=supabase_service is not None,
            aws_connected=s3_client is not None
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unhealthy: {str(e)}"
        )


@app.post("/async-process",
          status_code=status.HTTP_202_ACCEPTED,
          response_model=AsyncProcessResponse)
async def async_process(
    request: AsyncProcessRequest,
    background_tasks: BackgroundTasks
):
    """
    Asynchronous emotion analysis endpoint
    Returns 202 Accepted immediately and processes in background
    """
    logger.info(f"Starting async processing for {request.device_id} at {request.recorded_at}")

    # Validate services
    if not hume_provider:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hume Provider not initialized"
        )

    if not supabase_service:
        logger.warning("Processing without database - results will not be saved")

    # Add background task
    background_tasks.add_task(
        process_emotion_analysis,
        request.file_path,
        request.device_id,
        request.recorded_at
    )

    return AsyncProcessResponse(
        status="accepted",
        message="Emotion analysis started in background",
        device_id=request.device_id,
        recorded_at=request.recorded_at
    )


async def process_emotion_analysis(
    file_path: str,
    device_id: str,
    recorded_at: str
):
    """
    Background task for emotion analysis
    """
    start_time = datetime.utcnow()
    job_id = None

    try:
        # Update status to processing
        if supabase_service:
            await supabase_service.update_emotion_status(
                device_id, recorded_at, "processing"
            )

        # Generate presigned URL for S3 file
        if not s3_client:
            raise Exception("S3 client not initialized")

        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET_NAME, 'Key': file_path},
            ExpiresIn=3600
        )
        logger.info(f"Generated presigned URL for {file_path}")

        # Submit job to Hume API
        job_id = await hume_provider.create_job(
            audio_url=presigned_url,
            language="ja"  # Japanese language for better STT
        )
        logger.info(f"Created Hume job: {job_id}")

        # Poll for job completion
        result = await hume_provider.wait_for_job(job_id)

        if not result:
            raise Exception("Job completed but no results returned")

        # Process and save results
        processing_time = (datetime.utcnow() - start_time).total_seconds()

        # Parse Hume results
        parsed_result = await hume_provider.parse_results(result)

        # Check if we got valid emotion data
        if not parsed_result or parsed_result.get('total_segments', 0) == 0:
            # Low quality audio - no emotion data available
            logger.warning(f"No emotion data extracted for {file_path} - likely low quality audio")

            if supabase_service:
                # Save empty result with error flag
                await supabase_service.save_emotion_features(
                    device_id=device_id,
                    recorded_at=recorded_at,
                    emotion_data={
                        "provider": "hume",
                        "version": "3.0.0",
                        "error": "No emotion data extracted - audio quality too low",
                        "processing_time": processing_time
                    }
                )

                await supabase_service.update_emotion_status(
                    device_id, recorded_at, "failed"
                )
        else:
            # Valid emotion data
            logger.info(f"Extracted {parsed_result['total_segments']} segments with emotion data")

            if supabase_service:
                # Save to database
                await supabase_service.save_emotion_features(
                    device_id=device_id,
                    recorded_at=recorded_at,
                    emotion_data=parsed_result
                )

                await supabase_service.update_emotion_status(
                    device_id, recorded_at, "completed"
                )

        # Send SQS notification
        if sqs_client:
            await send_completion_notification(
                device_id=device_id,
                recorded_at=recorded_at,
                status="completed" if parsed_result else "failed",
                segments=parsed_result.get('total_segments', 0) if parsed_result else 0
            )

        logger.info(f"Completed emotion analysis for {device_id} in {processing_time:.2f}s")

    except Exception as e:
        logger.error(f"Failed to process {file_path}: {str(e)}")

        # Update status to failed
        if supabase_service:
            await supabase_service.update_emotion_status(
                device_id, recorded_at, "failed"
            )

            # Save error information
            await supabase_service.save_emotion_features(
                device_id=device_id,
                recorded_at=recorded_at,
                emotion_data={
                    "provider": "hume",
                    "version": "3.0.0",
                    "error": str(e),
                    "job_id": job_id
                }
            )

        # Send error notification
        if sqs_client:
            await send_completion_notification(
                device_id=device_id,
                recorded_at=recorded_at,
                status="failed",
                error=str(e)
            )


async def send_completion_notification(
    device_id: str,
    recorded_at: str,
    status: str,
    segments: int = 0,
    error: Optional[str] = None
):
    """Send completion notification to SQS"""
    try:
        message = {
            "device_id": device_id,
            "recorded_at": recorded_at,
            "feature_type": "emotion",
            "status": status,
            "provider": "hume",
            "segments": segments,
            "timestamp": datetime.utcnow().isoformat()
        }

        if error:
            message["error"] = error

        sqs_client.send_message(
            QueueUrl=FEATURE_COMPLETED_QUEUE_URL,
            MessageBody=json.dumps(message)
        )
        logger.info(f"Sent SQS notification for {device_id}: {status}")

    except Exception as e:
        logger.error(f"Failed to send SQS notification: {e}")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc)
        ).dict()
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("API_PORT", 8018)),
        reload=True,
        log_level="info"
    )