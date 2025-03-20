# rakuten-price-monitor
# 楽天商品価格監視システム

このリポジトリは、楽天の商品価格と在庫状態を定期的に監視し、価格下落や在庫復活があった場合にX(Twitter)やスレッズに自動投稿するシステムです。GitHub Actionsを使用して定期的に実行されます。

## 機能

- JANコードをもとに楽天APIで商品情報を自動取得
- 商品の価格と在庫状態を定期的に監視
- 価格下落率が設定閾値を超えた場合に通知
- 在庫が「なし→あり」に変化した場合に再入荷通知
- X(Twitter)とスレッズへの自動投稿
- 価格履歴の記録と管理

## セットアップ方法

### 1. リポジトリをフォーク

このリポジトリをあなたのGitHubアカウントにフォークします。

### 2. シークレット設定

リポジトリの「Settings」→「Secrets and variables」→「Actions」で以下のシークレットを設定します：

**楽天API関連**:
- `RAKUTEN_APP_ID`: 楽天APIのアプリケーションID
- `RAKUTEN_AFFILIATE_ID`: 楽天アフィリエイトID（オプション）

**X(Twitter)API関連**:
- `TWITTER_API_KEY`: Twitter APIキー
- `TWITTER_API_SECRET`: Twitter APIシークレット
- `TWITTER_ACCESS_TOKEN`: Twitterアクセストークン
- `TWITTER_ACCESS_TOKEN_SECRET`: Twitterアクセストークンシークレット

**スレッズAPI関連**:
- `THREADS_APP_ID`: Meta Developer AppのID
- `THREADS_APP_SECRET`: Meta Developer Appのシークレット
- `THREADS_LONG_LIVED_TOKEN`: Meta長期アクセストークン（オプション）
- `THREADS_INSTAGRAM_ACCOUNT_ID`: スレッズに連携したInstagramアカウントのID

**その他の設定**:
- `PRICE_CHANGE_THRESHOLD`: 通知する価格変動閾値（％）（デフォルト: 5）

### 3. 監視する商品を追加

`product_list.csv`ファイルに監視したい商品のJANコードを追加します。基本的にはJANコードのみの追加で大丈夫です。残りの情報（商品名、価格など）は初回実行時に自動的に取得されます。

例:
```
jan_code,product_name,last_price,last_availability,monitor_flag,notified_flag
4901234567890,,,unknown,TRUE,FALSE
4902345678901,,,unknown,TRUE,FALSE
```

### 4. ワークフローの有効化

リポジトリの「Actions」タブを開き、ワークフローを有効化します。その後、「楽天価格監視と投稿」ワークフローを選択し、「Run workflow」ボタンでテスト実行できます。

## 使用方法

### 商品の追加

監視したい商品のJANコードを`product_list.csv`に追加します。既存の行のフォーマットに従って追加してください。

### 手動実行

1. リポジトリの「Actions」タブを開きます
2. 「楽天価格監視と投稿」ワークフローを選択します
3. 「Run workflow」ボタンをクリックします

### 投稿プラットフォームの選択

X(Twitter)またはスレッズのいずれかだけに投稿したい場合は、`.github/workflows/price_monitor.yml`ファイルを編集して、不要なプラットフォームの投稿ステップをコメントアウトします。

## ファイル構成

- `monitor.py`: 価格監視のメインスクリプト
- `twitter_poster.py`: X(Twitter)投稿スクリプト
- `threads_poster.py`: スレッズ投稿スクリプト
- `product_list.csv`: 監視対象の商品リスト
- `price_history.csv`: 価格履歴データ
- `.github/workflows/price_monitor.yml`: GitHub Actionsワークフロー設定

## 注意事項

- 楽天APIには呼び出し回数の制限があります。多数の商品を監視する場合は実行頻度を調整してください。
- スレッズAPIはMeta Graph APIを使用しています。アプリの設定と権限が適切に構成されていることを確認してください。
- 商品数が多い場合、GitHubリポジトリのサイズが時間とともに大きくなる可能性があります。定期的に古いデータをクリーンアップすることをお勧めします。

## ライセンス

このプロジェクトは[MITライセンス](LICENSE)の下で公開されています。

## 謝辞

- 楽天商品検索APIを提供していただいている楽天様
- スクリプトのホスティングとワークフローの実行環境を提供していただいているGitHub様

---

不明点や問題がある場合は、Issueを作成してください。
