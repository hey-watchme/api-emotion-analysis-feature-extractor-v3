# SUPERB 音声感情分析 API

wav2vec2-base-superb-erモデルを使用した音声感情分析APIサービスです。AWS S3から音声ファイルを取得し、30秒チャンクに分割して処理し、8種類の感情を検出してSupabaseに保存します。

## 📊 システム概要

このAPIはOpenSMILE APIの代替として開発され、既存のシステムと完全な互換性を保ちながら、より高度な感情分析機能を提供します。

### 主な特徴
- **OpenSMILE API互換**: 同じエンドポイント、同じデータ構造
- **S3統合**: AWS S3から音声ファイルを自動取得
- **Supabase連携**: `emotion_opensmile`テーブルに結果を保存
- **30秒チャンク処理**: メモリ効率的な分割処理
- **8感情分析**: wav2vec2-base-superb-erによる詳細な感情検出

## 🎯 検出可能な8つの感情

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
- AWS S3アクセス権限
- Supabaseプロジェクト

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

### 3. 環境変数の設定

`.env`ファイルを作成し、以下の設定を記入：

```env
# Supabase設定
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# AWS S3設定
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
S3_BUCKET_NAME=your_s3_bucket_name
AWS_REGION=us-east-1
```

### 4. APIサーバーの起動

```bash
python3 main.py
```

サーバーはポート8018で起動します：
- http://localhost:8018
- Swagger UI: http://localhost:8018/docs
- ReDoc: http://localhost:8018/redoc

## 🔄 API仕様（OpenSMILE互換）

### メインエンドポイント

#### POST /process/emotion-features
S3から音声ファイルを取得して感情分析を実行

**リクエスト:**
```json
{
  "file_paths": [
    "files/device_id/2025-09-12/20-30/audio.wav"
  ]
}
```

**レスポンス:**
```json
{
  "success": true,
  "processed_files": 1,
  "saved_count": 1,
  "error_files": [],
  "total_processing_time": 5.15,
  "message": "S3から1個のファイルを処理し、1個のレコードをSupabaseに保存しました"
}
```

### その他のエンドポイント

#### GET /
API情報の取得

#### GET /health
ヘルスチェック

## 💾 データベース構造

### emotion_opensmileテーブル
```sql
create table public.emotion_opensmile (
  device_id text not null,
  date date not null,
  time_block text not null,
  filename text,
  duration_seconds integer,
  features_timeline jsonb,  -- OpenSMILE特徴量（SUPERBでは空）
  selected_features_timeline jsonb,  -- SUPERB感情分析結果
  processing_time double precision,
  error text,
  status text default 'pending'
);
```

### selected_features_timelineの構造
```json
[
  {
    "chunk_id": 1,
    "start_time": 0.0,
    "end_time": 30.0,
    "duration": 30.0,
    "emotions": [
      {
        "label": "hap",
        "score": 0.387932,
        "percentage": 38.793,
        "name_ja": "喜び",
        "name_en": "Happy",
        "group": "positive_active"
      }
      // ... 他の7感情
    ],
    "primary_emotion": {
      "label": "hap",
      "score": 0.387932,
      "percentage": 38.793,
      "name_ja": "喜び",
      "name_en": "Happy",
      "group": "positive_active"
    }
  }
  // ... 他のチャンク
]
```

## ⚙️ 技術仕様

### 処理フロー
1. S3から音声ファイルをダウンロード
2. 30秒チャンクに分割
3. 各チャンクをwav2vec2-base-superb-erで分析
4. 結果をSupabaseの`selected_features_timeline`に保存
5. `audio_files`テーブルのステータスを更新

### モデル仕様
- **モデル**: `superb/wav2vec2-base-superb-er` (Hugging Face)
- **フレームワーク**: FastAPI + PyTorch
- **音声処理**: librosa (16kHz リサンプリング)
- **サンプリングレート**: 16kHz (自動変換)
- **対応フォーマット**: WAV, MP3, その他soundfile対応形式

## 📈 パフォーマンス

- **30秒音声**: 約2-3秒で処理
- **60秒音声（2チャンク）**: 約5秒で処理
- **メモリ使用量**: 約1-2GB（モデル + 処理中のデータ）

## ⚠️ 既知の制限事項

### 精度に関する注意
- **英語データでの訓練**: このモデルは主に英語データで訓練されています
- **感情の誤認識**: 怒りの音声が「喜び」として認識される場合があります
- **音質の影響**: ノイズが多い環境では精度が低下します
- **推奨**: 全体的な感情グループ（negative_active等）で判断することを推奨

### 技術的制限
- 30秒を超える音声は自動的に分割処理
- 極端に長い音声（10分以上）は処理時間が長くなります

## 🐛 トラブルシューティング

### ポート8018が使用中
```bash
# 使用中のプロセスを確認
lsof -i :8018
# 必要に応じてプロセスを終了
kill -9 <PID>
```

### モデルのダウンロードが遅い
初回実行時は約400MBのモデルをダウンロードするため時間がかかります。安定したネットワーク環境で実行してください。

### S3アクセスエラー
AWS認証情報と権限を確認してください。

## 🏗️ プロジェクト構成

```
superb/
├── main.py                    # FastAPIアプリケーション（OpenSMILE互換）
├── main_original.py           # 元のローカル版実装
├── models.py                  # Pydanticモデル定義
├── supabase_service.py        # Supabaseサービスレイヤー
├── requirements.txt           # 依存パッケージ
├── .env                      # 環境変数設定（要作成）
├── test_model.py             # モデル動作確認スクリプト
├── generate_test_audio.py    # テスト音声生成
├── test_*.wav                # テスト音声ファイル
└── README.md                 # このファイル
```

## 📝 ライセンス

このプロジェクトで使用しているモデル：
- wav2vec2-base-superb-er: Apache License 2.0

## 🤝 貢献

バグ報告や機能リクエストは、Issueを作成してください。