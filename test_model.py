#!/usr/bin/env python3
"""
SUPERB wav2vec2-base-superb-er モデルの動作確認スクリプト
"""

import numpy as np
from transformers import pipeline
import torch

def test_model():
    print("=== SUPERB感情認識モデルのテスト開始 ===")
    
    # GPUが使えるかチェック
    if torch.backends.mps.is_available():
        device = 0  # Apple Siliconの場合
        print("✅ Apple Siliconを使用します")
    elif torch.cuda.is_available():
        device = 0  # CUDAが使える場合
        print("✅ GPUを使用します")
    else:
        device = -1  # CPUのみ
        print("ℹ️ CPUを使用します")
    
    try:
        # モデルをロード
        print("\n📥 モデルをダウンロード中...")
        emotion_classifier = pipeline(
            "audio-classification",
            model="superb/wav2vec2-base-superb-er",
            device=device
        )
        print("✅ モデルのロード成功！")
        
        # テスト用の音声データを作成（1秒の440Hzサイン波）
        print("\n🎵 テスト用音声データを生成中...")
        sample_rate = 16000
        duration = 1  # 1秒
        frequency = 440  # A4音
        t = np.linspace(0, duration, sample_rate * duration)
        audio_array = np.sin(2 * np.pi * frequency * t).astype(np.float32)
        
        # 感情分析を実行
        print("\n🧠 感情分析を実行中...")
        results = emotion_classifier(audio_array, top_k=5)
        
        # 結果を表示
        print("\n=== 分析結果 ===")
        for i, result in enumerate(results, 1):
            label = result['label']
            score = result['score']
            print(f"{i}. {label:10s}: {score:.4f} ({score*100:.2f}%)")
        
        print("\n✅ テスト完了！モデルは正常に動作しています。")
        
        # ラベルの説明
        print("\n=== 感情ラベルの説明 ===")
        labels = {
            "ang": "怒り (Angry)",
            "hap": "喜び (Happy)",
            "sad": "悲しみ (Sad)",
            "neu": "中立 (Neutral)",
            "exc": "興奮 (Excited)",
            "fru": "欲求不満 (Frustrated)",
            "sur": "驚き (Surprised)",
            "dis": "嫌悪 (Disgusted)"
        }
        
        for key, value in labels.items():
            if any(key in r['label'] for r in results):
                print(f"  {key}: {value}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_model()
    exit(0 if success else 1)