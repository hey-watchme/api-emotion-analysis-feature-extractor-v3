"""
Pydantic models for Hume AI Emotion Recognition API
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(description="Service health status")
    service: str = Field(description="Service name")
    version: str = Field(description="API version")
    provider_loaded: bool = Field(description="Hume provider status")
    supabase_connected: bool = Field(description="Database connection status")
    aws_connected: bool = Field(description="AWS services status")


class AsyncProcessRequest(BaseModel):
    """Asynchronous processing request"""
    file_path: str = Field(description="S3 file path")
    device_id: str = Field(description="Device identifier")
    recorded_at: str = Field(description="Recording timestamp")


class AsyncProcessResponse(BaseModel):
    """Asynchronous processing response"""
    status: str = Field(description="Processing status")
    message: str = Field(description="Status message")
    device_id: str = Field(description="Device identifier")
    recorded_at: str = Field(description="Recording timestamp")


class ErrorResponse(BaseModel):
    """Error response"""
    error: str = Field(description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")


class EmotionScore(BaseModel):
    """Single emotion score"""
    name: str = Field(description="Emotion name")
    score: float = Field(description="Emotion score (0.0-1.0)")


class TimeRange(BaseModel):
    """Time range for a segment"""
    begin: float = Field(description="Start time in seconds")
    end: float = Field(description="End time in seconds")


class ProsodySegment(BaseModel):
    """Speech prosody segment"""
    segment_id: int = Field(description="Segment identifier")
    time: TimeRange = Field(description="Time range")
    text: str = Field(description="Transcribed text")
    confidence: float = Field(description="Transcription confidence")
    emotions: Dict[str, float] = Field(description="48 emotion scores")
    dominant_emotion: Optional[Dict[str, Any]] = Field(None, description="Highest scoring emotion")


class BurstSegment(BaseModel):
    """Vocal burst segment"""
    segment_id: int = Field(description="Segment identifier")
    time: TimeRange = Field(description="Time range")
    emotions: Dict[str, float] = Field(description="48 emotion scores")
    dominant_emotion: Optional[Dict[str, Any]] = Field(None, description="Highest scoring emotion")


class LanguageSegment(BaseModel):
    """Language emotion segment"""
    segment_id: int = Field(description="Segment identifier")
    text: str = Field(description="Text content")
    position: Dict[str, int] = Field(description="Text position")
    emotions: Dict[str, float] = Field(description="53 emotion scores")
    dominant_emotion: Optional[Dict[str, Any]] = Field(None, description="Highest scoring emotion")


class HumeEmotionResult(BaseModel):
    """Complete Hume emotion analysis result"""
    provider: str = Field(default="hume", description="Provider name")
    version: str = Field(default="3.0.0", description="API version")
    job_id: Optional[str] = Field(None, description="Hume job ID")
    timestamp: str = Field(description="Processing timestamp")
    confidence: Optional[float] = Field(None, description="Overall confidence")
    detected_language: Optional[str] = Field(None, description="Detected language")
    total_segments: int = Field(description="Total number of segments across all models")

    speech_prosody: Optional[Dict[str, Any]] = Field(None, description="Speech prosody results")
    vocal_burst: Optional[Dict[str, Any]] = Field(None, description="Vocal burst results")
    language: Optional[Dict[str, Any]] = Field(None, description="Language emotion results")

    processing_time: Optional[float] = Field(None, description="Processing time in seconds")
    error: Optional[str] = Field(None, description="Error message if failed")