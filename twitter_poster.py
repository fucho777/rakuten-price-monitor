import os
import json
import csv
from datetime import datetime
import tweepy

# ログ出力関数
def log_message(message_type, target, status, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{message_type}] [{target}] [{status}] {message}")

# テキストを指定した長さに切り詰める
def truncate_text(text, max_length):
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

# Twitter投稿用のメッセージを作成
def create_twitter_message(product):
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
    
    # Twitter用（最大280文字に収まるよう調整）
    twitter_msg = (
        f"【価格変動】\n"
        f"商品名：{truncate_text(product['product_name'], 50)}\n"
        f"価格：{product['current_price']:,}円（{change_rate_str}%）\n"
        f"在庫：{availability_status}\n"
        f"販売：{product['shop_name']}\n"
        f"{product['affiliate_url']}"
    )
    
    return twitter_msg

# Twitterに投稿する関数
def post_to_twitter(message):
    try:
        # Twitter API認証情報
        api_key = os.environ.get("TWITTER_API_KEY")
        api_secret = os.environ.get("TWITTER_API_SECRET")
        access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
        access_token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")
        
        # 認証情報が設定されているか確認
        if not all([api_key, api_secret, access_token, access_token_secret]):
            raise ValueError("Twitter API認証情報が不足しています")
            
        # Twitter APIクライアントを初期化
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_token_secret
        )
        
        # ツイート投稿
        response = client.create_tweet(text=message)
        
        tweet_id = response.data["id"]
        log_message("Twitter投稿", tweet_id, "成功", f"投稿ID: {tweet_id}")
        
        return {
            "success": True,
            "id": tweet_id,
            "platform": "twitter"
        }
        
    except Exception as e:
        log_message("Twitter投稿", "なし", "失敗", f"エラー: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "platform": "twitter"
        }

# 投稿結果を記録
def record_posting_result(product, post_result):
    try:
        # 記録用のファイルがなければ作成
        if not os.path.exists("twitter_posting_log.csv"):
            with open("twitter_posting_log.csv", mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow([
                    "timestamp", "jan_code", "product_name", "current_price", 
                    "price_change_rate", "success", "tweet_id", "error"
                ])
        
        # 記録を追加
        with open("twitter_posting_log.csv", mode="a", newline="", encoding="utf-8") as file:
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

# 商品情報をTwitterに投稿するメイン関数
def post_products_to_twitter():
    try:
        # 通知対象の商品がなければ終了
        if not os.path.exists("notifiable_products.json"):
            log_message("Twitter投稿", "システム", "情報", "通知対象の商品がありません")
            return []
            
        # 通知対象の商品を読み込む
        with open("notifiable_products.json", "r", encoding="utf-8") as f:
            notifiable_products = json.load(f)
            
        if not notifiable_products:
            log_message("Twitter投稿", "システム", "情報", "通知対象の商品がありません")
            return []
            
        log_message("Twitter投稿", "システム", "開始", f"{len(notifiable_products)}件の商品を投稿します")
        
        results = []
        
        # 投稿数の上限（API制限対策）
        max_posts = min(5, len(notifiable_products))
        
        # 各商品を処理
        for i in range(max_posts):
            product = notifiable_products[i]
            
            try:
                # 投稿メッセージを作成
                twitter_message = create_twitter_message(product)
                
                # Twitterに投稿
                log_message("Twitter投稿", product["jan_code"], "進行中", "Twitterに投稿します")
                post_result = post_to_twitter(twitter_message)
                
                # 投稿結果を記録
                record_posting_result(product, post_result)
                
                results.append({
                    "product": product,
                    "result": post_result
                })
                
                log_message("Twitter投稿", product["jan_code"], "完了", 
                           f"結果: {'成功' if post_result['success'] else '失敗'}")
                
                # 連続投稿の場合はAPIレート制限を考慮して少し待機
                if i < max_posts - 1:
                    import time
                    time.sleep(2)
                    
            except Exception as e:
                log_message("Twitter投稿", product["jan_code"], "失敗", f"エラー: {str(e)}")
        
        log_message("Twitter投稿", "システム", "完了", f"{len(results)}件の商品の投稿が完了しました")
        
        return results
        
    except Exception as e:
        log_message("Twitter投稿", "システム", "失敗", f"エラー: {str(e)}")
        return []

# メイン実行関数
if __name__ == "__main__":
    try:
        # 実行開始ログ
        log_message("メイン処理", "システム", "開始", "Twitter投稿処理を開始します")
        
        # 商品情報をTwitterに投稿
        results = post_products_to_twitter()
        
        # 実行結果をログに記録
        log_message("メイン処理", "システム", "完了", f"{len(results)}件の商品をTwitterに投稿しました")
        
    except Exception as e:
        log_message("メイン処理", "システム", "失敗", f"エラー: {str(e)}")
