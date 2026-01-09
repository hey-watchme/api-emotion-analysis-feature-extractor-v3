"""
Hume AI Provider
Handles all interactions with Hume API
"""

import os
import json
import time
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import base64

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class HumeProvider:
    """Provider for Hume AI emotion analysis"""

    def __init__(self, api_key: str, secret_key: str):
        """
        Initialize Hume Provider

        Args:
            api_key: Hume API key
            secret_key: Hume Secret key
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://api.hume.ai/v0/batch"

        # Hume API uses X-Hume-Api-Key header for authentication
        self.headers = {
            "X-Hume-Api-Key": api_key,
            "Content-Type": "application/json"
        }

        # Polling configuration
        self.poll_interval = int(os.getenv("HUME_POLL_INTERVAL", 3))
        self.max_poll_attempts = int(os.getenv("HUME_MAX_POLL_ATTEMPTS", 40))
        self.confidence_threshold = float(os.getenv("HUME_CONFIDENCE_THRESHOLD", 0.5))

    async def create_job(
        self,
        audio_url: str,
        language: str = "ja"
    ) -> str:
        """
        Create a new emotion analysis job

        Args:
            audio_url: Presigned URL for audio file
            language: Language code for transcription

        Returns:
            Job ID
        """
        # Prepare request body with all 3 models
        request_body = {
            "models": {
                "prosody": {
                    "granularity": "utterance",
                    "identify_speakers": False
                },
                "burst": {},  # Vocal burst detection
                "language": {}  # Text emotion analysis
            },
            "transcription": {
                "language": language,
                "confidence_threshold": self.confidence_threshold
            },
            "urls": [audio_url]
        }

        try:
            # Make API request
            response = requests.post(
                f"{self.base_url}/jobs",
                headers=self.headers,
                json=request_body,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Failed to create job: {response.status_code} - {response.text}")
                raise Exception(f"Hume API error: {response.status_code}")

            result = response.json()
            job_id = result.get("job_id")

            if not job_id:
                raise Exception("No job_id in response")

            logger.info(f"Created Hume job: {job_id}")
            return job_id

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise Exception(f"Failed to create Hume job: {str(e)}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get job status

        Args:
            job_id: Hume job ID

        Returns:
            Job status information
        """
        try:
            response = requests.get(
                f"{self.base_url}/jobs/{job_id}",
                headers=self.headers,
                timeout=30
            )

            if response.status_code != 200:
                raise Exception(f"Failed to get job status: {response.status_code}")

            return response.json()

        except Exception as e:
            logger.error(f"Failed to get job status: {e}")
            raise

    async def wait_for_job(
        self,
        job_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Poll and wait for job completion

        Args:
            job_id: Hume job ID

        Returns:
            Job results or None if failed
        """
        attempts = 0

        while attempts < self.max_poll_attempts:
            try:
                # Get job status
                status_response = await self.get_job_status(job_id)
                state = status_response.get("state", {})
                status = state.get("status")

                logger.info(f"Job {job_id} status: {status} (attempt {attempts + 1})")

                if status == "COMPLETED":
                    # Get predictions
                    return await self.get_job_predictions(job_id)

                elif status == "FAILED":
                    logger.error(f"Job {job_id} failed")
                    return None

                # Wait before next poll
                await asyncio.sleep(self.poll_interval)
                attempts += 1

            except Exception as e:
                logger.error(f"Error polling job {job_id}: {e}")
                attempts += 1
                await asyncio.sleep(self.poll_interval)

        logger.error(f"Job {job_id} timed out after {attempts} attempts")
        return None

    async def get_job_predictions(self, job_id: str) -> Dict[str, Any]:
        """
        Get job predictions/results

        Args:
            job_id: Hume job ID

        Returns:
            Prediction results
        """
        try:
            response = requests.get(
                f"{self.base_url}/jobs/{job_id}/predictions",
                headers=self.headers,
                timeout=60  # Longer timeout for large results
            )

            if response.status_code != 200:
                raise Exception(f"Failed to get predictions: {response.status_code}")

            return response.json()

        except Exception as e:
            logger.error(f"Failed to get predictions: {e}")
            raise

    async def parse_results(self, raw_results: Any) -> Optional[Dict[str, Any]]:
        """
        Parse Hume API results into structured format

        Args:
            raw_results: Raw API response

        Returns:
            Parsed emotion data or None if no valid data
        """
        try:
            # Navigate to predictions
            if not raw_results or not isinstance(raw_results, list):
                return None

            first_result = raw_results[0] if raw_results else {}
            results = first_result.get("results", {})
            predictions = results.get("predictions", [])

            if not predictions:
                logger.warning("No predictions in results")
                return None

            first_prediction = predictions[0]
            models = first_prediction.get("models", {})

            # Initialize result structure
            parsed = {
                "provider": "hume",
                "version": "3.0.0",
                "job_id": None,  # Will be set by caller
                "timestamp": datetime.utcnow().isoformat(),
                "total_segments": 0
            }

            # Parse Speech Prosody results
            prosody = models.get("prosody", {})
            if prosody:
                parsed["speech_prosody"] = self._parse_prosody(prosody)
                parsed["total_segments"] += parsed["speech_prosody"].get("total_segments", 0)

                # Extract metadata
                metadata = prosody.get("metadata", {})
                parsed["confidence"] = metadata.get("confidence", 0.0)
                parsed["detected_language"] = metadata.get("detected_language")

            # Parse Vocal Burst results
            burst = models.get("burst", {})
            if burst:
                parsed["vocal_burst"] = self._parse_burst(burst)
                parsed["total_segments"] += parsed["vocal_burst"].get("total_segments", 0)

            # Parse Language results
            language = models.get("language", {})
            if language:
                parsed["language"] = self._parse_language(language)
                parsed["total_segments"] += parsed["language"].get("total_segments", 0)

            # Check if we got any valid data
            if parsed["total_segments"] == 0:
                logger.warning("No emotion segments extracted")
                return None

            return parsed

        except Exception as e:
            logger.error(f"Failed to parse results: {e}")
            return None

    def _parse_prosody(self, prosody_data: Dict) -> Dict:
        """Parse speech prosody results"""
        result = {
            "total_segments": 0,
            "segments": []
        }

        grouped = prosody_data.get("grouped_predictions", [])
        if not grouped:
            return result

        predictions = grouped[0].get("predictions", []) if grouped else []

        for idx, pred in enumerate(predictions):
            segment = {
                "segment_id": idx + 1,
                "time": pred.get("time", {}),
                "text": pred.get("text", ""),
                "confidence": pred.get("confidence", 0.0),
                "emotions": {}
            }

            # Extract emotion scores
            emotions = pred.get("emotions", [])
            for emotion in emotions:
                name = emotion.get("name")
                score = emotion.get("score", 0.0)
                if name:
                    segment["emotions"][name] = score

            # Find dominant emotion
            if segment["emotions"]:
                dominant = max(segment["emotions"].items(), key=lambda x: x[1])
                segment["dominant_emotion"] = {
                    "name": dominant[0],
                    "score": dominant[1]
                }

            result["segments"].append(segment)

        result["total_segments"] = len(result["segments"])
        return result

    def _parse_burst(self, burst_data: Dict) -> Dict:
        """Parse vocal burst results"""
        result = {
            "total_segments": 0,
            "segments": []
        }

        grouped = burst_data.get("grouped_predictions", [])
        if not grouped:
            return result

        predictions = grouped[0].get("predictions", []) if grouped else []

        for idx, pred in enumerate(predictions):
            segment = {
                "segment_id": idx + 1,
                "time": pred.get("time", {}),
                "emotions": {}
            }

            # Extract emotion scores
            emotions = pred.get("emotions", [])
            for emotion in emotions:
                name = emotion.get("name")
                score = emotion.get("score", 0.0)
                if name:
                    segment["emotions"][name] = score

            # Find dominant emotion
            if segment["emotions"]:
                dominant = max(segment["emotions"].items(), key=lambda x: x[1])
                segment["dominant_emotion"] = {
                    "name": dominant[0],
                    "score": dominant[1]
                }

            result["segments"].append(segment)

        result["total_segments"] = len(result["segments"])
        return result

    def _parse_language(self, language_data: Dict) -> Dict:
        """Parse language emotion results"""
        result = {
            "total_segments": 0,
            "segments": []
        }

        grouped = language_data.get("grouped_predictions", [])
        if not grouped:
            return result

        predictions = grouped[0].get("predictions", []) if grouped else []

        for idx, pred in enumerate(predictions):
            segment = {
                "segment_id": idx + 1,
                "text": pred.get("text", ""),
                "position": pred.get("position", {}),  # Text position instead of time
                "emotions": {}
            }

            # Extract emotion scores
            emotions = pred.get("emotions", [])
            for emotion in emotions:
                name = emotion.get("name")
                score = emotion.get("score", 0.0)
                if name:
                    segment["emotions"][name] = score

            # Find dominant emotion
            if segment["emotions"]:
                dominant = max(segment["emotions"].items(), key=lambda x: x[1])
                segment["dominant_emotion"] = {
                    "name": dominant[0],
                    "score": dominant[1]
                }

            result["segments"].append(segment)

        result["total_segments"] = len(result["segments"])
        return result