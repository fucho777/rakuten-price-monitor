#!/bin/bash

# JSONファイルをバックアップするスクリプト
# GitHubアクションの最初と最後に実行することで、ファイルの変更を追跡

# 現在時刻のタイムスタンプを生成
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# バックアップディレクトリを作成
BACKUP_DIR="json_backups"
mkdir -p $BACKUP_DIR

echo "JSONファイルのバックアップを開始します: $TIMESTAMP"

# notifiable_products.jsonのバックアップ
if [ -f "notifiable_products.json" ]; then
    cp notifiable_products.json "$BACKUP_DIR/notifiable_products_$TIMESTAMP.json"
    echo "notifiable_products.jsonをバックアップしました"
    echo "ファイルサイズ: $(wc -c < notifiable_products.json) バイト"
    echo "内容:"
    cat notifiable_products.json
else
    echo "notifiable_products.jsonが見つかりません"
    echo "{}" > notifiable_products.json
    echo "空のnotifiable_products.jsonを作成しました"
fi

# notification_history.jsonのバックアップ
if [ -f "notification_history.json" ]; then
    cp notification_history.json "$BACKUP_DIR/notification_history_$TIMESTAMP.json"
    echo "notification_history.jsonをバックアップしました"
    echo "ファイルサイズ: $(wc -c < notification_history.json) バイト"
else
    echo "notification_history.jsonが見つかりません"
    echo "{}" > notification_history.json
    echo "空のnotification_history.jsonを作成しました"
fi

echo "バックアッププロセスが完了しました"
echo "バックアップディレクトリ: $BACKUP_DIR"
ls -la $BACKUP_DIR

# バックアップファイルもGitに追加
git add $BACKUP_DIR/*.json
echo "バックアップファイルをGitに追加しました"
