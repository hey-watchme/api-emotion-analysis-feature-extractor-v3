# Hume AI Emotion Recognition API v3

## 概要

Hume AIの Speech Prosody、Vocal Burst、Language モデルを使用した48感情分析APIです。
音声の韻律、非言語音声、テキスト内容から詳細な感情を分析します。

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

## トラブルシューティング

### 低品質音声の場合

Hume APIは低品質音声を処理できません。この場合:
- エラーとして記録
- `emotion_features_result_hume` に error フラグを保存
- 欠損データとして扱う

### ヘルスチェックエラー

```bash
# EC2でコンテナ状態確認
docker ps | grep emotion-analysis-hume

# ログ確認
docker logs emotion-analysis-hume --tail 100
```

## 関連ドキュメント

- [実装計画書](./IMPLEMENTATION_PLAN.md)
- [システム全体構成](/projects/watchme/server-configs/docs/README.md)
- [技術仕様](/projects/watchme/server-configs/docs/TECHNICAL_REFERENCE.md)

## ライセンス

プライベートリポジトリ

---

最終更新: 2026-01-09