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
            return long_lived_token
            
        # 認証情報が設定されているか確認
        if not all([app_id, app_secret]):
            raise ValueError("Threads API認証情報が不足しています")
        
        # アクセストークンリクエストURL
        token_url = f"https://graph.facebook.com/v18.0/oauth/access_token"
        
        # リクエストパラメータ
        params = {
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "client_credentials"
        }
        
        # POSTリクエストを送信
        response = requests.get(token_url, params=params)
        
        # レスポンスを確認
        if response.status_code == 200:
            response_data = response.json()
            access_token = response_data.get("access_token")
            log_message("Threads認証", "システム", "成功", "アクセストークンを取得しました")
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
        instagram_account_id = os.environ.get("THREADS_INSTAGRAM_ACCOUNT_ID")
        
        # 認証情報が設定されているか確認
        if not all([access_token, instagram_account_id]):
            raise ValueError("Threads API認証情報が不足しています")
            
        # スレッズ投稿エンドポイント
        # Instagram Graph APIを使用してスレッズに投稿
        api_url = f"https://graph.facebook.com/v18.0/{instagram_account_id}/threads"
        
        # リクエストパラメータ
        params = {
            "message": message,
            "access_token": access_token
        }
        
        # POSTリクエストを送信
        response = requests.post(api_url, data=params, timeout=30)
        
        # レスポンスを確認
        if response.status_code == 200:
            response_data = response.json()
            thread_id = response_data.get("id", "未取得")
            log_message("Threads投稿", thread_id, "成功", f"投稿ID: {thread_id}")
            
            return {
                "success": True,
                "id": thread_id,
                "platform": "threads"
            }
        else:
            error_msg = f"APIエラー: ステータスコード {response.status_code}, レスポンス: {response.text}"
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

# 商品情報をスレッズに投稿するメイン関数
def post_products_to_threads():
    try:
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
        max_posts = min(5, len(notifiable_products))
        
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

# メイン実行関数
if __name__ == "__main__":
    try:
        # 実行開始ログ
        log_message("メイン処理", "システム", "開始", "Threads投稿処理を開始します")
        
        # 商品情報をスレッズに投稿
        results = post_products_to_threads()
        
        # 実行結果をログに記録
        log_message("メイン処理", "システム", "完了", f"{len(results)}件の商品をThreadsに投稿しました")
        
    except Exception as e:
        log_message("メイン処理", "システム", "失敗", f"エラー: {str(e)}")
