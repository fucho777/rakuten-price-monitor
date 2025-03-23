import os
import json
import csv
import requests
from datetime import datetime

# ログ出力関数
def log_message(message_type, target, status, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{message_type}] [{target}] [{status}] {message}")

# スレッズ投稿用のメッセージを作成
def create_threads_message(product):
    # 価格変動の方向を示す矢印
    price_change_arrow = "↑" if product["price_change_rate"] > 0 else "↓"
    
    # 変動率（小数点2桁まで）
    change_rate_str = f"{abs(product['price_change_rate']):.2f}{price_change_arrow}"
    
    # 在庫状態の変化を示す文字列
    availability_status = product["current_availability"]
    if product["previous_availability"] != product["current_availability"]:
        if product["current_availability"] == "在庫あり":
            availability_status += "（再入荷）"
        elif product["current_availability"] == "在庫なし":
            availability_status += "（品切れ）"
    
    # スレッズ用（より詳細に）
    threads_msg = (
        f"【価格変動】\n"
        f"商品名：{product['product_name']}\n"
        f"価格：{product['current_price']:,}円（{change_rate_str}%）\n"
        f"前回：{product['previous_price']:,}円\n"
        f"在庫：{availability_status}\n"
        f"販売：{product['shop_name']}\n"
        f"{product['affiliate_url']}"
    )
    
    return threads_msg

# スレッズAPIにアクセストークンを取得
def get_threads_access_token():
    try:
        # Meta Graph APIの認証情報
        app_id = os.environ.get("THREADS_APP_ID")
        app_secret = os.environ.get("THREADS_APP_SECRET")
        long_lived_token = os.environ.get("THREADS_LONG_LIVED_TOKEN")
        
        # 長期アクセストークンが既に存在する場合はそれを使用
        if long_lived_token:
            log_message("Threads認証", "システム", "情報", "長期アクセストークンを使用します")
            return long_lived_token
        
        # クライアント認証情報が不足している場合はエラー
        if not all([app_id, app_secret]):
            raise ValueError("Threads API認証情報が不足しています")
        
        # アクセストークンリクエストURL
        token_url = "https://graph.facebook.com/v18.0/oauth/access_token"
        
        # リクエストパラメータ
        params = {
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "client_credentials"
        }
        
        # POSTリクエストを送信
        log_message("Threads認証", "システム", "進行中", "アクセストークンをリクエスト中...")
        response = requests.get(token_url, params=params)
        
        # レスポンスを確認
        if response.status_code == 200:
            response_data = response.json()
            access_token = response_data.get("access_token")
            log_message("Threads認証", "システム", "成功", "クライアントアクセストークンを取得しました")
            return access_token
        else:
            error_msg = f"アクセストークン取得エラー: ステータスコード {response.status_code}, レスポンス: {response.text}"
            log_message("Threads認証", "システム", "失敗", error_msg)
            raise ValueError(error_msg)
            
    except Exception as e:
        log_message("Threads認証", "システム", "失敗", f"エラー: {str(e)}")
        raise

# スレッズにAPIを使用して投稿する関数
def post_to_threads(message):
    try:
        # スレッズAPI認証情報
        access_token = get_threads_access_token()
        
        if not access_token:
            log_message("Threads投稿", "システム", "警告", "アクセストークンの取得に失敗しました")
            return {
                "success": False,
                "error": "アクセストークンが取得できません",
                "platform": "threads"
            }
        
        log_message("Threads投稿", "システム", "進行中", "ステップ1: コンテナID作成中...")
        
        # ステップ1: コンテナIDの作成（新しいエンドポイント）
        upload_url = "https://graph.threads.net/v1.0/me/threads"
        upload_params = {
            "access_token": access_token,
            "media_type": "TEXT",
            "text": message
        }
        
        # リクエスト送信
        upload_response = requests.post(upload_url, data=upload_params)
        
        if upload_response.status_code != 200:
            error_msg = f"コンテナ作成エラー: ステータスコード {upload_response.status_code}, レスポンス: {upload_response.text}"
            log_message("Threads投稿", "なし", "失敗", error_msg)
            return {
                "success": False,
                "error": error_msg,
                "platform": "threads"
            }
        
        # コンテナIDの取得
        try:
            container_id = upload_response.json().get("id")
            if not container_id:
                error_msg = "コンテナIDが取得できませんでした"
                log_message("Threads投稿", "なし", "失敗", error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "platform": "threads"
                }
        except Exception as e:
            error_msg = f"コンテナIDの解析に失敗: {str(e)}"
            log_message("Threads投稿", "なし", "失敗", error_msg)
            return {
                "success": False,
                "error": error_msg,
                "platform": "threads"
            }
        
        log_message("Threads投稿", "システム", "進行中", f"コンテナID取得成功: {container_id}")
        
        # ステップ2: 投稿の公開
        log_message("Threads投稿", "システム", "進行中", "ステップ2: 投稿公開中...")
        publish_url = "https://graph.threads.net/v1.0/me/threads_publish"
        publish_params = {
            "access_token": access_token,
            "creation_id": container_id
        }
        
        # リクエスト送信
        publish_response = requests.post(publish_url, data=publish_params)
        
        if publish_response.status_code != 200:
            error_msg = f"公開エラー: ステータスコード {publish_response.status_code}, レスポンス: {publish_response.text}"
            log_message("Threads投稿", "なし", "失敗", error_msg)
            return {
                "success": False,
                "error": error_msg,
                "platform": "threads"
            }
        
        # 公開成功
        try:
            publish_data = publish_response.json()
            thread_id = publish_data.get("id", "未取得")
            log_message("Threads投稿", thread_id, "成功", f"投稿ID: {thread_id}")
            return {
                "success": True,
                "id": thread_id,
                "platform": "threads"
            }
        except Exception as e:
            error_msg = f"公開レスポンスの解析に失敗: {str(e)}"
            log_message("Threads投稿", "なし", "失敗", error_msg)
            return {
                "success": False,
                "error": error_msg,
                "platform": "threads"
            }
        
    except Exception as e:
        log_message("Threads投稿", "なし", "失敗", f"エラー: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "platform": "threads"
        }

# 投稿結果を記録
def record_posting_result(product, post_result):
    try:
        # 記録用のファイルがなければ作成
        if not os.path.exists("threads_posting_log.csv"):
            with open("threads_posting_log.csv", mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow([
                    "timestamp", "jan_code", "product_name", "current_price", 
                    "price_change_rate", "success", "thread_id", "error"
                ])
        
        # 記録を追加
        with open("threads_posting_log.csv", mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                product["jan_code"],
                product["product_name"],
                product["current_price"],
                product["price_change_rate"],
                post_result["success"],
                post_result.get("id", ""),
                post_result.get("error", "")
            ])
            
    except Exception as e:
        log_message("投稿記録", product["jan_code"], "失敗", f"エラー: {str(e)}")

# アクセストークンの検証用関数
def validate_threads_token():
    """トークンが正常に取得できるかを検証する関数"""
    try:
        token = get_threads_access_token()
        if token:
            log_message("Threads認証", "システム", "検証", "アクセストークンの取得に成功しました")
            return True
        return False
    except Exception as e:
        log_message("Threads認証", "システム", "検証失敗", f"エラー: {str(e)}")
        return False

# 商品情報をスレッズに投稿するメイン関数
def post_products_to_threads():
    try:
        # まずトークンの検証を行う
        if not validate_threads_token():
            log_message("Threads投稿", "システム", "中止", "アクセストークンの検証に失敗したため処理を中止します")
            return []
            
        # 通知対象の商品がなければ終了
        if not os.path.exists("notifiable_products.json"):
            log_message("Threads投稿", "システム", "情報", "通知対象の商品がありません")
            return []
            
        # 通知対象の商品を読み込む
        with open("notifiable_products.json", "r", encoding="utf-8") as f:
            notifiable_products = json.load(f)
            
        if not notifiable_products:
            log_message("Threads投稿", "システム", "情報", "通知対象の商品がありません")
            return []
            
        log_message("Threads投稿", "システム", "開始", f"{len(notifiable_products)}件の商品を投稿します")
        
        results = []
        
        # 投稿数の上限（API制限対策）
        max_posts = min(20, len(notifiable_products))
        
        # 各商品を処理
        for i in range(max_posts):
            product = notifiable_products[i]
            
            try:
                # 投稿メッセージを作成
                threads_message = create_threads_message(product)
                
                # スレッズに投稿
                log_message("Threads投稿", product["jan_code"], "進行中", "Threadsに投稿します")
                post_result = post_to_threads(threads_message)
                
                # 投稿結果を記録
                record_posting_result(product, post_result)
                
                results.append({
                    "product": product,
                    "result": post_result
                })
                
                log_message("Threads投稿", product["jan_code"], "完了", 
                           f"結果: {'成功' if post_result['success'] else '失敗'}")
                
                # 連続投稿の場合はAPIレート制限を考慮して少し待機
                if i < max_posts - 1:
                    import time
                    time.sleep(2)
                    
            except Exception as e:
                log_message("Threads投稿", product["jan_code"], "失敗", f"エラー: {str(e)}")
        
        log_message("Threads投稿", "システム", "完了", f"{len(results)}件の商品の投稿が完了しました")
        
        return results
        
    except Exception as e:
        log_message("Threads投稿", "システム", "失敗", f"エラー: {str(e)}")
        return []

# テスト用の関数
def test_threads_connection():
    """スレッズAPIの接続テスト用関数"""
    try:
        log_message("接続テスト", "システム", "開始", "Threads API接続テストを開始します")
        
        # 認証情報の確認
        app_id = os.environ.get("THREADS_APP_ID")
        app_secret = os.environ.get("THREADS_APP_SECRET")
        instagram_account_id = os.environ.get("THREADS_INSTAGRAM_ACCOUNT_ID")
        
        log_message("接続テスト", "システム", "情報", f"App ID設定: {'あり' if app_id else 'なし'}")
        log_message("接続テスト", "システム", "情報", f"App Secret設定: {'あり' if app_secret else 'なし'}")
        log_message("接続テスト", "システム", "情報", f"Instagram ID設定: {'あり' if instagram_account_id else 'なし'}")
        
        # アクセストークン取得テスト
        token = get_threads_access_token()
        log_message("接続テスト", "システム", "情報", f"アクセストークン取得: {'成功' if token else '失敗'}")
        
        # 簡易的なテスト投稿
        if token:
            test_message = "これはThreads APIのテスト投稿です。"
            log_message("接続テスト", "システム", "進行中", "テスト投稿を試みます")
            
            # テスト投稿を実行（実際に投稿したくない場合はコメントアウト）
            post_result = post_to_threads(test_message)
            log_message("接続テスト", "システム", "結果", f"テスト投稿: {'成功' if post_result['success'] else '失敗'}")
        
        log_message("接続テスト", "システム", "完了", "接続テストが完了しました")
        
    except Exception as e:
        log_message("接続テスト", "システム", "失敗", f"エラー: {str(e)}")

# メイン実行関数
if __name__ == "__main__":
    try:
        import sys
        
        # コマンドライン引数の確認
        if len(sys.argv) > 1 and sys.argv[1] == "--test":
            # テストモードの場合
            test_threads_connection()
        else:
            # 通常実行
            log_message("メイン処理", "システム", "開始", "Threads投稿処理を開始します")
            
            # 商品情報をスレッズに投稿
            results = post_products_to_threads()
            
            # 実行結果をログに記録
            log_message("メイン処理", "システム", "完了", f"{len(results)}件の商品をThreadsに投稿しました")
        
    except Exception as e:
        log_message("メイン処理", "システム", "失敗", f"エラー: {str(e)}")
# 投稿完了後にnotifiable_products.jsonをクリアする
with open("notifiable_products.json", "w", encoding="utf-8") as f:
    json.dump([], f)
log_message("メイン処理", "システム", "情報", "通知対象商品リストをクリアしました")
