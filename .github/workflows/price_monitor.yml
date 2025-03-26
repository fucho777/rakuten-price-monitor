name: 楽天価格監視と投稿

on:
  schedule:
    - cron: '0 */3 * * *'  # 3時間ごとに実行
  workflow_dispatch:  # 手動実行も可能に

jobs:
  monitor-and-post:
    runs-on: ubuntu-latest
    permissions:
      contents: write  # GitHubリポジトリの内容を変更する権限を明示的に指定
    steps:
      - name: リポジトリをチェックアウト
        uses: actions/checkout@v3
        with:
          fetch-depth: 0  # 完全な履歴を取得
      
      - name: 最新の変更を取得
        run: |
          git pull origin main
        
      - name: Pythonセットアップ
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
          
      - name: 依存関係キャッシュ
        uses: actions/cache@v3
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}
          restore-keys: |
            ${{ runner.os }}-pip-
          
      - name: 依存関係インストール
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          
      - name: 通知履歴ファイルの存在確認
        run: |
          if [ ! -f "notification_history.json" ]; then
            echo "{}" > notification_history.json
            echo "通知履歴ファイルを初期化しました"
          fi
          
      - name: 楽天商品価格監視を実行
        env:
          RAKUTEN_APP_ID: ${{ secrets.RAKUTEN_APP_ID }}
          RAKUTEN_AFFILIATE_ID: ${{ secrets.RAKUTEN_AFFILIATE_ID }}
          PRICE_CHANGE_THRESHOLD: ${{ secrets.PRICE_CHANGE_THRESHOLD || '5' }}
        run: python monitor.py
        
      - name: スレッズに投稿
        env:
          THREADS_APP_ID: ${{ secrets.THREADS_APP_ID }}
          THREADS_APP_SECRET: ${{ secrets.THREADS_APP_SECRET }}
          THREADS_LONG_LIVED_TOKEN: ${{ secrets.THREADS_LONG_LIVED_TOKEN }}
          THREADS_INSTAGRAM_ACCOUNT_ID: ${{ secrets.THREADS_INSTAGRAM_ACCOUNT_ID }}
        run: python threads_poster.py
        
      # Twitter投稿ステップ（コメントアウト解除で有効化）
      #- name: X(Twitter)に投稿
      #  env:
      #    TWITTER_API_KEY: ${{ secrets.TWITTER_API_KEY }}
      #    TWITTER_API_SECRET: ${{ secrets.TWITTER_API_SECRET }}
      #    TWITTER_ACCESS_TOKEN: ${{ secrets.TWITTER_ACCESS_TOKEN }}
      #    TWITTER_ACCESS_TOKEN_SECRET: ${{ secrets.TWITTER_ACCESS_TOKEN_SECRET }}
      #  run: python twitter_poster.py
        
      - name: JSONファイルの内容を確認（デバッグ用）
        run: |
          echo "notifiable_products.jsonの内容確認:"
          if [ -f "notifiable_products.json" ]; then
            cat notifiable_products.json
            echo "ファイルサイズ: $(wc -c < notifiable_products.json) バイト"
          else
            echo "ファイルが存在しません"
          fi
          
          echo "notification_history.jsonの内容確認:"
          if [ -f "notification_history.json" ]; then
            cat notification_history.json
            echo "ファイルサイズ: $(wc -c < notification_history.json) バイト"
          else
            echo "ファイルが存在しません"
          fi
        
      - name: データ更新をコミット
        run: |
          git config --global user.name 'GitHub Actions'
          git config --global user.email 'actions@github.com'
          
          # 変更ファイルを検出して追加
          for file in price_history.csv product_list.csv twitter_posting_log.csv threads_posting_log.csv notifiable_products.json notification_history.json; do
            if [ -f "$file" ]; then
              echo "ファイル $file を追加します"
              git add "$file"
            else
              echo "ファイル $file が見つかりません"
            fi
          done
          
          # 特に notification_history.json を確実に追加
          if [ -f "notification_history.json" ]; then
            git add notification_history.json
            echo "notification_history.json を明示的に追加しました"
          fi
          
          # 特に notifiable_products.json を確実に追加
          if [ -f "notifiable_products.json" ]; then
            git add notifiable_products.json
            echo "notifiable_products.json を明示的に追加しました"
          fi
          
          # コミットする変更があるかチェック
          if ! git diff --staged --quiet; then
            git commit -m "🤖 価格データ更新: $(date +%Y-%m-%d-%H:%M)"
            git push origin main
            echo "変更をコミットしました"
          else
            echo "コミットする変更はありません"
          fi
