# Hume API Speech Prosody 実装計画書

最終更新: 2026-01-09

---

## 📋 目次

1. [プロジェクト概要](#プロジェクト概要)
2. [Hume API仕様](#hume-api仕様)
3. [テスト結果](#テスト結果)
4. [実装計画](#実装計画)
5. [重要な発見事項](#重要な発見事項)
6. [データベース設計](#データベース設計)
7. [次回セッションでの実装タスク](#次回セッションでの実装タスク)
8. [参考リソース](#参考リソース)

---

## プロジェクト概要

### 目的
WatchMeプラットフォームの感情分析APIを、Kushinada（4感情）からHume AI Speech Prosody（48感情）に移行し、より詳細な心理状態把握を実現する。

### 新規API情報
- **ディレクトリ**: `/Users/kaya.matsumoto/projects/watchme/api/emotion-analysis/feature-extractor-v3`
- **ポート**: 8019（v2は8018）
- **エンドポイント**: `https://api.hey-watch.me/emotion-analysis/hume/`
- **命名規則**: `feature-extractor-v3`（既存の命名規則に準拠）

### v2（Kushinada）との比較

| 項目 | Kushinada v2 | Hume API v3 |
|------|-------------|-------------|
| **感情数** | 4種類 | **48種類** |
| **処理方式** | ローカルモデル実行 | **外部API** |
| **処理時間** | 40-60秒 | **12秒** |
| **セグメント分割** | 手動（10秒固定） | **自動（発話単位）** |
| **STT** | 別途Deepgram API | **内蔵** |
| **メモリ消費** | 3-3.5GB | **軽量** |
| **低品質音声** | ✅ 処理可能 | ❌ 処理不可 |

---

## Hume API仕様

### 利用可能なモデル一覧

Hume APIは音声・映像・テキストから感情を分析する複数のモデルを提供しています。

#### 音声分析モデル（WatchMeで使用）

| モデル | 対象 | 感情数 | 説明 |
|--------|------|--------|------|
| **Speech Prosody** | 発話（言語的な音声） | 48感情 | 話し声の韻律（トーン・リズム・音色）を分析 |
| **Vocal Burst** | 非言語的発声 | 48感情 | 笑い声、ため息、うめき声、叫び声などを分析 |
| **Language** | テキスト | 53感情 | 文字起こし結果から言葉の感情的トーンを分析 |

#### 映像分析モデル（WatchMeでは未使用）

| モデル | 対象 | 感情数 | 説明 |
|--------|------|--------|------|
| **Face** | 顔の表情 | 48感情 | 微細な表情変化を分析 |
| **FACS 2.0** | 顔の筋肉 | N/A | Action Units（顔の筋肉の動き）を検出 |

#### モデルの自動分類

**重要**: 音声ファイルに話し声とうめき声が混在している場合、Hume APIが自動的に分類します。

```
音声ファイル（話し声 + うめき声が混在）
  ↓
Hume API（自動分類）
  ├─ 話し声の部分 → Speech Prosodyモデル
  ├─ うめき声の部分 → Vocal Burstモデル
  └─ テキスト → Languageモデル
  ↓
統合された結果が1つのレスポンスで返る
```

**実装への影響**:
- ✅ 複数モデルを1回のAPI呼び出しでリクエスト可能
- ✅ 分類は自動（手動での統合処理は不要）
- ✅ 結果は時系列で整理されて返される

#### 推奨モデル構成

WatchMeでは以下の3モデルを同時使用することを推奨：

```json
{
  "models": {
    "prosody": {},    // 話し声の韻律分析
    "burst": {},      // 非言語的発声の分析
    "language": {}    // テキストの感情トーン分析
  },
  "transcription": {
    "language": "ja"
  }
}
```

**各モデルの役割**:
1. **Speech Prosody**: 「どう言ったか」を分析
2. **Vocal Burst**: 「うめき声・笑い声」を分析
3. **Language**: 「何を言ったか」を分析

### 認証情報

```bash
API_KEY: KfIbNPRXVKeeroy7ulb67yzey6L6l9DDl45VODugUdBpGmln
SECRET_KEY: moe38Y09igpLd0a3gU3BCMfBGuv0f2rSdwuGJReJVX1DVwxYYUfoumPTAS2GBdoc
```

### APIエンドポイント

#### 1. ジョブ作成（Job Creation）

```bash
POST https://api.hume.ai/v0/batch/jobs
```

**リクエスト例**:
```json
{
  "models": {
    "prosody": {
      "granularity": "utterance",
      "window": {"length": 4, "step": 1},
      "identify_speakers": false
    }
  },
  "transcription": {
    "language": "ja",
    "confidence_threshold": 0.5
  },
  "urls": ["https://s3-url/audio.wav"]
}
```

**レスポンス**:
```json
{
  "job_id": "908c9fae-1290-4776-9e37-b1a8d1a03fea"
}
```

#### 2. ジョブステータス確認

```bash
GET https://api.hume.ai/v0/batch/jobs/{job_id}
```

**レスポンス**:
```json
{
  "job_id": "...",
  "state": {
    "status": "COMPLETED",
    "num_predictions": 27,
    "num_errors": 0
  }
}
```

#### 3. 結果取得

```bash
GET https://api.hume.ai/v0/batch/jobs/{job_id}/predictions
```

**レスポンス構造**: 後述の「レスポンス形式」参照

### レスポンス形式

#### 全体構造

```json
[{
  "source": {
    "type": "url",
    "url": "..."
  },
  "results": {
    "predictions": [{
      "file": "audio.wav",
      "file_type": "audio",
      "models": {
        "prosody": {
          "metadata": {
            "confidence": 0.936,
            "detected_language": "ja"
          },
          "grouped_predictions": [{
            "id": "unknown",
            "predictions": [
              // セグメント配列
            ]
          }]
        }
      }
    }],
    "errors": []
  }
}]
```

#### セグメント構造

```json
{
  "text": "あんまり自分が賢いと思ってるんじゃねーぞ",
  "time": {
    "begin": 4.22,
    "end": 6.64
  },
  "confidence": 0.9273926,
  "speaker_confidence": null,
  "emotions": [
    {"name": "Admiration", "score": 0.013},
    {"name": "Adoration", "score": 0.012},
    // ... 48感情すべて
  ]
}
```

### 重要なパラメータ

#### `transcription.language`
- **推奨値**: `"ja"`（日本語を明示）
- **効果**:
  - テキストが自然な日本語になる（スペースなし）
  - 処理が高速化（言語検出をスキップ）

**言語指定なし**:
```
"text": "あ ん ま り 自 分 が 賢 い と ..."
```

**言語指定あり (`ja`)**:
```
"text": "あんまり自分が賢いと..."
```

#### `transcription.confidence_threshold`
- **デフォルト**: `0.5`（50%）
- **意味**: STT（文字起こし）の最低信頼度
- **低品質音声対応**: `0.0`に下げても発話検出できない場合あり
- **推奨**: デフォルト（0.5）を維持

---

## テスト結果

### テスト1: 通常品質音声（成功）

**ファイル**: `ja_anger_netflix_001.wav`（17MB、1分30秒）
- **処理時間**: 12秒
- **セグメント数**: 27個
- **Confidence**: 0.936（93.6%）
- **検出言語**: `ja`

**Top 3セグメント例**:

| セグメント | 時間 | テキスト | Top感情 |
|-----------|------|---------|---------|
| 2 | 4.22-6.64秒 | あんまり自分が賢いと思ってるんじゃねーぞ | Doubt 13.48%, Determination 13.32% |
| 5 | 15.95-18.69秒 | 首になるのはお前の王だわし | **Anger 19.95%**, Confusion 18.92% |
| 27 | 85.88-95.06秒 | めて想動ぐらいしすぎろよす | **Anger 26.6%**, Fear 8.6% |

**サンプルJSON**: `/Users/kaya.matsumoto/projects/watchme/api/emotion-analysis/feature-extractor-v3/hume-api-samples/ja_anger_netflix_001_readable.json`

### テスト2: 低品質音声（失敗）

**ファイル**: `children_low-quality_001.wav`（1.8MB）
- **処理時間**: 15秒
- **セグメント数**: 0個
- **Confidence**: 0.0（0%）
- **検出言語**: `null`
- **エラー**: `"transcript confidence (0.0) below threshold value (0.5)"`

**結論**: Hume APIは低品質音声を処理できない（最低音質要件あり）

---

## 実装計画

### ディレクトリ構造

```
/Users/kaya.matsumoto/projects/watchme/api/emotion-analysis/feature-extractor-v3/
├── app/
│   ├── __init__.py
│   ├── routes.py          # FastAPIルーティング
│   ├── hume_provider.py   # Hume APIクライアント
│   ├── models.py          # Pydanticモデル
│   └── services.py        # ビジネスロジック
├── main.py                # FastAPIアプリケーション
├── config.py              # 環境変数管理
├── supabase_service.py    # DB保存処理
├── requirements.txt
├── Dockerfile
├── docker-compose.prod.yml
├── .github/
│   └── workflows/
│       └── deploy-to-ecr.yml
├── hume-api-samples/      # テスト結果JSONファイル
├── README.md
├── IMPLEMENTATION_PLAN.md # このファイル
└── .env.example
```

### エンドポイント設計

#### 1. 非同期処理（Lambda呼び出し用）

```python
POST /async-process
```

**リクエスト**:
```json
{
  "file_path": "files/device_id/2025-01-09/10-00/audio.wav",
  "device_id": "device_id",
  "recorded_at": "2025-01-09T10:00:00Z"
}
```

**レスポンス**:
```json
{
  "status": "accepted",
  "job_id": "hume-job-id-..."
}
```

**処理フロー**:
1. 202 Accepted即座返却
2. バックグラウンドでHume API呼び出し
3. ジョブ結果をポーリング（数秒〜数十秒）
4. Supabaseに保存
5. SQS完了通知送信

#### 2. ヘルスチェック

```python
GET /health
```

**レスポンス**:
```json
{
  "status": "healthy",
  "service": "emotion-analysis-hume-api",
  "version": "3.0.0"
}
```

### 環境変数

```env
# Hume API
HUME_API_KEY=KfIbNPRXVKeeroy7ulb67yzey6L6l9DDl45VODugUdBpGmln
HUME_SECRET_KEY=moe38Y09igpLd0a3gU3BCMfBGuv0f2rSdwuGJReJVX1DVwxYYUfoumPTAS2GBdoc

# AWS
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=ap-southeast-2
S3_BUCKET_NAME=watchme-vault

# SQS
FEATURE_COMPLETED_QUEUE_URL=https://sqs.ap-southeast-2.amazonaws.com/754724220380/watchme-feature-completed-queue

# Supabase
SUPABASE_URL=https://qvtlwotzuzbavrzqhyvt.supabase.co
SUPABASE_KEY=

# API設定
API_PORT=8019
HUME_CONFIDENCE_THRESHOLD=0.5
HUME_POLL_INTERVAL=3
HUME_MAX_POLL_ATTEMPTS=40
```

### データベース保存形式

**テーブル**: `spot_features`
**カラム**: `emotion_features_result` (JSONB)

```json
{
  "provider": "hume",
  "version": "3.0.0",
  "metadata": {
    "confidence": 0.936,
    "detected_language": "ja",
    "total_segments": 27,
    "audio_duration": 90.0
  },
  "segments": [
    {
      "time": {"begin": 4.22, "end": 6.64},
      "text": "あんまり自分が賢いと思ってるんじゃねーぞ",
      "confidence": 0.927,
      "emotions": {
        "Doubt": 0.1348,
        "Determination": 0.1332,
        "Realization": 0.1275,
        "Anger": 0.0763,
        // ... 残り44感情
      }
    }
    // ... 残り26セグメント
  ]
}
```

### エラーハンドリング

#### 低品質音声への対応

```python
def process_audio(file_path):
    try:
        # 1. Hume API v3を試す
        result = hume_provider.analyze(file_path)

        if result.confidence < 0.5:
            # 2. 低品質の場合、フォールバックを検討
            logger.warning(f"Low confidence: {result.confidence}")
            # オプション: Kushinada v2へフォールバック
            # result = kushinada_provider.analyze(file_path)

        return result

    except HumeAPIError as e:
        logger.error(f"Hume API error: {e}")
        # SQSにエラー通知
        send_error_notification(file_path, str(e))
        raise
```

### requirements.txt

```txt
fastapi==0.115.0
uvicorn==0.34.0
pydantic==2.11.0
requests>=2.31.0
boto3==1.35.0
supabase==2.10.0
python-dotenv==1.0.0
tenacity>=8.2.0
```

### Docker設定

**Dockerfile**:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8019

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8019"]
```

**docker-compose.prod.yml**:
```yaml
version: '3.8'

services:
  emotion-analysis-hume:
    image: 754724220380.dkr.ecr.ap-southeast-2.amazonaws.com/watchme-emotion-analysis-feature-extractor-v3:latest
    container_name: emotion-analysis-hume
    ports:
      - "127.0.0.1:8019:8019"
    environment:
      - HUME_API_KEY=${HUME_API_KEY}
      - HUME_SECRET_KEY=${HUME_SECRET_KEY}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - AWS_REGION=${AWS_REGION}
      - S3_BUCKET_NAME=${S3_BUCKET_NAME}
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_KEY=${SUPABASE_KEY}
      - FEATURE_COMPLETED_QUEUE_URL=${FEATURE_COMPLETED_QUEUE_URL}
      - API_PORT=8019
    networks:
      - watchme-network
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8019/health"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  watchme-network:
    external: true
```

---

## 重要な発見事項

### 1. 感情分析の原理

✅ **純粋に音響情報（Prosody）のみを使用**

- **韻律（Prosody）**: トーン、リズム、音色
- **言語とは独立**: 「何を言ったか」ではなく「どう言ったか」
- **科学的根拠**: Nature論文に基づく大規模心理学研究

引用（公式ドキュメント）:
> "Speech prosody is distinct from language (words) and from non-linguistic vocal utterances"

**参考**: [About the Science | Hume API](https://dev.hume.ai/docs/resources/science)

### 2. 48感情の仕組み

❌ **間違った理解**: 「このセグメントはAngerとDoubtだけ検出された」
✅ **正しい理解**: 「全48感情が必ず出力され、スコアの強弱で表現される」

**比喩**: 音楽のイコライザー
- 全周波数帯が存在
- それぞれの強さ（音量）が異なる

**スコアの範囲**:
- 最小: 0.0（0%）
- 最大: 理論上1.0（100%）
- 実際の最大値: 0.266（26.6%）← Angerの最高スコア

**スコア評価基準**:
- **0.10以上** (10%以上): 非常に強い
- **0.05-0.10** (5-10%): 強い
- **0.03-0.05** (3-5%): 中程度
- **0.03未満** (3%未満): 弱い

### 3. セグメント分割

✅ **Hume APIは発話単位（utterance）で自動分割**

- セグメント長: 可変（0.5秒〜9秒）
- 分割基準: 発話の区切り
- 手動設定: 不要

**例**（27セグメント、90秒音声）:
```
セグメント1: 2.70-3.20秒 (0.50秒)
セグメント2: 4.22-6.64秒 (2.42秒)
セグメント27: 85.88-95.06秒 (9.18秒)
```

### 4. STT（文字起こし）

✅ **Prosody分析と同時にSTTも実行される**

- `"text"` フィールドが自動的に含まれる
- 別途STT APIを呼ぶ必要なし
- `confidence` = STTの精度（感情分析の信頼度ではない）

**メリット**:
- API呼び出し削減
- コスト削減
- 処理時間短縮

**既存Vibe Transcriber APIとの関係**:
- オプション1: 両方取得して比較
- オプション2: Hume APIに統一
- オプション3: Deepgramを継続（より高精度なSTTが必要な場合）

### 5. 低品質音声への対応

❌ **Hume APIは低品質音声を処理できない**

**エラー例**:
```
"transcript confidence (0.0) below threshold value (0.5)"
```

**原因**:
1. STTが前提（発話区間検出が必要）
2. 最低信頼度: 0.5（50%）
3. 閾値を0.0に下げても発話検出できない場合あり

**推奨対応**:
```python
# ハイブリッド戦略
if hume_result.confidence < 0.5:
    # Kushinada v2へフォールバック
    result = kushinada_v2.analyze(audio)
```

### 6. 言語指定の重要性

✅ **必ず `transcription.language = "ja"` を指定**

**効果**:
1. テキストが自然な日本語（スペースなし）
2. 処理高速化（言語検出スキップ）
3. 精度の安定化

### 7. 処理フロー

**ジョブベースの非同期処理**:

```
1. ジョブ作成 (POST /batch/jobs)
   ↓ 即座にjob_id返却

2. ポーリング (GET /batch/jobs/{id})
   ↓ status: QUEUED → PROCESSING → COMPLETED

3. 結果取得 (GET /batch/jobs/{id}/predictions)
   ↓ 48感情 x セグメント数

4. Supabase保存 + SQS通知
```

**推奨ポーリング設定**:
- 間隔: 3秒
- 最大試行回数: 40回（120秒）

---

## 参考リソース

### 公式ドキュメント

#### 主要ドキュメント
1. **Expression Measurement 概要**
   - URL: https://dev.hume.ai/docs/expression-measurement/overview
   - 内容: Speech Prosodyの概要、48感情の説明

2. **Batch API（REST）**
   - URL: https://dev.hume.ai/docs/expression-measurement/rest
   - 内容: バッチ処理の使い方、制限事項

3. **About the Science**
   - URL: https://dev.hume.ai/docs/resources/science
   - 内容: 感情分析の科学的根拠、Prosodyの原理

4. **FAQ**
   - URL: https://dev.hume.ai/docs/expression-measurement/faq
   - 内容: 言語サポート、制限事項

#### APIリファレンス
1. **Start Inference Job**
   - URL: https://dev.hume.ai/reference/expression-measurement-api/batch/start-inference-job
   - 内容: ジョブ作成のリクエスト/レスポンス仕様

2. **Get Job Predictions**
   - URL: https://dev.hume.ai/reference/expression-measurement-api/batch/get-job-predictions
   - 内容: 結果取得のレスポンス構造

3. **Get Job Status**
   - URL: https://dev.hume.ai/reference/expression-measurement-api/batch/get-job
   - 内容: ジョブステータス確認

#### その他
1. **API Keys取得方法**
   - URL: https://dev.hume.ai/docs/introduction/api-key
   - 内容: Hume Portalでのキー取得手順

2. **エラーコード**
   - URL: https://dev.hume.ai/docs/resources/errors
   - 内容: エラーハンドリング

### サンプルコード

#### GitHub公式サンプル
- URL: https://github.com/HumeAI/hume-api-examples
- 内容: Python/TypeScript/JavaScriptのサンプル

#### Python SDK（オプション）
- URL: https://github.com/HumeAI/hume-python-sdk
- 内容: 公式SDKを使った実装例
- **注意**: このプロジェクトでは `requests` を直接使用する方針

### WatchMeプロジェクト内の参考実装

#### transcriber-v2（最も参考になる）
- パス: `/Users/kaya.matsumoto/projects/watchme/api/vibe-analysis/transcriber-v2`
- 参考ポイント:
  - `app/asr_providers.py`: プロバイダー抽象化レイヤー
  - `app/routes.py`: `/async-process` エンドポイント実装
  - `main.py`: FastAPI構造
  - `.github/workflows/deploy-to-ecr.yml`: CI/CD設定

#### emotion-analysis feature-extractor-v2
- パス: `/Users/kaya.matsumoto/projects/watchme/api/emotion-analysis/feature-extractor-v2`
- 参考ポイント:
  - `supabase_service.py`: DB保存処理
  - `models.py`: Pydanticモデル定義

#### aggregator API
- パス: `/Users/kaya.matsumoto/projects/watchme/api/aggregator`
- 参考ポイント:
  - シンプルなFastAPI構造
  - `endpoints/` ディレクトリでのルーティング分割

### テストデータ

#### サンプルJSON
```
/Users/kaya.matsumoto/projects/watchme/api/emotion-analysis/feature-extractor-v3/hume-api-samples/
├── ja_anger_netflix_001_hume_result.json (言語指定なし)
├── ja_anger_netflix_001_hume_result_with_lang.json (言語指定あり)
└── ja_anger_netflix_001_readable.json (人間が読みやすい形式)
```

#### サンプル音声
```
/Users/kaya.matsumoto/projects/watchme/docs/sample-audio/
├── ja_anger_netflix_001.wav (17MB, 高品質) ✅ 処理成功
└── children_low-quality_001.wav (1.8MB, 低品質) ❌ 処理失敗
```

### WatchMeプロジェクト全体ドキュメント

```
/Users/kaya.matsumoto/projects/watchme/server-configs/docs/
├── README.md - システム全体の構成
├── PROCESSING_ARCHITECTURE.md - データ処理フロー
├── TECHNICAL_REFERENCE.md - 技術仕様
├── OPERATIONS_GUIDE.md - デプロイ・運用手順
└── CICD_STANDARD_SPECIFICATION.md - CI/CD設定
```

---

## データベース設計

### spot_features テーブルへの追加

**新規カラム**: `emotion_features_result_hume` (JSONB)

```sql
ALTER TABLE spot_features
ADD COLUMN emotion_features_result_hume JSONB;

-- インデックス追加（検索高速化）
CREATE INDEX idx_spot_features_emotion_hume
ON spot_features USING GIN (emotion_features_result_hume);
```

**命名規則の理由**:
- 既存: `emotion_features_result` (Kushinada v2)
- 新規: `emotion_features_result_hume` (Hume API v3)
- 同じ「感情分析」カテゴリで、プロバイダーをサフィックスで区別

### データ保存形式

#### 3モデルすべてを保存（推奨）

```json
{
  "provider": "hume",
  "api_version": "v0",
  "job_id": "hume-job-id",
  "confidence": 0.9297,
  "detected_language": "ja",

  "speech_prosody": {
    "total_segments": 11,
    "segments": [
      {
        "segment_id": 1,
        "time": {"begin": 0.14, "end": 0.64},
        "text": "さ",
        "confidence": 0.8169,
        "emotions": {
          "Excitement": 0.1951,
          "Anger": 0.1806,
          "Distress": 0.1254,
          // ... 48感情すべて
        }
      }
    ]
  },

  "vocal_burst": {
    "total_segments": 3,
    "segments": [
      {
        "segment_id": 1,
        "time": {"begin": 27.0, "end": 28.0},
        "emotions": {
          "Amusement": 0.7642,
          "Joy": 0.1823,
          // ... 48感情
        }
      }
    ]
  },

  "language": {
    "total_segments": 44,
    "segments": [
      {
        "segment_id": 1,
        "time": {"begin": 0.14, "end": 0.64},
        "text": "さ",
        "emotions": {
          "Confusion": 0.2101,
          "Calmness": 0.1181,
          // ... 53感情
        }
      }
    ]
  }
}
```

### 既存カラムとの関係

| カラム | データソース | 用途 |
|--------|------------|------|
| `transcription_result` | **Deepgram** | 正確なテキスト（優先使用） |
| `behavior_features_result` | PaSST | 527種類の音響イベント |
| `emotion_features_result` | Kushinada v2 | 4感情（旧バージョン） |
| `emotion_features_result_hume` | **Hume API v3** | **48感情 + 3モデル（新規）** |

### データ活用方針

#### 1. テキストの優先順位

```
優先度1: transcription_result (Deepgram)
優先度2: emotion_features_result_hume.speech_prosody[].text (参考程度)
```

**理由**: Deepgramの方が日本語認識精度が高い

#### 2. 感情分析の使い分け

**Spot分析（リアルタイム）**:
- Hume Speech Prosody → 韻律から感情
- Hume Vocal Burst → 笑い声・泣き声

**Daily/Weekly分析（累積）**:
- Hume Language → テキスト内容の感情トーン
- Deepgramテキストと組み合わせて高精度分析

#### 3. 48感情の集約

**カテゴリごとに集約**:

```json
{
  "negative_active": {
    "emotions": ["Anger", "Anxiety", "Distress", "Fear"],
    "total_score": 0.45
  },
  "negative_passive": {
    "emotions": ["Sadness", "Disappointment", "Boredom"],
    "total_score": 0.15
  },
  "positive_active": {
    "emotions": ["Joy", "Excitement", "Amusement"],
    "total_score": 0.30
  },
  "positive_passive": {
    "emotions": ["Calmness", "Contentment", "Satisfaction"],
    "total_score": 0.10
  }
}
```

---

## 次回セッションでの実装タスク

### 🎯 最優先タスク

#### 1. テスト結果の検証（30分）

- [x] ✅ 3つの音声でテスト完了
  - `2026-01-08/15-01-01` (中品質・子供の声)
  - `2026-01-05/16-01-01` (低品質・母親の叱責)
  - `ja_joy_happy-birthday_001` (高品質・笑い声あり)

**気づき**:
- ✅ Speech Prosody（韻律）は非常に有効
- ✅ Vocal Burst検出は音声品質に依存
- ⚠️ Hume内蔵STTは不正確（Deepgram併用必須）
- ✅ 3モデル同時使用で多面的評価可能

#### 2. データベーススキーマ追加（15分）

```bash
# Supabaseダッシュボードで実行
ALTER TABLE spot_features
ADD COLUMN emotion_features_result_hume JSONB;

CREATE INDEX idx_spot_features_emotion_hume
ON spot_features USING GIN (emotion_features_result_hume);
```

#### 3. API実装（2-3時間）

**優先順位**:

1. **`app/hume_provider.py`** - Hume API呼び出しロジック
   - ジョブ作成
   - ポーリング（3秒間隔、最大40回）
   - 結果取得・パース

2. **`app/models.py`** - Pydanticモデル定義
   - リクエスト/レスポンススキーマ
   - 3モデル対応の型定義

3. **`supabase_service.py`** - DB保存処理
   - `emotion_features_result_hume`への保存
   - 既存カラムとの併用

4. **`main.py`** - FastAPIアプリケーション
   - `/async-process` エンドポイント
   - バックグラウンド処理
   - SQS完了通知

5. **`requirements.txt`** - 依存関係

#### 4. ローカルテスト（30分）

```bash
# 構文チェック
python3 -m py_compile app/*.py
python3 -m py_compile main.py

# エンコーディング検証
file app/*.py main.py
```

**注意**: ローカルDockerは動作しないため、構文チェックのみ

#### 5. CI/CD設定（1時間）

- `.github/workflows/deploy-to-ecr.yml`
- GitHub Secrets追加（HUME_API_KEY, HUME_SECRET_KEY）
- docker-compose.prod.yml修正

### 📝 実装時の重要ポイント

#### ポイント1: 3モデルすべてリクエスト

```python
# Hume API リクエスト例
request_body = {
    "models": {
        "prosody": {},    # 必須
        "burst": {},      # 必須
        "language": {}    # 必須
    },
    "transcription": {
        "language": "ja",  # 必須（日本語明示）
        "confidence_threshold": 0.5
    },
    "urls": [presigned_url]
}
```

#### ポイント2: Deepgramテキストとの統合

```python
# データベース保存時
spot_data = {
    "transcription_result": deepgram_result,  # Deepgram（正確）
    "emotion_features_result_hume": {
        "speech_prosody": {...},  # Hume（感情）
        # Humeのtextは参考程度
    }
}
```

#### ポイント3: セグメント分割の違いを考慮

- Speech Prosody: utterance単位（粗い）
- Language: 単語/文字単位（細かい）
- **統合は不要**（別々に保存）

#### ポイント4: エラーハンドリング

```python
# 低品質音声対応
try:
    hume_result = await hume_provider.analyze(audio_url)
    if hume_result.confidence < 0.5:
        logger.warning(f"Low confidence: {hume_result.confidence}")
        # v2（Kushinada）へのフォールバックは将来検討
except HumeAPIError as e:
    logger.error(f"Hume API failed: {e}")
    # SQSエラー通知
```

### 🚀 デプロイ後の確認

1. **ヘルスチェック**
   ```bash
   curl https://api.hey-watch.me/emotion-analysis/hume/health
   ```

2. **実音声でテスト**
   ```bash
   # Lambda ser-workerから呼び出し
   # または直接curlで/async-processを呼ぶ
   ```

3. **データベース確認**
   ```sql
   SELECT
     device_id,
     recorded_at,
     emotion_features_result_hume->'speech_prosody'->'total_segments' as segments
   FROM spot_features
   WHERE emotion_features_result_hume IS NOT NULL
   LIMIT 5;
   ```

### 📋 チェックリスト

実装前に確認：
- [ ] GitHub Secretsに認証情報追加済み
- [ ] ポート8019が未使用であることを確認
- [ ] Nginx設定ファイルの準備
- [ ] Lambda ser-workerの修正方針決定

実装後に確認：
- [ ] 3モデルすべてのデータが保存されている
- [ ] Deepgramテキストが優先使用されている
- [ ] 処理時間が15秒以内
- [ ] エラー時のSQS通知が正常

---

## 次のステップ

### 実装タスク

1. ✅ Hume API仕様確認（完了）
2. ✅ テスト実行（完了）
3. ⏳ コード実装
   - [ ] `main.py` 作成
   - [ ] `app/hume_provider.py` 作成
   - [ ] `app/routes.py` 作成
   - [ ] `app/models.py` 作成
   - [ ] `supabase_service.py` 作成
   - [ ] `requirements.txt` 作成
   - [ ] `Dockerfile` 作成
   - [ ] `docker-compose.prod.yml` 作成
4. ⏳ GitHub Actions CI/CD設定
5. ⏳ EC2デプロイ・動作確認
6. ⏳ Nginx設定追加
7. ⏳ Lambda ser-worker修正（v3呼び出し追加）
8. ⏳ 本番環境で検証

### 確認事項

- [ ] 料金体系の確認（月間予算上限設定）
- [ ] v2との並行稼働期間の決定
- [ ] エラーハンドリング方針の最終確認
- [ ] 低品質音声のフォールバック戦略

---

## 48感情の日本語訳一覧

| No | English | 日本語 | 説明 |
|----|---------|--------|------|
| 1 | Admiration | 賞賛 | 尊敬や称賛の気持ち |
| 2 | Adoration | 崇拝 | 深い愛情や崇拝 |
| 3 | Aesthetic Appreciation | 美的鑑賞 | 美しさへの感動 |
| 4 | Amusement | 愉快 | 楽しさや面白さ |
| 5 | Anger | 怒り | 不満や敵意 |
| 6 | Anxiety | 不安 | 心配や緊張 |
| 7 | Awe | 畏敬 | 圧倒される驚き |
| 8 | Awkwardness | 気まずさ | 居心地の悪さ |
| 9 | Boredom | 退屈 | 興味の欠如 |
| 10 | Calmness | 平静 | 落ち着きや安らぎ |
| 11 | Concentration | 集中 | 注意を向けた状態 |
| 12 | Confusion | 混乱 | 理解できない状態 |
| 13 | Contemplation | 熟考 | 深く考える状態 |
| 14 | Contempt | 軽蔑 | 見下す気持ち |
| 15 | Contentment | 満足 | 心地よい充足感 |
| 16 | Craving | 渇望 | 強い欲求 |
| 17 | Desire | 欲望 | 何かを望む気持ち |
| 18 | Determination | 決意 | 固い意志 |
| 19 | Disappointment | 失望 | 期待外れの感情 |
| 20 | Disgust | 嫌悪 | 不快感や拒絶 |
| 21 | Distress | 苦悩 | 精神的苦痛 |
| 22 | Doubt | 疑念 | 確信が持てない状態 |
| 23 | Ecstasy | 恍惚 | 強烈な喜び |
| 24 | Embarrassment | 恥ずかしさ | きまりの悪さ |
| 25 | Empathic Pain | 共感的苦痛 | 他者の痛みへの共感 |
| 26 | Entrancement | 魅了 | 夢中になる状態 |
| 27 | Envy | 嫉妬 | 他者への羨望 |
| 28 | Excitement | 興奮 | 高揚した感情 |
| 29 | Fear | 恐怖 | 脅威への反応 |
| 30 | Guilt | 罪悪感 | 過ちへの後悔 |
| 31 | Horror | 戦慄 | 強い恐怖や嫌悪 |
| 32 | Interest | 興味 | 関心や好奇心 |
| 33 | Joy | 喜び | 幸福感 |
| 34 | Love | 愛 | 深い愛情 |
| 35 | Nostalgia | 郷愁 | 懐かしさ |
| 36 | Pain | 苦痛 | 身体的・精神的痛み |
| 37 | Pride | 誇り | 自尊心や達成感 |
| 38 | Realization | 気づき | 理解が訪れる瞬間 |
| 39 | Relief | 安堵 | 緊張からの解放 |
| 40 | Romance | ロマンス | 恋愛的な感情 |
| 41 | Sadness | 悲しみ | 喪失や失望 |
| 42 | Satisfaction | 達成感 | 満たされた気持ち |
| 43 | Shame | 恥 | 社会的な恥ずかしさ |
| 44 | Surprise (negative) | 驚き（ネガティブ） | 不快な驚き |
| 45 | Surprise (positive) | 驚き（ポジティブ） | 嬉しい驚き |
| 46 | Sympathy | 同情 | 他者への思いやり |
| 47 | Tiredness | 疲労 | 疲れた状態 |
| 48 | Triumph | 勝利感 | 成功の喜び |

---

**最終更新**: 2026-01-09
**作成者**: Claude Code
**バージョン**: 1.0.0
