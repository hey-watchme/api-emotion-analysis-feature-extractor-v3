#!/usr/bin/env python3
"""
テスト用音声ファイルの生成
"""

import numpy as np
import soundfile as sf

def generate_test_audio():
    # サンプリングレート
    sample_rate = 16000
    
    # 1. 穏やかな音（低音、ゆっくり）- 中立的
    duration = 2  # 2秒
    t = np.linspace(0, duration, sample_rate * duration)
    audio1 = np.sin(2 * np.pi * 220 * t) * 0.3  # A3音、音量控えめ
    
    # 2. 高い音（激しく）- 怒りや興奮を想定
    audio2 = np.sin(2 * np.pi * 880 * t) * 0.8  # A5音、音量大きめ
    audio2 += np.sin(2 * np.pi * 1320 * t) * 0.3  # 倍音を追加
    
    # 3. 変動する音（不安定）- 悲しみを想定
    frequency_mod = 440 + 50 * np.sin(2 * np.pi * 3 * t)  # 周波数を変動
    audio3 = np.sin(2 * np.pi * frequency_mod * t) * 0.5
    
    # ファイルに保存
    sf.write('test_neutral.wav', audio1.astype(np.float32), sample_rate)
    sf.write('test_angry.wav', audio2.astype(np.float32), sample_rate)
    sf.write('test_sad.wav', audio3.astype(np.float32), sample_rate)
    
    print("✅ テスト用音声ファイルを生成しました:")
    print("  - test_neutral.wav (穏やかな音)")
    print("  - test_angry.wav (高く激しい音)")
    print("  - test_sad.wav (変動する音)")

if __name__ == "__main__":
    generate_test_audio()