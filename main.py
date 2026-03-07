"""
Hume AI Emotion Recognition API v3
Main FastAPI application - queue-first operation
"""

import os
import json
import asyncio
import hashlib
import logging
import time
import threading
from typing import Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, status
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(
    title="Hume AI Emotion Recognition API",
    description="48-emotion analysis using Hume AI Speech Prosody, Vocal Burst, and Language models",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

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

FEATURE_COMPLETED_QUEUE_URL = os.getenv(
    'FEATURE_COMPLETED_QUEUE_URL',
    'https://sqs.ap-southeast-2.amazonaws.com/754724220380/watchme-feature-completed-queue'
)

S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'watchme-vault')
AWS_REGION = os.getenv('AWS_REGION', 'ap-southeast-2')


def _read_bool(env_name: str, default: bool = False) -> bool:
    raw_value = os.environ.get(env_name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _read_max_workers(env_name: str, default: int = 1) -> int:
    raw_value = os.environ.get(env_name, str(default))
    try:
        return max(1, int(raw_value))
    except ValueError:
        return default


SER_JOB_QUEUE_URL = os.environ.get(
    "SER_JOB_QUEUE_URL",
    "https://sqs.ap-southeast-2.amazonaws.com/754724220380/watchme-ser-job-queue-v1.fifo",
)
SER_JOB_QUEUE_ENABLED = _read_bool("SER_JOB_QUEUE_ENABLED", True)
SER_ALLOW_IN_PROCESS_FALLBACK = _read_bool("SER_ALLOW_IN_PROCESS_FALLBACK", False)
SER_JOB_QUEUE_WAIT_SECONDS = max(1, min(20, int(os.environ.get("SER_JOB_QUEUE_WAIT_SECONDS", "20"))))
SER_JOB_QUEUE_VISIBILITY_TIMEOUT = max(60, int(os.environ.get("SER_JOB_QUEUE_VISIBILITY_TIMEOUT", "600")))
SER_ASYNC_JOB_WORKERS = _read_max_workers("SER_ASYNC_JOB_WORKERS", 1)

ser_async_executor = ThreadPoolExecutor(max_workers=SER_ASYNC_JOB_WORKERS)
ser_queue_worker_stop_event = threading.Event()
ser_queue_worker_thread: Optional[threading.Thread] = None


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global hume_provider, supabase_service, sqs_client, s3_client
    global ser_queue_worker_thread

    try:
        hume_api_key = os.getenv('HUME_API_KEY')
        hume_secret_key = os.getenv('HUME_SECRET_KEY')

        if not hume_api_key or not hume_secret_key:
            logger.error("Hume API credentials not found in environment variables")
            raise ValueError("HUME_API_KEY and HUME_SECRET_KEY must be set")

        hume_provider = HumeProvider(hume_api_key, hume_secret_key)
        logger.info("Hume Provider initialized successfully")

        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')

        if supabase_url and supabase_key:
            supabase_service = SupabaseService(supabase_url, supabase_key)
            logger.info(f"Supabase initialized: {supabase_url}")
        else:
            logger.warning("Supabase credentials not found - running without database")

        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')

        if aws_access_key and aws_secret_key:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=AWS_REGION
            )
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

    if SER_JOB_QUEUE_ENABLED and SER_JOB_QUEUE_URL and sqs_client:
        ser_queue_worker_stop_event.clear()
        ser_queue_worker_thread = threading.Thread(
            target=_consume_ser_job_queue,
            name="ser-job-queue-worker",
            daemon=True,
        )
        ser_queue_worker_thread.start()
        logger.info(f"SER queue worker started: {SER_JOB_QUEUE_URL}")
    else:
        logger.info("SER queue worker disabled")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop queue worker thread and executor on shutdown"""
    ser_queue_worker_stop_event.set()
    if ser_queue_worker_thread and ser_queue_worker_thread.is_alive():
        ser_queue_worker_thread.join(timeout=2)
    ser_async_executor.shutdown(wait=False, cancel_futures=False)


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


@app.post("/async-process", status_code=status.HTTP_202_ACCEPTED)
async def async_process(request: AsyncProcessRequest):
    """
    Queue-first async endpoint.
    Enqueues to SER job queue and returns 202.
    Falls back to in-process executor only when explicitly allowed.
    """
    logger.info(f"async-process request: {request.device_id} at {request.recorded_at}")

    if not hume_provider:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hume Provider not initialized"
        )

    if not SER_JOB_QUEUE_ENABLED or not SER_JOB_QUEUE_URL or not sqs_client:
        if not SER_ALLOW_IN_PROCESS_FALLBACK:
            raise HTTPException(status_code=503, detail="SER queue mode is disabled or misconfigured")
        if supabase_service:
            await supabase_service.update_emotion_status(request.device_id, request.recorded_at, "processing")
        ser_async_executor.submit(
            _run_process_in_background,
            request.file_path, request.device_id, request.recorded_at
        )
        return {
            "status": "accepted",
            "message": "Processing started in background",
            "transport": "in_process_executor",
            "device_id": request.device_id,
            "recorded_at": request.recorded_at,
        }

    try:
        if supabase_service:
            await supabase_service.update_emotion_status(request.device_id, request.recorded_at, "queued")
        _enqueue_ser_job(
            file_path=request.file_path,
            device_id=request.device_id,
            recorded_at=request.recorded_at,
            trigger_source="ser-worker",
        )
    except Exception as e:
        logger.error(f"Failed to enqueue SER job: {e}")
        if not SER_ALLOW_IN_PROCESS_FALLBACK:
            raise HTTPException(status_code=503, detail="Failed to enqueue SER job")
        ser_async_executor.submit(
            _run_process_in_background,
            request.file_path, request.device_id, request.recorded_at
        )
        return {
            "status": "accepted",
            "message": "Processing started in background (fallback)",
            "transport": "in_process_executor",
            "device_id": request.device_id,
            "recorded_at": request.recorded_at,
        }

    return {
        "status": "accepted",
        "message": "Processing queued",
        "transport": "sqs",
        "device_id": request.device_id,
        "recorded_at": request.recorded_at,
    }


def _enqueue_ser_job(*, file_path: str, device_id: str, recorded_at: str, trigger_source: str) -> None:
    """Enqueue an emotion analysis job to the SER FIFO queue."""
    payload = {
        "file_path": file_path,
        "device_id": device_id,
        "recorded_at": recorded_at,
        "feature_type": "emotion",
        "trigger_source": trigger_source,
        "queued_at": int(time.time()),
    }

    send_kwargs = {
        "QueueUrl": SER_JOB_QUEUE_URL,
        "MessageBody": json.dumps(payload),
    }

    if SER_JOB_QUEUE_URL.endswith(".fifo"):
        dedupe_input = f"{device_id}:{recorded_at}:{file_path}:emotion"
        send_kwargs["MessageGroupId"] = f"{device_id}-emotion"
        send_kwargs["MessageDeduplicationId"] = hashlib.sha256(dedupe_input.encode("utf-8")).hexdigest()[:80]

    sqs_client.send_message(**send_kwargs)
    logger.info(f"Enqueued SER job: {device_id}/{recorded_at}")


def _consume_ser_job_queue() -> None:
    """Long-running thread that polls the SER job queue and processes messages."""
    logger.info("SER queue consumer loop started")

    while not ser_queue_worker_stop_event.is_set():
        try:
            response = sqs_client.receive_message(
                QueueUrl=SER_JOB_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=SER_JOB_QUEUE_WAIT_SECONDS,
                VisibilityTimeout=SER_JOB_QUEUE_VISIBILITY_TIMEOUT,
            )
            messages = response.get("Messages", [])
            if not messages:
                continue

            for message in messages:
                receipt_handle = message["ReceiptHandle"]
                body = json.loads(message["Body"])

                file_path = body["file_path"]
                device_id = body["device_id"]
                recorded_at = body["recorded_at"]

                try:
                    asyncio.run(process_emotion_analysis(file_path, device_id, recorded_at))
                    sqs_client.delete_message(QueueUrl=SER_JOB_QUEUE_URL, ReceiptHandle=receipt_handle)
                    logger.info(f"SER queue job done: {device_id}/{recorded_at}")
                except Exception as e:
                    logger.error(f"SER queue job failed (will retry): {device_id}/{recorded_at} - {e}")

        except Exception as e:
            logger.error(f"SER queue consumer error: {e}")
            time.sleep(2)


def _run_process_in_background(file_path: str, device_id: str, recorded_at: str):
    """Wrapper for ThreadPoolExecutor fallback path."""
    try:
        asyncio.run(process_emotion_analysis(file_path, device_id, recorded_at))
    except Exception as e:
        logger.error(f"Background runner crashed for {device_id}/{recorded_at}: {e}")


async def process_emotion_analysis(
    file_path: str,
    device_id: str,
    recorded_at: str
):
    """Core emotion analysis logic using Hume AI."""
    start_time = datetime.utcnow()
    job_id = None

    try:
        if supabase_service:
            await supabase_service.update_emotion_status(
                device_id, recorded_at, "processing"
            )

        if not s3_client:
            raise Exception("S3 client not initialized")

        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET_NAME, 'Key': file_path},
            ExpiresIn=3600
        )
        logger.info(f"Generated presigned URL for {file_path}")

        job_id = await hume_provider.create_job(
            audio_url=presigned_url,
            language="ja"
        )
        logger.info(f"Created Hume job: {job_id}")

        result = await hume_provider.wait_for_job(job_id)

        if not result:
            raise Exception("Job completed but no results returned")

        processing_time = (datetime.utcnow() - start_time).total_seconds()
        parsed_result = await hume_provider.parse_results(result)

        if not parsed_result or parsed_result.get('total_segments', 0) == 0:
            logger.warning(f"No emotion data extracted for {file_path} - likely low quality audio")

            if supabase_service:
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
            logger.info(f"Extracted {parsed_result['total_segments']} segments with emotion data")

            if supabase_service:
                await supabase_service.save_emotion_features(
                    device_id=device_id,
                    recorded_at=recorded_at,
                    emotion_data=parsed_result
                )
                await supabase_service.update_emotion_status(
                    device_id, recorded_at, "completed"
                )

        if sqs_client:
            _send_completion_notification(
                device_id=device_id,
                recorded_at=recorded_at,
                notify_status="completed" if parsed_result else "failed",
                segments=parsed_result.get('total_segments', 0) if parsed_result else 0
            )

        logger.info(f"Completed emotion analysis for {device_id} in {processing_time:.2f}s")

    except Exception as e:
        logger.error(f"Failed to process {file_path}: {str(e)}")

        if supabase_service:
            await supabase_service.update_emotion_status(
                device_id, recorded_at, "failed"
            )
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

        if sqs_client:
            _send_completion_notification(
                device_id=device_id,
                recorded_at=recorded_at,
                notify_status="failed",
                error=str(e)
            )


def _send_completion_notification(
    device_id: str,
    recorded_at: str,
    notify_status: str,
    segments: int = 0,
    error: Optional[str] = None
):
    """Send completion notification to feature-completed-queue (synchronous)."""
    try:
        message = {
            "device_id": device_id,
            "recorded_at": recorded_at,
            "feature_type": "emotion",
            "status": notify_status,
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
        logger.info(f"Sent SQS notification for {device_id}: {notify_status}")

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