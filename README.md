# Hume AI Emotion Recognition API v3

## 概要

Hume AIの Speech Prosody、Vocal Burst、Language モデルを使用した48感情分析APIです。
音声の韻律、非言語音声、テキスト内容から詳細な感情を分析します。

## 🗺️ ルーティング詳細

| 項目 | 値 | 説明 |
|------|-----|------|
| **🏷️ サービス名** | Emotion Features API | 48感情分析（Hume AI） |
| **📦 モデル** | Hume AI Speech Prosody + Vocal Burst + Language | Speech Prosody (韻律), Vocal Burst (非言語音), Language (テキスト) |
| | | |
| **🌐 外部アクセス（Nginx）** | | |
| └ 公開エンドポイント | `https://api.hey-watch.me/emotion-analysis/features/` | ✅ v2と同じエンドポイント（完全置き換え） |
| └ Nginx設定ファイル | `/etc/nginx/sites-available/api.hey-watch.me` | 既存設定を継続使用 |
| └ proxy_pass先 | `http://localhost:8018/` | 内部転送先（v2と同じポート） |
| └ タイムアウト | 180秒 | read/connect/send |
| | | |
| **🔌 API内部エンドポイント** | | |
| └ ヘルスチェック | `/health` | GET |
| └ ルート情報 | `/` | GET - API情報表示 |
| └ **非同期処理（重要）** | `/async-process` | POST - Lambda ser-workerが呼ぶべきエンドポイント |
| | | |
| **🐳 Docker/コンテナ** | | |
| └ コンテナ名 | `emotion-analysis-feature-extractor` | `docker ps`で表示される名前（v2と同じ） |
| └ ポート（内部） | 8018 | コンテナ内（v2と同じ） |
| └ ポート（公開） | `127.0.0.1:8018:8018` | ローカルホストのみ |
| └ ヘルスチェック | `/health` | Docker healthcheck |
| | | |
| **☁️ AWS ECR** | | |
| └ リポジトリ名 | `watchme-emotion-analysis-feature-extractor` | イメージ保存先（v2と同じ） |
| └ リージョン | ap-southeast-2 (Sydney) | |
| └ URI | `754724220380.dkr.ecr.ap-southeast-2.amazonaws.com/watchme-emotion-analysis-feature-extractor:latest` | |
| | | |
| **⚙️ systemd** | | |
| └ サービス名 | （systemd未使用） | Docker Composeで直接起動 |
| └ 起動コマンド | `docker-compose up -d` | |
| └ 自動起動 | enabled | サーバー再起動時に自動起動 |
| | | |
| **📂 ディレクトリ** | | |
| └ ソースコード | `/Users/kaya.matsumoto/projects/watchme/api/emotion-analysis/feature-extractor-v3` | ローカル |
| └ GitHubリポジトリ | `hey-watchme/api-emotion-analysis-feature-extractor-v3` | |
| └ EC2配置場所 | `/home/ubuntu/emotion-analysis-feature-extractor` | 設定ファイル・.env配置先（v2と同じ） |
| | | |
| **🔗 呼び出し元** | | |
| └ Lambda関数 | `watchme-ser-worker` | SQS: ser-queue-v2.fifo からトリガー |
| └ 呼び出しURL | `https://api.hey-watch.me/emotion-analysis/features/async-process` | ✅ v2と同じパス |
| └ 環境変数 | `API_BASE_URL=https://api.hey-watch.me` | Lambda内 |
| └ Docker内部通信 | `http://emotion-analysis-feature-extractor:8018/async-process` | watchme-network経由 |

### ✅ v2完全置き換え完了（2026-01-09）

**変更内容:**
- Kushinada v2（4感情）→ Hume AI v3（48感情）
- 同じECRリポジトリ・同じポート・同じコンテナ名で完全置き換え
- Lambda ser-workerは変更不要（同じエンドポイント）
- Nginx設定も変更不要（同じproxy_pass先）

## 特徴

- **48種類の感情分析**: Kushinada v2の4感情から大幅に拡張
- **3つのモデル同時使用**:
  - Speech Prosody: 話し声の韻律分析
  - Vocal Burst: 笑い声、うめき声などの非言語音声
  - Language: テキスト内容の感情分析
- **自動セグメント分割**: 発話単位で自動的に分割
- **高速処理**: 外部API利用により約12秒で処理完了

## エンドポイント

| パス | メソッド | 説明 |
|------|----------|------|
| `/` | GET | API情報 |
| `/health` | GET | ヘルスチェック |
| `/async-process` | POST | 非同期感情分析（202 Accepted） |
| `/docs` | GET | API仕様書（Swagger UI） |

## 技術スタック

- FastAPI 0.115.0
- Python 3.12
- Hume AI API v0
- Docker
- AWS (S3, SQS, ECR)
- Supabase

## ローカル開発

### 環境構築

```bash
# リポジトリクローン
git clone https://github.com/hey-watchme/api-emotion-analysis-feature-extractor-v3.git
cd api-emotion-analysis-feature-extractor-v3

# 環境変数設定
cp .env.example .env
# .envファイルを編集してAPIキーを設定

# Python仮想環境
python3 -m venv venv
source venv/bin/activate

# 依存関係インストール
pip install -r requirements.txt
```

### ローカル起動

```bash
# 開発サーバー起動
python main.py
```

http://localhost:8019 でアクセス可能

## デプロイ

### GitHub経由の自動デプロイ

```bash
git add .
git commit -m "feat: update feature"
git push origin main
```

GitHub Actionsが自動的に:
1. Dockerイメージをビルド
2. AWS ECRにプッシュ
3. EC2にデプロイ
4. ヘルスチェック実行

### 手動デプロイ

```bash
# EC2に接続
ssh -i ~/watchme-key.pem ubuntu@3.24.16.82

# サービスディレクトリに移動
cd /home/ubuntu/emotion-analysis-hume

# コンテナ再起動
docker-compose down
docker-compose pull
docker-compose up -d

# ログ確認
docker logs emotion-analysis-hume -f
```

## データベース

### Supabase `spot_features` テーブル

新規カラム: `emotion_features_result_hume` (JSONB)

```json
{
  "provider": "hume",
  "version": "3.0.0",
  "confidence": 0.936,
  "detected_language": "ja",
  "total_segments": 27,
  "speech_prosody": {
    "segments": [...]
  },
  "vocal_burst": {
    "segments": [...]
  },
  "language": {
    "segments": [...]
  }
}
```

## 環境変数

必須の環境変数は `.env.example` を参照してください。

主要な設定:
- `HUME_API_KEY`: Hume API キー
- `HUME_SECRET_KEY`: Hume Secret キー
- `SUPABASE_URL`: SupabaseプロジェクトURL
- `SUPABASE_KEY`: Supabase Service Role Key

## 実装状況（2026-01-09）

### ✅ 完了
- Hume AI v3実装完了（Speech Prosody + Vocal Burst + Language）
- v2完全置き換え（同ECR/ポート/コンテナ名）
- GitHub Actions CI/CD設定
- EC2デプロイ成功
- Supabase `emotion_features_result_hume` カラム追加完了

### ⚠️ 修正済み問題
1. **Hume API認証**: Basic認証→`X-Hume-Api-Key`ヘッダーに修正
2. **Supabase**: `updated_at`/`id`カラム参照を削除
3. **環境変数**: 手動で`.env`修正（GitHub Actions変数渡しに問題）

### 🧪 テスト状況
- ヘルスチェック: ✅ `status: healthy`
- `/async-process`: ✅ 202 Accepted返却
- **次回デプロイ後に実音声でテスト必要**

### 💰 コスト
- **$0.0639/分**（Audio: Prosody+Burst+Language+Transcription）
- 1デバイス（48分/日）: **$92.1/月**
- フリープラン制限は要確認

## トラブルシューティング

### 環境変数が読み込まれない
```bash
ssh ubuntu@3.24.16.82
cd /home/ubuntu/emotion-analysis-feature-extractor
cat .env  # 内容確認
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d
```

### ヘルスチェック
```bash
curl http://localhost:8018/health
docker logs emotion-analysis-feature-extractor --tail 100
```

## 関連ドキュメント

- [実装計画書](./IMPLEMENTATION_PLAN.md)
- [システム全体構成](/projects/watchme/server-configs/docs/README.md)
- [技術仕様](/projects/watchme/server-configs/docs/TECHNICAL_REFERENCE.md)

## ライセンス

プライベートリポジトリ

---

最終更新: 2026-01-09