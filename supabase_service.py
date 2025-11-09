"""
Supabaseサービスレイヤー
audio_featuresテーブルへのデータ保存を管理
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from supabase import Client


class SupabaseService:
    """Supabaseとの連携を管理するサービスクラス"""

    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.table_name = "audio_features"
    
    async def upsert_emotion_data(
        self,
        device_id: str,
        date: str,
        time_block: str,
        filename: str,
        duration_seconds: int,
        features_timeline: List[Dict],
        processing_time: float,
        error: Optional[str] = None,
        selected_features_timeline: Optional[List[Dict]] = None
    ) -> Dict:
        """
        audio_featuresテーブルに感情データをUPSERT

        Args:
            device_id: デバイスID
            date: 日付 (YYYY-MM-DD形式)
            time_block: 時間ブロック (HH-MM形式)
            filename: 処理したファイル名（旧パラメータ、互換性のため保持）
            duration_seconds: 音声の長さ（旧パラメータ、互換性のため保持）
            features_timeline: SUPERBの感情分析結果
            processing_time: 処理時間（旧パラメータ、互換性のため保持）
            error: エラーメッセージ（あれば）
            selected_features_timeline: 旧パラメータ（互換性のため保持）

        Returns:
            Dict: Supabaseからのレスポンス
        """
        try:
            # 現在のUTCタイムスタンプを取得
            processed_at = datetime.now(timezone.utc).isoformat()

            # データの準備（新しいスキーマに対応）
            data = {
                "device_id": device_id,
                "date": date,
                "time_block": time_block,
                "emotion_extractor_result": features_timeline,  # JSONB形式
                "emotion_extractor_status": "completed" if not error else "failed",
                "emotion_extractor_processed_at": processed_at
            }

            # エラーメッセージがあれば追加
            if error:
                data["emotion_extractor_error_message"] = error

            # UPSERT実行（プライマリキー: device_id, date, time_block）
            response = self.supabase.table(self.table_name).upsert(
                data,
                on_conflict="device_id,date,time_block"
            ).execute()

            print(f"✅ audio_features UPSERT成功: {device_id}/{date}/{time_block}")
            return response.data

        except Exception as e:
            print(f"❌ audio_features UPSERT失敗: {str(e)}")
            raise e
    
    async def batch_upsert_emotion_data(
        self,
        records: List[Dict]
    ) -> List[Dict]:
        """
        複数のレコードを一度にUPSERT（新スキーマ対応）

        Args:
            records: UPSERTするレコードのリスト

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
                    "date": record["date"],
                    "time_block": record["time_block"],
                    "emotion_extractor_result": record.get("features_timeline", []),  # JSONB形式
                    "emotion_extractor_status": "completed" if not record.get("error") else "failed",
                    "emotion_extractor_processed_at": processed_at
                }

                # エラーメッセージがあれば追加
                if record.get("error"):
                    new_record["emotion_extractor_error_message"] = record["error"]

                converted_records.append(new_record)

            response = self.supabase.table(self.table_name).upsert(
                converted_records,
                on_conflict="device_id,date,time_block"
            ).execute()

            print(f"✅ audio_features バッチUPSERT成功: {len(converted_records)}件")
            return response.data

        except Exception as e:
            print(f"❌ audio_features バッチUPSERT失敗: {str(e)}")
            raise e