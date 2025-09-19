# SUPERB 音声感情分析 API

wav2vec2-base-superb-erモデルを使用した音声感情分析APIサービスです。音声ファイルを30秒チャンクに分割して処理し、8種類の感情を検出・スコアリングします。

## ⚠️ 重要な注意事項

- **30秒チャンク処理が必須**: 長い音声は自動的に30秒ごとに分割して処理されます
- **メモリ制限**: 30秒を超える一括処理はメモリ不足でクラッシュする可能性があります
- **推奨音声長**: 30秒〜5分程度が最適（それ以上も処理可能ですが時間がかかります）

## 🎯 機能

- 音声ファイル（WAV, MP3等）からの感情分析
- **30秒チャンク単位での安定処理**
- 8種類の感情検出（全感情のスコアを出力）
- 感情グループ化による包括的な分析
- Apple Silicon/GPU対応による高速処理

## 📊 検出可能な8つの感情

| ラベル | 日本語 | 英語 | グループ |
|--------|--------|------|----------|
| ang | 怒り | Angry | negative_active |
| hap | 喜び | Happy | positive_active |
| sad | 悲しみ | Sad | negative_passive |
| neu | 中立 | Neutral | neutral |
| exc | 興奮 | Excited | positive_active |
| fru | 欲求不満 | Frustrated | negative_active |
| sur | 驚き | Surprised | neutral |
| dis | 嫌悪 | Disgusted | negative_active |

### 感情グループ
- **negative_active**: 怒り系（ang, fru, dis）
- **positive_active**: 喜び系（hap, exc）
- **negative_passive**: 悲しみ系（sad）
- **neutral**: 中立系（neu, sur）

## 📋 必要要件

- Python 3.8以上
- 4GB以上のメモリ（モデル読み込み用）
- Apple Silicon Mac または CUDA対応GPU（オプション、CPU動作も可）

## 🚀 セットアップ

### 1. 仮想環境の作成と有効化

```bash
python3 -m venv venv
source venv/bin/activate  # Windowsの場合: venv\Scripts\activate
```

### 2. 依存パッケージのインストール

```bash
pip3 install -r requirements.txt
```

初回実行時は、Hugging Faceから約400MBのモデルがダウンロードされます。

### 3. モデルの動作確認（オプション）

```bash
python3 test_model.py
```

## 🎮 使い方

### APIサーバーの起動

```bash
python3 main.py
```

サーバーはポート8018で起動します：
- http://localhost:8018

### APIエンドポイント

#### 1. ルート情報
```bash
curl http://localhost:8018/
```

#### 2. ヘルスチェック
```bash
curl http://localhost:8018/health
```

#### 3. 感情分析（メインエンドポイント）
```bash
# 音声ファイルを分析
curl -X POST http://localhost:8018/analyze \
  -F "file=@your_audio.wav"
```

### レスポンス形式

```json
{
  "success": true,
  "filename": "audio.wav",
  "file_size_mb": 8.0,
  "file_info": {
    "total_duration": 261.0,
    "sample_rate": 16000,
    "total_chunks": 9,
    "chunk_duration": 30.0
  },
  "chunks": [
    {
      "chunk_id": 1,
      "start_time": 0.0,
      "end_time": 30.0,
      "duration": 30.0,
      "emotions": [
        {
          "label": "ang",
          "score": 0.7862,
          "percentage": 78.62,
          "name_ja": "怒り",
          "name_en": "Angry",
          "group": "negative_active"
        },
        // ... 他の7感情
      ],
      "primary_emotion": {
        "label": "ang",
        "score": 0.7862,
        "percentage": 78.62,
        "name_ja": "怒り",
        "name_en": "Angry",
        "group": "negative_active"
      }
    },
    // ... 他のチャンク
  ],
  "summary": {
    "overall_primary_emotion": {
      "label": "ang",
      "average_score": 0.5530,
      "average_percentage": 55.30,
      "name_ja": "怒り",
      "name_en": "Angry",
      "group": "negative_active"
    },
    "emotion_averages": [
      // 8感情の平均スコア（降順）
    ],
    "group_statistics": {
      "negative_active": {
        "average_score": 0.5529,
        "average_percentage": 55.29,
        "total_appearances": 72
      },
      // ... 他のグループ
    },
    "dominant_group": {
      "name": "negative_active",
      "data": {
        "average_percentage": 55.29
      }
    }
  }
}
```

## 🏗️ プロジェクト構成

```
superb/
├── main.py                 # FastAPI アプリケーション（30秒チャンク処理）
├── test_model.py          # モデル動作確認スクリプト
├── generate_test_audio.py # テスト音声生成スクリプト
├── requirements.txt       # 依存パッケージ
├── test_neutral.wav       # テスト音声（中立）
├── test_angry.wav         # テスト音声（怒り）
├── test_sad.wav          # テスト音声（悲しみ）
└── README.md             # このファイル
```

## ⚙️ 技術仕様

### 処理方式
- **30秒チャンク分割処理**: メモリ効率とパフォーマンスの最適化
- **順次処理**: 各チャンクを順番に処理してメモリを解放
- **全8感情出力**: すべての感情スコアを取得して詳細な分析

### モデル仕様
- **モデル**: `superb/wav2vec2-base-superb-er` (Hugging Face)
- **フレームワーク**: FastAPI 
- **音声処理**: librosa (16kHz リサンプリング)
- **推論**: PyTorch (CPU/GPU/Apple Silicon対応)
- **サンプリングレート**: 16kHz (自動変換)
- **対応フォーマット**: WAV, MP3, その他soundfile対応形式

## 🐛 トラブルシューティング

### メモリエラー / フリーズ
- **原因**: 30秒を超える音声を一括処理しようとした場合
- **解決**: このAPIは自動的に30秒チャンクに分割するため、通常は発生しません
- **注意**: 極端に長い音声（10分以上）は処理時間が長くなります

### モデルのダウンロードが遅い
初回実行時は約400MBのモデルをダウンロードするため時間がかかります。安定したネットワーク環境で実行してください。

### ポート8018が使用中
```bash
# 使用中のプロセスを確認
lsof -i :8018
# 必要に応じてプロセスを終了
kill -9 <PID>
```

### 精度に関する注意
- このモデルは主に英語データで訓練されています
- 日本語音声では「怒り」と「喜び」が混同される場合があります
- 全体的な感情グループ（negative_active等）で判断することを推奨

## 📈 パフォーマンス

- **30秒音声**: 約2-3秒で処理
- **5分音声（10チャンク）**: 約20-30秒で処理
- **メモリ使用量**: 約1-2GB（モデル + 処理中のデータ）

## 📝 ライセンス

このプロジェクトで使用しているモデル：
- wav2vec2-base-superb-er: Apache License 2.0

## 🤝 貢献

バグ報告や機能リクエストは、Issueを作成してください。