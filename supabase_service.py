"""
Supabaseサービスレイヤー
spot_featuresテーブルへのデータ保存を管理
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from supabase import Client


class SupabaseService:
    """Supabaseとの連携を管理するサービスクラス"""

    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.table_name = "spot_features"
    
    async def upsert_emotion_data(
        self,
        device_id: str,
        recorded_at: str,
        features_timeline: List[Dict],
        local_date: Optional[str] = None,
        local_time: Optional[str] = None,
        error: Optional[str] = None
    ) -> Dict:
        """
        spot_featuresテーブルに感情データをUPSERT

        Args:
            device_id: デバイスID
            recorded_at: 録音日時 (UTC timestamp)
            features_timeline: SUPERBの感情分析結果
            local_date: ローカル日付 (YYYY-MM-DD)
            local_time: ローカル時刻 (YYYY-MM-DD HH:MM:SS)
            error: エラーメッセージ（あれば）

        Returns:
            Dict: Supabaseからのレスポンス
        """
        try:
            # 現在のUTCタイムスタンプを取得
            processed_at = datetime.now(timezone.utc).isoformat()

            # データの準備
            data = {
                "device_id": device_id,
                "recorded_at": recorded_at,
                "emotion_extractor_result": features_timeline,  # JSONB形式
                "emotion_extractor_status": "completed" if not error else "failed",
                "emotion_extractor_processed_at": processed_at
            }

            # local_dateがあれば追加
            if local_date:
                data["local_date"] = local_date

            # local_timeがあれば追加
            if local_time:
                data["local_time"] = local_time

            # エラーメッセージがあれば追加
            if error:
                data["emotion_extractor_error_message"] = error

            # UPSERT実行（プライマリキー: device_id, recorded_at）
            response = self.supabase.table(self.table_name).upsert(data).execute()

            print(f"✅ spot_features UPSERT成功: {device_id}/{recorded_at}")
            return response.data

        except Exception as e:
            print(f"❌ spot_features UPSERT失敗: {str(e)}")
            raise e
    
    async def batch_upsert_emotion_data(
        self,
        records: List[Dict]
    ) -> List[Dict]:
        """
        複数のレコードを一度にUPSERT

        Args:
            records: UPSERTするレコードのリスト
                    各レコードには device_id, recorded_at, features_timeline が必要

        Returns:
            List[Dict]: Supabaseからのレスポンス
        """
        try:
            # 現在のUTCタイムスタンプを取得
            processed_at = datetime.now(timezone.utc).isoformat()

            # 新しいスキーマに変換
            converted_records = []
            for record in records:
                new_record = {
                    "device_id": record["device_id"],
                    "recorded_at": record["recorded_at"],
                    "emotion_extractor_result": record.get("features_timeline", []),  # JSONB形式
                    "emotion_extractor_status": "completed" if not record.get("error") else "failed",
                    "emotion_extractor_processed_at": processed_at
                }

                # local_dateがあれば追加
                if record.get("local_date"):
                    new_record["local_date"] = record["local_date"]

                # local_timeがあれば追加
                if record.get("local_time"):
                    new_record["local_time"] = record["local_time"]

                # エラーメッセージがあれば追加
                if record.get("error"):
                    new_record["emotion_extractor_error_message"] = record["error"]

                converted_records.append(new_record)

            response = self.supabase.table(self.table_name).upsert(converted_records).execute()

            print(f"✅ spot_features バッチUPSERT成功: {len(converted_records)}件")
            return response.data

        except Exception as e:
            print(f"❌ spot_features バッチUPSERT失敗: {str(e)}")
            raise e

    async def update_status(self, device_id: str, recorded_at: str, status_field: str, status_value: str):
        """
        Update processing status in spot_features table
        """
        try:
            # Update status in database
            response = self.supabase.table('spot_features').update({
                status_field: status_value,
                'updated_at': datetime.utcnow().isoformat()
            }).eq(
                'device_id', device_id
            ).eq(
                'recorded_at', recorded_at
            ).execute()

            if response.data:
                print(f"Status updated: {device_id}/{recorded_at} - {status_field}={status_value}")
            else:
                # If no existing record, create one
                insert_data = {
                    'device_id': device_id,
                    'recorded_at': recorded_at,
                    status_field: status_value,
                    'created_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat()
                }
                self.supabase.table('spot_features').insert(insert_data).execute()
                print(f"Status record created: {device_id}/{recorded_at} - {status_field}={status_value}")

        except Exception as e:
            print(f"Failed to update status: {str(e)}")
            raise