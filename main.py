#!/usr/bin/env python3
"""
SUPERB感情分析API - OpenSMILE互換版
wav2vec2-base-superb-erを使用した音声感情分析
S3からファイルを取得し、Supabaseに結果を保存
"""

import os
import gc
import time
import tempfile
import json
import librosa
import numpy as np
import soundfile as sf
from transformers import pipeline
import torch
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from supabase import create_client, Client

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, List, Optional

from models import (
    HealthResponse,
    ErrorResponse,
    EmotionFeaturesRequest,
    EmotionFeaturesResponse,
    ChunkResult,
    EmotionScore
)
from supabase_service import SupabaseService

# 環境変数の読み込み
load_dotenv()

# FastAPIアプリケーションの初期化
app = FastAPI(
    title="SUPERB Emotion Recognition API - OpenSMILE Compatible",
    description="wav2vec2-base-superb-erを使用したfile_pathsベースの感情分析サービス",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORSミドルウェアの設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabaseクライアントの初期化
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
if supabase_url and supabase_key:
    supabase_client: Client = create_client(supabase_url, supabase_key)
    supabase_service = SupabaseService(supabase_client)
    print(f"✅ Supabase接続設定完了: {supabase_url}")
else:
    supabase_service = None
    print("⚠️ Supabase環境変数が設定されていません")

# AWS S3クライアントの初期化
aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
s3_bucket_name = os.getenv('S3_BUCKET_NAME', 'watchme-vault')
aws_region = os.getenv('AWS_REGION', 'us-east-1')

if not aws_access_key_id or not aws_secret_access_key:
    raise ValueError("AWS_ACCESS_KEY_IDおよびAWS_SECRET_ACCESS_KEYが設定されていません")

s3_client = boto3.client(
    's3',
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    region_name=aws_region
)
print(f"✅ AWS S3接続設定完了: バケット={s3_bucket_name}, リージョン={aws_region}")

# グローバル変数でモデルを保持
emotion_classifier = None

# チャンク設定
CHUNK_DURATION = 30.0  # 30秒固定

# 感情ラベルの詳細情報
LABELS_INFO = {
    "ang": {"ja": "怒り", "en": "Angry", "group": "negative_active"},
    "hap": {"ja": "喜び", "en": "Happy", "group": "positive_active"},
    "sad": {"ja": "悲しみ", "en": "Sad", "group": "negative_passive"},
    "neu": {"ja": "中立", "en": "Neutral", "group": "neutral"},
    "exc": {"ja": "興奮", "en": "Excited", "group": "positive_active"},
    "fru": {"ja": "欲求不満", "en": "Frustrated", "group": "negative_active"},
    "sur": {"ja": "驚き", "en": "Surprised", "group": "neutral"},
    "dis": {"ja": "嫌悪", "en": "Disgusted", "group": "negative_active"}
}


def init_model():
    """モデルを初期化"""
    global emotion_classifier
    
    # デバイスの設定
    if torch.backends.mps.is_available():
        device = 0  # Apple Silicon
        print("✅ Apple Siliconを使用します")
    elif torch.cuda.is_available():
        device = 0  # CUDA
        print("✅ GPUを使用します")
    else:
        device = -1  # CPU
        print("ℹ️ CPUを使用します")
    
    print("📥 感情認識モデルをロード中...")
    emotion_classifier = pipeline(
        "audio-classification",
        model="superb/wav2vec2-base-superb-er",
        device=device
    )
    print("✅ モデルのロード完了！")


# 起動時にモデルをロード
@app.on_event("startup")
async def startup_event():
    init_model()


def extract_info_from_file_path(file_path: str) -> dict:
    """ファイルパスからデバイス情報を抽出
    
    Args:
        file_path: 'files/device_id/date/time/audio.wav' 形式
        
    Returns:
        dict: {'device_id': str, 'date': str, 'time_block': str}
    """
    parts = file_path.split('/')
    if len(parts) >= 5:
        return {
            'device_id': parts[1],
            'date': parts[2], 
            'time_block': parts[3]
        }
    else:
        raise ValueError(f"不正なファイルパス形式: {file_path}")


async def update_audio_files_status(file_path: str) -> bool:
    """audio_filesテーブルのemotion_features_statusを更新
    
    Args:
        file_path: 処理完了したファイルのパス
        
    Returns:
        bool: 更新成功可否
    """
    try:
        update_response = supabase_client.table('audio_files') \
            .update({'emotion_features_status': 'completed'}) \
            .eq('file_path', file_path) \
            .execute()
        
        if update_response.data:
            print(f"✅ ステータス更新成功: {file_path}")
            return True
        else:
            print(f"⚠️ 対象レコードが見つかりません: {file_path}")
            return False
            
    except Exception as e:
        print(f"❌ ステータス更新エラー: {str(e)}")
        return False


def analyze_audio_file(audio_path: str) -> List[Dict]:
    """
    音声ファイルを30秒チャンクに分割して感情分析
    
    Args:
        audio_path: 音声ファイルのパス
    
    Returns:
        30秒ごとの感情分析結果リスト
    """
    if emotion_classifier is None:
        raise RuntimeError("Model not loaded")
    
    # 音声読み込み
    audio_data, sample_rate = sf.read(audio_path)
    
    # モノラルに変換
    if len(audio_data.shape) > 1:
        audio_data = np.mean(audio_data, axis=1)
    
    # 16kHzにリサンプリング
    if sample_rate != 16000:
        audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=16000)
        sample_rate = 16000
    
    # 音声の総時間
    total_duration = len(audio_data) / sample_rate
    
    # チャンクサイズ（サンプル数）
    chunk_samples = int(CHUNK_DURATION * sample_rate)
    
    # チャンク処理結果を格納
    chunks_results = []
    
    # チャンクごとに処理
    chunk_id = 0
    for start_idx in range(0, len(audio_data), chunk_samples):
        chunk_id += 1
        end_idx = min(start_idx + chunk_samples, len(audio_data))
        
        # チャンク情報
        start_time = start_idx / sample_rate
        end_time = end_idx / sample_rate
        duration = end_time - start_time
        
        # チャンクを抽出
        chunk = audio_data[start_idx:end_idx]
        
        # Float32に変換
        chunk = chunk.astype(np.float32)
        
        # 正規化
        max_val = np.max(np.abs(chunk))
        if max_val > 0:
            chunk = chunk / max_val
        
        # モデルで分析（全8感情を取得）
        results = emotion_classifier(chunk, top_k=8)
        
        # 結果を整形
        emotions = []
        for result in results:
            label = result['label']
            score = float(result['score'])
            info = LABELS_INFO.get(label, {"ja": label, "en": label, "group": "unknown"})
            
            emotions.append({
                "label": label,
                "score": round(score, 6),
                "percentage": round(score * 100, 3),
                "name_ja": info["ja"],
                "name_en": info["en"],
                "group": info["group"]
            })
        
        # チャンク結果
        chunk_result = {
            "chunk_id": chunk_id,
            "start_time": round(start_time, 1),
            "end_time": round(end_time, 1),
            "duration": round(duration, 1),
            "emotions": emotions,
            "primary_emotion": emotions[0] if emotions else None
        }
        
        chunks_results.append(chunk_result)
        
        # メモリ解放
        del chunk
        gc.collect()
    
    # メモリ解放
    del audio_data
    gc.collect()
    
    return chunks_results, int(total_duration)


@app.get("/", response_model=dict)
async def root():
    """ルートエンドポイント"""
    return {
        "message": "SUPERB Emotion Recognition API - OpenSMILE Compatible",
        "version": "3.0.0",
        "model": "wav2vec2-base-superb-er",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """ヘルスチェックエンドポイント"""
    try:
        return HealthResponse(
            status="healthy",
            service="SUPERB API - OpenSMILE Compatible",
            version="3.0.0",
            model_loaded=emotion_classifier is not None
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unhealthy: {str(e)}"
        )


@app.post("/process/emotion-features", response_model=EmotionFeaturesResponse)
async def process_emotion_features(request: EmotionFeaturesRequest):
    """file_pathsベースの感情分析（OpenSMILE互換）"""
    start_time = time.time()
    
    try:
        print(f"\n=== file_pathsベースによる感情分析開始 ===")
        print(f"file_pathsパラメータ: {len(request.file_paths)}件のファイルを処理")
        print(f"=" * 50)
        
        if not supabase_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Supabaseサービスが利用できません。環境変数を確認してください。"
            )
        
        processed_files = 0
        error_files = []
        supabase_records = []
        
        # 一時ディレクトリを作成してWAVファイルを処理
        with tempfile.TemporaryDirectory() as temp_dir:
            for file_path in request.file_paths:
                try:
                    print(f"\n📥 S3からファイル取得開始: {file_path}")
                    
                    # ファイルパスから情報を抽出
                    path_info = extract_info_from_file_path(file_path)
                    device_id = path_info['device_id']
                    date = path_info['date']
                    time_block = path_info['time_block']
                    
                    # S3から一時ファイルにダウンロード
                    temp_file_path = os.path.join(temp_dir, f"{time_block}.wav")
                    
                    try:
                        s3_client.download_file(s3_bucket_name, file_path, temp_file_path)
                        print(f"✅ S3ダウンロード成功: {file_path}")
                    except ClientError as e:
                        error_code = e.response['Error']['Code']
                        if error_code == 'NoSuchKey':
                            print(f"⚠️ ファイルが見つかりません: {file_path}")
                            error_files.append(file_path)
                            continue
                        else:
                            raise e
                    
                    print(f"🎵 感情分析開始: {file_path}")
                    
                    # 感情分析を実行
                    analysis_start = time.time()
                    chunks_results, duration_seconds = analyze_audio_file(temp_file_path)
                    processing_time = time.time() - analysis_start
                    
                    processed_files += 1
                    
                    # Supabase用のレコードを準備
                    # features_timelineにSUPERBの結果を保存（修正版）
                    # selected_features_timelineは空配列（互換性のため）
                    supabase_record = {
                        "device_id": device_id,
                        "date": date,
                        "time_block": time_block,
                        "filename": os.path.basename(file_path),
                        "duration_seconds": duration_seconds,
                        "features_timeline": chunks_results,  # SUPERBの感情分析結果をこちらに保存
                        "selected_features_timeline": [],  # 空配列を設定
                        "processing_time": processing_time,
                        "error": None
                    }
                    supabase_records.append(supabase_record)
                    
                    # audio_filesテーブルのステータスを更新
                    await update_audio_files_status(file_path)
                    
                    # 主要感情を表示
                    if chunks_results:
                        for chunk in chunks_results:
                            primary = chunk["primary_emotion"]
                            print(f"  チャンク{chunk['chunk_id']}: {primary['name_ja']} ({primary['percentage']:.1f}%)")
                    
                    print(f"✅ 完了: {file_path} → {len(chunks_results)}チャンクの感情分析完了")
                    
                except Exception as e:
                    error_files.append(file_path)
                    print(f"❌ エラー: {file_path} - {str(e)}")
                    
                    # エラーレコードもSupabaseに保存
                    try:
                        path_info = extract_info_from_file_path(file_path)
                        supabase_record = {
                            "device_id": path_info['device_id'],
                            "date": path_info['date'],
                            "time_block": path_info['time_block'],
                            "filename": os.path.basename(file_path),
                            "duration_seconds": 0,
                            "features_timeline": [],  # エラー時は空
                            "selected_features_timeline": [],  # エラー時は空
                            "processing_time": 0,
                            "error": str(e)
                        }
                        supabase_records.append(supabase_record)
                    except:
                        pass
        
        # Supabaseにバッチで保存
        print(f"\n=== Supabase保存開始 ===")
        print(f"保存対象: {len(supabase_records)} レコード")
        print(f"=" * 50)
        
        saved_count = 0
        save_errors = []
        
        if supabase_records:
            try:
                # バッチでUPSERT実行
                await supabase_service.batch_upsert_emotion_data(supabase_records)
                saved_count = len(supabase_records)
                print(f"✅ Supabase保存成功: {saved_count} レコード")
            except Exception as e:
                print(f"❌ Supabaseバッチ保存エラー: {str(e)}")
                # 個別に保存を試みる
                for record in supabase_records:
                    try:
                        await supabase_service.upsert_emotion_data(
                            device_id=record["device_id"],
                            date=record["date"],
                            time_block=record["time_block"],
                            filename=record["filename"],
                            duration_seconds=record["duration_seconds"],
                            features_timeline=record["features_timeline"],  # SUPERBの結果がここに入る
                            processing_time=record["processing_time"],
                            error=record.get("error"),
                            selected_features_timeline=record.get("selected_features_timeline", [])  # 空配列
                        )
                        saved_count += 1
                    except Exception as individual_error:
                        save_errors.append(f"{record['time_block']}: {str(individual_error)}")
                        print(f"❌ 個別保存エラー: {record['time_block']} - {str(individual_error)}")
        
        # レスポンス作成
        total_time = time.time() - start_time
        
        print(f"\n=== file_pathsベースによる感情分析完了 ===")
        print(f"📥 S3処理: {processed_files} ファイル")
        print(f"💾 Supabase保存: {saved_count} レコード")
        print(f"❌ エラー: {len(error_files)} ファイル")
        print(f"⏱️ 総処理時間: {total_time:.2f}秒")
        print(f"=" * 50)
        
        return EmotionFeaturesResponse(
            success=True,
            processed_files=processed_files,
            saved_count=saved_count,
            error_files=error_files,
            total_processing_time=total_time,
            message=f"S3から{processed_files}個のファイルを処理し、{saved_count}個のレコードをSupabaseに保存しました"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"感情分析処理中にエラーが発生しました: {str(e)}"
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """グローバル例外ハンドラー"""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc)
        ).dict()
    )


if __name__ == "__main__":
    # ポート8018で起動（OpenSMILEは8011）
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8018,
        reload=True,
        log_level="info"
    )