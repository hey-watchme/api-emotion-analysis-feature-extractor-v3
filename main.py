#!/usr/bin/env python3
"""
SUPERB感情分析API - 30秒チャンク処理版
wav2vec2-base-superb-erを使用した音声感情分析
30秒ごとに分割して処理し、統合結果を返す
"""

import os
import gc
import tempfile
import json
import librosa
import numpy as np
import soundfile as sf
from transformers import pipeline
import torch
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
from typing import Dict, List

# FastAPIアプリケーションの初期化
app = FastAPI(
    title="SUPERB Emotion Recognition API",
    description="30秒チャンクで処理する音声感情分析API",
    version="2.0.0"
)

# グローバル変数でモデルを保持
emotion_classifier = None

# チャンク設定
CHUNK_DURATION = 30.0  # 30秒固定

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

@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "message": "SUPERB Emotion Recognition API",
        "version": "1.0.0",
        "model": "wav2vec2-base-superb-er",
        "endpoints": {
            "health": "/health",
            "analyze": "/analyze (POST with audio file)"
        }
    }

@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {
        "status": "healthy",
        "model_loaded": emotion_classifier is not None
    }

def analyze_chunk(audio_chunk: np.ndarray, chunk_info: Dict) -> Dict:
    """
    30秒チャンクを分析
    """
    # Float32に変換
    audio_chunk = audio_chunk.astype(np.float32)
    
    # 正規化
    max_val = np.max(np.abs(audio_chunk))
    if max_val > 0:
        audio_chunk = audio_chunk / max_val
    
    # モデルで分析（全8感情を取得）
    results = emotion_classifier(audio_chunk, top_k=8)
    
    # ラベルの詳細情報
    labels_info = {
        "ang": {"ja": "怒り", "en": "Angry", "group": "negative_active"},
        "hap": {"ja": "喜び", "en": "Happy", "group": "positive_active"},
        "sad": {"ja": "悲しみ", "en": "Sad", "group": "negative_passive"},
        "neu": {"ja": "中立", "en": "Neutral", "group": "neutral"},
        "exc": {"ja": "興奮", "en": "Excited", "group": "positive_active"},
        "fru": {"ja": "欲求不満", "en": "Frustrated", "group": "negative_active"},
        "sur": {"ja": "驚き", "en": "Surprised", "group": "neutral"},
        "dis": {"ja": "嫌悪", "en": "Disgusted", "group": "negative_active"}
    }
    
    # 結果を整形
    emotions = []
    for result in results:
        label = result['label']
        score = float(result['score'])
        info = labels_info.get(label, {"ja": label, "en": label, "group": "unknown"})
        
        emotions.append({
            "label": label,
            "score": round(score, 6),
            "percentage": round(score * 100, 3),
            "name_ja": info["ja"],
            "name_en": info["en"],
            "group": info["group"]
        })
    
    # チャンク結果
    return {
        "chunk_id": chunk_info["id"],
        "start_time": chunk_info["start"],
        "end_time": chunk_info["end"],
        "duration": chunk_info["duration"],
        "emotions": emotions,
        "primary_emotion": emotions[0] if emotions else None
    }

@app.post("/analyze")
async def analyze_emotion(file: UploadFile = File(...)):
    """
    音声を30秒チャンクに分割して感情分析
    各チャンクの結果と統合結果を返す
    
    Args:
        file: アップロードされた音声ファイル（WAV, MP3等）
    
    Returns:
        30秒ごとの感情分析結果と統合サマリー
    """
    if emotion_classifier is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        print(f"\n{'='*60}")
        print(f"📁 分析開始: {file.filename}")
        print(f"{'='*60}")
        
        # ファイル読み込み
        contents = await file.read()
        file_size_mb = len(contents) / 1024 / 1024
        print(f"📦 ファイルサイズ: {file_size_mb:.2f}MB")
        
        # 一時ファイルに保存
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(contents)
            tmp_file_path = tmp_file.name
        
        # メモリ解放
        del contents
        gc.collect()
        
        # 音声読み込み
        audio_data, sample_rate = sf.read(tmp_file_path)
        
        # 一時ファイル削除
        os.unlink(tmp_file_path)
        
        # モノラルに変換
        if len(audio_data.shape) > 1:
            audio_data = np.mean(audio_data, axis=1)
        
        # 16kHzにリサンプリング
        if sample_rate != 16000:
            print(f"🔄 リサンプリング: {sample_rate}Hz → 16000Hz")
            audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=16000)
            sample_rate = 16000
        
        # 音声の総時間
        total_duration = len(audio_data) / sample_rate
        print(f"📊 総時間: {total_duration:.1f}秒")
        
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
            
            print(f"\n🔍 チャンク {chunk_id}: {start_time:.1f}秒 - {end_time:.1f}秒 ({duration:.1f}秒)")
            
            # チャンクを抽出
            chunk = audio_data[start_idx:end_idx]
            
            # チャンク情報
            chunk_info = {
                "id": chunk_id,
                "start": round(start_time, 1),
                "end": round(end_time, 1),
                "duration": round(duration, 1)
            }
            
            # チャンクを分析
            chunk_result = analyze_chunk(chunk, chunk_info)
            chunks_results.append(chunk_result)
            
            # 結果をコンソールに表示
            primary = chunk_result["primary_emotion"]
            print(f"   主要感情: {primary['name_ja']} ({primary['percentage']:.1f}%)")
            
            # メモリ解放
            del chunk
            gc.collect()
        
        # メモリ解放
        del audio_data
        gc.collect()
        
        # 全体の統計を計算
        all_emotions_sum = {}
        for chunk in chunks_results:
            for emotion in chunk["emotions"]:
                label = emotion["label"]
                if label not in all_emotions_sum:
                    all_emotions_sum[label] = {
                        "scores": [],
                        "name_ja": emotion["name_ja"],
                        "name_en": emotion["name_en"],
                        "group": emotion["group"]
                    }
                all_emotions_sum[label]["scores"].append(emotion["score"])
        
        # 平均スコアを計算
        emotion_averages = []
        for label, data in all_emotions_sum.items():
            avg_score = sum(data["scores"]) / len(data["scores"])
            emotion_averages.append({
                "label": label,
                "average_score": round(avg_score, 6),
                "average_percentage": round(avg_score * 100, 3),
                "name_ja": data["name_ja"],
                "name_en": data["name_en"],
                "group": data["group"],
                "appearances": len(data["scores"])
            })
        
        # スコアでソート
        emotion_averages.sort(key=lambda x: x["average_score"], reverse=True)
        
        # グループごとの統計
        group_stats = {}
        for chunk in chunks_results:
            for emotion in chunk["emotions"]:
                group = emotion["group"]
                if group not in group_stats:
                    group_stats[group] = []
                group_stats[group].append(emotion["score"])
        
        group_averages = {}
        for group, scores in group_stats.items():
            group_averages[group] = {
                "average_score": round(sum(scores) / len(scores), 4),
                "average_percentage": round((sum(scores) / len(scores)) * 100, 2),
                "total_appearances": len(scores)
            }
        
        # 最も強いグループを特定
        dominant_group = max(group_averages.items(), key=lambda x: x[1]["average_score"])
        
        # レスポンス作成
        response = {
            "success": True,
            "filename": file.filename,
            "file_size_mb": round(file_size_mb, 2),
            "file_info": {
                "total_duration": round(total_duration, 1),
                "sample_rate": sample_rate,
                "total_chunks": len(chunks_results),
                "chunk_duration": CHUNK_DURATION
            },
            "chunks": chunks_results,
            "summary": {
                "overall_primary_emotion": emotion_averages[0] if emotion_averages else None,
                "emotion_averages": emotion_averages,
                "group_statistics": group_averages,
                "dominant_group": {
                    "name": dominant_group[0],
                    "data": dominant_group[1]
                }
            }
        }
        
        # コンソールに最終サマリーを表示
        print(f"\n{'='*60}")
        print(f"📊 最終サマリー:")
        print(f"{'='*60}")
        print(f"総チャンク数: {len(chunks_results)}")
        print(f"総時間: {total_duration:.1f}秒")
        print(f"\n全体を通しての主要感情:")
        for i, emotion in enumerate(emotion_averages[:3]):
            print(f"{i+1}. {emotion['name_ja']:8} {emotion['average_percentage']:6.2f}%")
        print(f"\n支配的な感情グループ: {dominant_group[0]}")
        print(f"  平均スコア: {dominant_group[1]['average_percentage']:.1f}%")
        print(f"{'='*60}\n")
        
        return JSONResponse(content=response)
        
    except Exception as e:
        import traceback
        print(f"❌ エラー: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

if __name__ == "__main__":
    # ポート8018で起動
    uvicorn.run(app, host="0.0.0.0", port=8018, reload=False)