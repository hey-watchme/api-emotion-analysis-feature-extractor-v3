#!/bin/bash

# SUPERB API 本番環境デプロイスクリプト
# 本番環境（EC2: 3.24.16.82）で実行してください

echo "========================================="
echo "SUPERB API 本番環境デプロイ開始"
echo "========================================="

# 作業ディレクトリに移動
cd /home/ubuntu/api_superb_v1 || exit 1

# 1. ECRにログイン
echo "1. ECRにログイン中..."
aws ecr get-login-password --region ap-southeast-2 | docker login --username AWS --password-stdin 754724220380.dkr.ecr.ap-southeast-2.amazonaws.com

# 2. 最新のDockerイメージをプル
echo "2. 最新のDockerイメージをプル中..."
docker pull 754724220380.dkr.ecr.ap-southeast-2.amazonaws.com/watchme-api-superb:latest

# 3. 現在のコンテナを確認
echo "3. 現在のSUPERB APIコンテナを確認..."
docker ps | grep superb-api

# 4. docker-composeでサービスを再起動
echo "4. docker-composeでサービスを再起動中..."
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d

# 5. 起動確認（少し待機）
echo "5. サービス起動を確認中..."
sleep 10

# 6. コンテナの状態を確認
echo "6. コンテナの状態確認..."
docker ps | grep superb-api

# 7. ログを確認（最後の20行）
echo "7. 起動ログ確認..."
docker logs superb-api --tail 20

# 8. ヘルスチェック
echo "8. ヘルスチェック実行..."
curl -s http://localhost:8018/health | python3 -m json.tool

echo ""
echo "========================================="
echo "デプロイ完了！"
echo "========================================="
echo ""
echo "確認用コマンド："
echo "  ローカルヘルスチェック: curl http://localhost:8018/health"
echo "  外部ヘルスチェック: curl https://api.hey-watch.me/emotion-features/health"
echo "  ログ確認: docker logs superb-api --tail 50 -f"
echo "  Swagger UI: https://api.hey-watch.me/emotion-features/docs"