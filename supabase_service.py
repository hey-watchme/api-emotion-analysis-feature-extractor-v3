"""
Supabaseサービスレイヤー
emotion_opensmileテーブルへのデータ保存を管理
"""

import json
from datetime import datetime
from typing import Dict, List, Optional
from supabase import Client


class SupabaseService:
    """Supabaseとの連携を管理するサービスクラス"""
    
    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.table_name = "emotion_opensmile"
    
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
        emotion_opensmileテーブルに感情データをUPSERT
        
        Args:
            device_id: デバイスID
            date: 日付 (YYYY-MM-DD形式)
            time_block: 時間ブロック (HH-MM形式)
            filename: 処理したファイル名
            duration_seconds: 音声の長さ（秒）
            features_timeline: タイムスタンプと特徴量のリスト
            processing_time: 処理時間
            error: エラーメッセージ（あれば）
            selected_features_timeline: 選択された特徴量のタイムライン（SUPERBの感情分析結果）
            
        Returns:
            Dict: Supabaseからのレスポンス
        """
        try:
            # データの準備
            data = {
                "device_id": device_id,
                "date": date,
                "time_block": time_block,
                "filename": filename,
                "duration_seconds": duration_seconds,
                "features_timeline": features_timeline,  # JSONBとして保存
                "processing_time": processing_time,
                "error": error,
                "status": "completed" if not error else "error"
            }
            
            # selected_features_timelineがあれば追加（SUPERBの感情分析結果）
            if selected_features_timeline is not None:
                data["selected_features_timeline"] = selected_features_timeline
            
            # UPSERT実行（プライマリキー: device_id, date, time_block）
            response = self.supabase.table(self.table_name).upsert(
                data,
                on_conflict="device_id,date,time_block"
            ).execute()
            
            print(f"✅ Supabase UPSERT成功: {device_id}/{date}/{time_block}")
            return response.data
            
        except Exception as e:
            print(f"❌ Supabase UPSERT失敗: {str(e)}")
            raise e
    
    async def batch_upsert_emotion_data(
        self,
        records: List[Dict]
    ) -> List[Dict]:
        """
        複数のレコードを一度にUPSERT
        
        Args:
            records: UPSERTするレコードのリスト
            
        Returns:
            List[Dict]: Supabaseからのレスポンス
        """
        try:
            # statusを追加
            for record in records:
                if "status" not in record:
                    record["status"] = "completed" if not record.get("error") else "error"
            
            response = self.supabase.table(self.table_name).upsert(
                records,
                on_conflict="device_id,date,time_block"
            ).execute()
            
            print(f"✅ Supabase バッチUPSERT成功: {len(records)}件")
            return response.data
            
        except Exception as e:
            print(f"❌ Supabase バッチUPSERT失敗: {str(e)}")
            raise e