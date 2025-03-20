import os
import json
import time
from datetime import datetime
import tweepy
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ログ出力関数
def log_message(message_type, target, status, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{message_type}] [{target}] [{status}] {message}")

# テキストを指定した長さに切り詰める
def truncate_text(text, max_length):
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

# 投稿メッセージを作成
def create_post_messages(product):
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
    
    # Twitter用（短めに調整）
    twitter_msg = (
        f"【価格変動】\n"
        f"商品名：{truncate_text(product['product_name'], 50)}\n"
        f"価格：{product['current_price']:,}円（{change_rate_str}%）\n"
        f"在庫：{availability_status}\n"
        f"販売：{product['shop_name']}\n"
        f"{product['affiliate_url']}"
    )
    
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
    
    return {
        "twitter": twitter_msg,
        "threads": threads_msg
    }

# Twitterに投稿
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
        
        return tweet_id
        
    except Exception as e:
        log_message("Twitter投稿", "なし", "失敗", f"エラー: {str(e)}")
        raise

# スレッズに投稿（セレニウム使用）
def post_to_threads(message, username, password):
    try:
        log_message("スレッズ投稿", "準備", "開始", "ブラウザを初期化します")
        
        # 認証情報が設定されているか確認
        if not username or not password:
            raise ValueError("スレッズ認証情報が不足しています")
            
        # Chromeのオプション設定
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # WebDriverを初期化
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        try:
            # Instagram（スレッズのログイン用）にアクセス
            log_message("スレッズ投稿", "ログイン", "開始", "Instagramログインページにアクセスします")
            driver.get("https://www.instagram.com/accounts/login/")
            
            # ログイン画面が表示されるまで待機
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            
            # クッキー同意ボタンがあれば処理
            try:
                cookie_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), '同意')]"))
                )
                cookie_button.click()
                time.sleep(2)
            except:
                log_message("スレッズ投稿", "ログイン", "情報", "クッキー同意ボタンはありませんでした")
            
            # ユーザー名とパスワードを入力
            log_message("スレッズ投稿", "ログイン", "進行中", "認証情報を入力します")
            driver.find_element(By.NAME, "username").send_keys(username)
            driver.find_element(By.NAME, "password").send_keys(password)
            
            # ログインボタンをクリック
            login_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))
            )
            login_button.click()
            
            # ログイン完了を待機
            time.sleep(5)
            
            # スレッズにアクセス
            log_message("スレッズ投稿", "ナビゲーション", "進行中", "Threadsサイトにアクセスします")
            driver.get("https://www.threads.net
