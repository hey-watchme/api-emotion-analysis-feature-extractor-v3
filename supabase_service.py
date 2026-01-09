"""
Supabase Service for Hume AI Emotion Recognition API
Handles database operations
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import json

from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions

logger = logging.getLogger(__name__)


class SupabaseService:
    """Service for Supabase database operations"""

    def __init__(self, supabase_url: str, supabase_key: str):
        """
        Initialize Supabase client

        Args:
            supabase_url: Supabase project URL
            supabase_key: Supabase service role key
        """
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key

        # Create client with proper configuration
        options = ClientOptions(
            auto_refresh_token=False,  # Service role key doesn't need refresh
            persist_session=False
        )

        self.client: Client = create_client(
            supabase_url,
            supabase_key,
            options
        )

        logger.info(f"Supabase client initialized for {supabase_url}")

    async def update_emotion_status(
        self,
        device_id: str,
        recorded_at: str,
        status: str
    ) -> bool:
        """
        Update emotion processing status in spot_features table

        Args:
            device_id: Device identifier
            recorded_at: Recording timestamp
            status: Processing status (processing, completed, failed)

        Returns:
            Success status
        """
        try:
            # Update emotion_status column
            response = self.client.table('spot_features').update({
                'emotion_status': status,
                'updated_at': datetime.utcnow().isoformat()
            }).eq('device_id', device_id).eq('recorded_at', recorded_at).execute()

            if response.data:
                logger.info(f"Updated emotion_status to {status} for {device_id}")
                return True
            else:
                logger.warning(f"No record found to update for {device_id} at {recorded_at}")
                return False

        except Exception as e:
            logger.error(f"Failed to update emotion_status: {e}")
            return False

    async def save_emotion_features(
        self,
        device_id: str,
        recorded_at: str,
        emotion_data: Dict[str, Any]
    ) -> bool:
        """
        Save emotion features to spot_features table

        Args:
            device_id: Device identifier
            recorded_at: Recording timestamp
            emotion_data: Parsed Hume emotion analysis results

        Returns:
            Success status
        """
        try:
            # Check if record exists
            existing = self.client.table('spot_features').select('id').eq(
                'device_id', device_id
            ).eq('recorded_at', recorded_at).execute()

            if not existing.data:
                # Create new record
                logger.info(f"Creating new spot_features record for {device_id}")

                response = self.client.table('spot_features').insert({
                    'device_id': device_id,
                    'recorded_at': recorded_at,
                    'emotion_features_result_hume': emotion_data,
                    'emotion_status': 'completed' if not emotion_data.get('error') else 'failed',
                    'created_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat()
                }).execute()

                if response.data:
                    logger.info(f"Created new spot_features record for {device_id}")
                    return True
            else:
                # Update existing record
                response = self.client.table('spot_features').update({
                    'emotion_features_result_hume': emotion_data,
                    'emotion_status': 'completed' if not emotion_data.get('error') else 'failed',
                    'updated_at': datetime.utcnow().isoformat()
                }).eq('device_id', device_id).eq('recorded_at', recorded_at).execute()

                if response.data:
                    # Log summary
                    total_segments = emotion_data.get('total_segments', 0)
                    confidence = emotion_data.get('confidence', 0)

                    if total_segments > 0:
                        logger.info(
                            f"Saved Hume emotion data for {device_id}: "
                            f"{total_segments} segments, confidence {confidence:.2%}"
                        )

                        # Log dominant emotions if available
                        if emotion_data.get('speech_prosody'):
                            prosody = emotion_data['speech_prosody']
                            segments = prosody.get('segments', [])
                            if segments and segments[0].get('dominant_emotion'):
                                dominant = segments[0]['dominant_emotion']
                                logger.info(
                                    f"First segment dominant emotion: {dominant['name']} "
                                    f"({dominant['score']:.2%})"
                                )
                    else:
                        logger.warning(f"No emotion segments extracted for {device_id}")

                    return True

            return False

        except Exception as e:
            logger.error(f"Failed to save emotion features: {e}")
            return False

    async def check_existing_features(
        self,
        device_id: str,
        recorded_at: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if emotion features already exist

        Args:
            device_id: Device identifier
            recorded_at: Recording timestamp

        Returns:
            Existing emotion features or None
        """
        try:
            response = self.client.table('spot_features').select(
                'emotion_features_result_hume'
            ).eq('device_id', device_id).eq('recorded_at', recorded_at).execute()

            if response.data and response.data[0]:
                return response.data[0].get('emotion_features_result_hume')

            return None

        except Exception as e:
            logger.error(f"Failed to check existing features: {e}")
            return None

    async def get_audio_file_info(
        self,
        file_path: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get audio file information from database

        Args:
            file_path: S3 file path

        Returns:
            Audio file record or None
        """
        try:
            response = self.client.table('audio_files').select(
                'device_id, recorded_at, duration_seconds'
            ).eq('file_path', file_path).execute()

            if response.data and response.data[0]:
                return response.data[0]

            return None

        except Exception as e:
            logger.error(f"Failed to get audio file info: {e}")
            return None