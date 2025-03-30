import os
import csv
import json
import time
import functools
import pandas as pd
import requests
import subprocess
from datetime import datetime, timedelta

# ======= 共通ユーティリティ関数 =======

# ログ出力関数
def log_message(message_type, target, status, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{message_type}] [{target}] [{status}] {message}")

# 指数バックオフ付きリトライ装飾子
def retry_with_backoff(max_tries=3, backoff_factor=2):
    """指数バックオフ付きリトライ装飾子"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retry_count = 0
            while retry_count < max_tries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retry_count += 1
                    if retry_count == max_tries:
                        # 最大リトライ回数に達したら例外を再発生
                        raise
                    
                    # 待機時間を計算 (1, 2, 4, 8, ... 秒)
                    wait_time = (backoff_factor ** (retry_count - 1))
                    log_message("リトライ", func.__name__, "待機", 
                               f"エラー: {str(e)}, {wait_time}秒後に再試行します ({retry_count}/{max_tries})")
                    time.sleep(wait_time)
            return None  # ここには到達しないはずだが、念のため
        return wrapper
    return decorator

# 設定値
CONFIG = {
    "price_change_threshold": float(os.environ.get("PRICE_CHANGE_THRESHOLD", "5")),
    "min_price_change_amount": 500,  # 最低500円の変動
    "min_notification_interval_hours": 72,  # 3日間
    "min_price_change_percentage": 1.0,  # 最低1%の変動率
    "api_cache_lifetime": 3600,  # APIキャッシュ有効期間（秒）
    "max_posts_per_run": 5,  # 1回の実行で投稿する最大商品数
}

# ======= 通知履歴管理 =======

# 通知履歴の取得
def get_notification_history():
    """通知履歴ファイルから履歴を取得"""
    if os.path.exists("notification_history.json"):
        try:
            with open("notification_history.json", "r", encoding="utf-8") as f:
                history = json.load(f)
            
            log_message("通知履歴", "システム", "読込", f"{len(history)}件の通知履歴を読み込みました")
            return history
        except Exception as e:
            log_message("通知履歴", "システム", "読込エラー", str(e))
            return {}
    else:
        log_message("通知履歴", "システム", "初期化", "通知履歴ファイルが存在しないため新規作成します")
        return {}

# 通知履歴の保存
def save_notification_history(history):
    """通知履歴をファイルに保存"""
    try:
        with open("notification_history.json", "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        
        log_message("通知履歴", "システム", "保存", f"{len(history)}件の履歴を保存しました")
        return True
    except Exception as e:
        log_message("通知履歴", "システム", "保存エラー", str(e))
        return False

# 通知履歴の更新
def update_notification_history(notifiable_products):
    """通知対象商品の履歴を更新"""
    try:
        history = get_notification_history()
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 新しい通知を履歴に追加
        for product in notifiable_products:
            jan_code = str(product["jan_code"])
            
            if jan_code in history:
                # 既存エントリの更新
                history[jan_code].update({
                    "product_name": product["product_name"],
                    "price": product["current_price"],
                    "last_notified_time": current_time_str,
                    "notification_count": history[jan_code].get("notification_count", 0) + 1,
                    "previous_prices": history[jan_code].get("previous_prices", []) + [
                        {"price": product["current_price"], "time": current_time_str}
                    ][-5:]  # 直近5回分の履歴を保持
                })
            else:
                # 新規エントリの追加
                history[jan_code] = {
                    "product_name": product["product_name"],
                    "price": product["current_price"],
                    "last_notified_time": current_time_str,
                    "notification_count": 1,
                    "previous_prices": [
                        {"price": product["current_price"], "time": current_time_str}
                    ]
                }
        
        # 履歴を保存
        save_notification_history(history)
        log_message("通知履歴", "システム", "更新", f"{len(notifiable_products)}件の通知履歴を更新しました")
    except Exception as e:
        log_message("通知履歴", "システム", "更新失敗", str(e))

# ======= 商品リスト管理 =======

# 商品リストの読み込み
def load_product_list():
    """product_list.csvを読み込み、DataFrameとして返す"""
    try:
        if os.path.exists("product_list.csv"):
            try:
                # jan_codeを文字列として読み込む
                product_df = pd.read_csv("product_list.csv", dtype={"jan_code": str})
                log_message("商品リスト", "システム", "読込", f"{len(product_df)}件の商品情報を読み込みました")
                
                # カラム型を適切に設定
                if "last_price" in product_df.columns:
                    # 数値データの型変換（エラーは無視）
                    product_df["last_price"] = pd.to_numeric(product_df["last_price"], errors="coerce")
                    product_df["last_notified_price"] = pd.to_numeric(product_df["last_notified_price"], errors="coerce")
                
                # 真偽値の型変換
                if "monitor_flag" in product_df.columns:
                    product_df["monitor_flag"] = product_df["monitor_flag"].astype(bool)
                    
                if "notified_flag" in product_df.columns:
                    product_df["notified_flag"] = product_df["notified_flag"].astype(bool)
                
                # 必要な列が存在するか確認
                required_columns = [
                    "jan_code", "product_name", "last_price", "last_availability", 
                    "monitor_flag", "notified_flag", "last_notified_price", "last_notified_time"
                ]
                
                # 不足している列を追加
                for col in required_columns:
                    if col not in product_df.columns:
                        if col in ["monitor_flag", "notified_flag"]:
                            product_df[col] = False
                        elif col in ["last_price", "last_notified_price"]:
                            product_df[col] = 0
                        else:
                            product_df[col] = None
                        log_message("商品リスト", "システム", "列追加", f"{col}列を追加しました")
                
                return product_df
            except Exception as e:
                log_message("商品リスト", "システム", "読込エラー", f"CSV解析エラー: {str(e)}")
                # 読み込みに失敗した場合は空のDataFrameを作成し返す
        
        # ファイルが存在しない場合、またはエラーが発生した場合は新規作成
        log_message("商品リスト", "システム", "警告", "product_list.csvが見つからないか読み込めません。新規作成します。")
        # 空のDataFrameを返す
        return pd.DataFrame(columns=[
            "jan_code", "product_name", "last_price", "last_availability", 
            "monitor_flag", "notified_flag", "last_notified_price", "last_notified_time"
        ])
    except Exception as e:
        log_message("商品リスト", "システム", "読込エラー", str(e))
        # エラーが発生した場合も空のDataFrameを返す
        return pd.DataFrame(columns=[
            "jan_code", "product_name", "last_price", "last_availability", 
            "monitor_flag", "notified_flag", "last_notified_price", "last_notified_time"
        ])

# 商品リストの保存
def save_product_list(product_df):
    """商品リストをCSVファイルに保存"""
    try:
        # 保存前のチェック
        log_message("商品リスト", "システム", "保存前", f"行数: {len(product_df)}, 列: {product_df.columns.tolist()}")
        
        # null値を適切に処理
        product_df["product_name"] = product_df["product_name"].fillna("").astype(str)
        product_df["last_availability"] = product_df["last_availability"].fillna("unknown").astype(str)
        
        # 現在の時刻を取得してタイムスタンプ列を追加
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        product_df["last_updated"] = current_time
        
        # CSVファイルに保存（index=Falseは必須）
        product_df.to_csv("product_list.csv", index=False, encoding="utf-8")
        
        # 保存後の確認
        if os.path.exists("product_list.csv"):
            file_size = os.path.getsize("product_list.csv")
            log_message("商品リスト", "システム", "保存成功", f"{len(product_df)}件の商品情報を保存しました (サイズ: {file_size} バイト)")
            return True
        else:
            log_message("商品リスト", "システム", "保存エラー", "ファイルの確認ができません")
            return False
    except Exception as e:
        log_message("商品リスト", "システム", "保存エラー", f"例外発生: {str(e)}")
        return False

# 商品情報の更新
def update_product_info(product_df, jan_code, product_info, price_change_rate=0):
    """指定されたJANコードの商品情報を更新"""
    try:
        # JANコードを文字列として扱う
        jan_code_str = str(jan_code)
        
        # 文字列に変換したJANコードで比較
        mask = product_df["jan_code"].astype(str) == jan_code_str
        
        # マッチする行が存在するか確認
        if not mask.any():
            log_message("商品情報更新", jan_code, "スキップ", "指定されたJANコードが商品リストに存在しません")
            return product_df
        
        # 更新前の値を記録
        old_product_name = product_df.loc[mask, "product_name"].iloc[0] if not pd.isna(product_df.loc[mask, "product_name"].iloc[0]) else "未取得"
        old_price = product_df.loc[mask, "last_price"].iloc[0] if not pd.isna(product_df.loc[mask, "last_price"].iloc[0]) else 0
        old_availability = product_df.loc[mask, "last_availability"].iloc[0] if not pd.isna(product_df.loc[mask, "last_availability"].iloc[0]) else "不明"
        
        # 商品情報を更新
        product_df.loc[mask, "product_name"] = product_info["item_name"]
        product_df.loc[mask, "last_price"] = product_info["item_price"]
        product_df.loc[mask, "last_availability"] = product_info["availability"]
        
        # 更新後の値を確認
        new_product_name = product_df.loc[mask, "product_name"].iloc[0]
        new_price = product_df.loc[mask, "last_price"].iloc[0]
        new_availability = product_df.loc[mask, "last_availability"].iloc[0]
        
        log_message("商品情報更新", jan_code, "成功", 
                   f"商品名: {old_product_name} → {new_product_name}, "
                   f"価格: {old_price}円 → {new_price}円, "
                   f"在庫: {old_availability} → {new_availability}")
        
        return product_df
    except Exception as e:
        log_message("商品情報更新", jan_code, "失敗", str(e))
        return product_df

# ======= 楽天API 関連 =======

# APIキャッシュ
_api_cache = {}  # シンプルなインメモリキャッシュ

# 楽天APIの設定を取得
def get_rakuten_api_settings():
    """楽天APIの認証情報を環境変数から取得"""
    return {
        "app_id": os.environ.get("RAKUTEN_APP_ID"),
        "affiliate_id": os.environ.get("RAKUTEN_AFFILIATE_ID", "")
    }

# JANコードで商品を検索（キャッシュ & リトライ機能付き）
@retry_with_backoff(max_tries=3)
def search_product_by_jan_code(jan_code, use_cache=True):
    """楽天APIで商品を検索する関数（キャッシュ機能付き）"""
    global _api_cache
    
    cache_key = f"jan_{jan_code}"
    current_time = time.time()
    
    # キャッシュチェック
    if use_cache and cache_key in _api_cache:
        cache_entry = _api_cache[cache_key]
        if current_time - cache_entry["timestamp"] < CONFIG["api_cache_lifetime"]:
            log_message("楽天API検索", f"JANコード: {jan_code}", "キャッシュ利用", "キャッシュからデータを返します")
            return cache_entry["data"]
    
    try:
        settings = get_rakuten_api_settings()
        app_id = settings["app_id"]
        affiliate_id = settings["affiliate_id"]
        
        if not app_id:
            raise ValueError("RAKUTEN_APP_ID環境変数が設定されていません")
            
        if not jan_code:
            raise ValueError("JANコードが指定されていません")
            
        # JANコードの形式確認（数字のみ、8桁または13桁）
        jan_code = str(jan_code).replace("-", "").strip()
        if not (len(jan_code) == 8 or len(jan_code) == 13):
            raise ValueError(f"無効なJANコード形式です: {jan_code}")
            
        # 楽天商品検索APIのURL構築
        base_url = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20170706"
        params = {
            "applicationId": app_id,
            "affiliateId": affiliate_id,
            "keyword": jan_code,  # JANコードで検索
            "hits": 30,
            "sort": "+itemPrice",
            "availability": 1,
            "format": "json"
        }
        
        # URLパラメータ構築
        import urllib.parse
        query_string = "&".join([f"{key}={urllib.parse.quote(str(value))}" for key, value in params.items()])
        request_url = f"{base_url}?{query_string}"
        
        # APIリクエスト実行
        response = requests.get(request_url, timeout=15)
        
        # レスポンスステータスの確認
        if response.status_code != 200:
            raise ValueError(f"API応答エラー：ステータスコード {response.status_code}")
            
        # レスポンスをJSONに変換
        result = response.json()
        
        # エラーレスポンスのチェック
        if "error" in result:
            error_msg = f"楽天API エラー: {result['error']}: {result.get('error_description', '')}"
            raise ValueError(error_msg)
        
        # 実行ログに記録
        log_message("楽天API検索", f"JANコード: {jan_code}", "成功", 
                    f"検索結果: {result.get('count', 0)}件")
        
        # 成功した結果をキャッシュに保存
        if use_cache and result and "Items" in result:
            _api_cache[cache_key] = {
                "data": result,
                "timestamp": current_time
            }
            
            # キャッシュサイズ管理
            if len(_api_cache) > 100:  # 100件を超えたら古いものを削除
                oldest_key = min(_api_cache.items(), key=lambda x: x[1]["timestamp"])[0]
                del _api_cache[oldest_key]
        
        return result
        
    except Exception as e:
        # エラーが発生した場合は実行ログに記録
        log_message("楽天API検索", f"JANコード: {jan_code}", "失敗", str(e))
        raise  # リトライデコレータがキャッチする
        
# 新品商品のみをフィルタリングする
def filter_new_items(items):
    """商品リストから新品商品のみをフィルタリング"""
    # 明確に「中古」を表すキーワード
    used_keywords = ["中古", "used", "ユーズド", "中古品", "USED"]
    
    # フィルタリング処理
    new_items = []
    for item in items:
        if not item.get("itemName"):
            continue
            
        item_name = item["itemName"].lower()
        if not any(keyword.lower() in item_name for keyword in used_keywords):
            new_items.append(item)
    
    log_message("新品フィルタ", "システム", "情報", 
                f"全{len(items)}件中、{len(new_items)}件の新品商品を抽出しました")
    
    return new_items

# 検索結果から最適な商品を選択する
def select_best_product(search_result, jan_code):
    """検索結果から最適な（最安値新品）商品を選択"""
    try:
        # 検索結果がない場合はNoneを返す
        if not search_result or "Items" not in search_result or not search_result["Items"]:
            log_message("商品選択", "なし", "失敗", "検索結果が0件です")
            return None
            
        # 商品リストを取得
        items = [item["Item"] for item in search_result["Items"]]
        
        # 新品商品のみをフィルタリング
        new_items = filter_new_items(items)
        
        # 新品がない場合はNoneを返す
        if not new_items:
            log_message("商品選択", "なし", "注意", "新品商品が見つからないため、スキップします")
            return None
            
        # 価格の安い順にソートして最安値商品を選択
        valid_items = [item for item in new_items 
                      if "itemPrice" in item and item["itemPrice"] and int(item["itemPrice"]) > 0]
        
        if not valid_items:
            log_message("商品選択", "なし", "警告", "有効な価格の新品商品がありません")
            return None
            
        # JANコードが商品名や説明文に含まれる商品を優先して選択
        jan_matched_items = []
        for item in valid_items:
            item_name = item.get("itemName", "").lower()
            item_caption = item.get("itemCaption", "").lower()
            if str(jan_code).lower() in item_name or str(jan_code).lower() in item_caption:
                jan_matched_items.append(item)
        
        # JANコードに一致する商品があればその中から最安値、なければ元の最安値商品を選択
        items_to_sort = jan_matched_items if jan_matched_items else valid_items
            
        # 価格の安い順にソート
        items_to_sort.sort(key=lambda x: int(x["itemPrice"]))
        
        # 最安値の商品を選択
        selected_item = items_to_sort[0]
        
        # 選択された商品の情報をログに記録
        if selected_item:
            log_message("商品選択", selected_item.get("itemCode", "なし"), "成功", 
                      f"新品商品を選択: {selected_item.get('itemName', '名称不明')}, "
                      f"価格: {selected_item.get('itemPrice', '0')}円, "
                      f"販売店: {selected_item.get('shopName', '不明')}")
        else:
            log_message("商品選択", "なし", "注意", "条件に合う商品が見つかりませんでした")
            
        return selected_item
        
    except Exception as e:
        log_message("商品選択", "なし", "失敗", str(e))
        return None

# 空の商品情報を作成
def create_empty_product_info(jan_code):
    """空の商品情報を作成"""
    return {
        "jan_code": str(jan_code),
        "item_name": f"取得できませんでした（{jan_code}）",
        "item_price": 0,
        "shop_name": "不明",
        "availability": "不明",
        "item_url": "",
        "affiliate_url": "",
        "image_url": "",
        "is_new_item": False
    }

# 商品情報を整形
def create_product_info(jan_code, selected_product):
    """商品情報を整形"""
    return {
        "jan_code": str(jan_code),
        "item_name": selected_product.get("itemName", "商品名なし"),
        "item_price": int(selected_product.get("itemPrice", 0)),
        "shop_name": selected_product.get("shopName", "販売店不明"),
        "availability": "在庫あり" if selected_product.get("availability") == 1 else "在庫なし",
        "item_url": selected_product.get("itemUrl", ""),
        "affiliate_url": selected_product.get("affiliateUrl", "") or selected_product.get("itemUrl", ""),
        "image_url": (selected_product.get("mediumImageUrls", [{}])[0].get("imageUrl", "") 
                    if selected_product.get("mediumImageUrls") else ""),
        "is_new_item": True
    }

# JANコードから商品情報を取得する
def get_product_info_by_jan_code(jan_code):
    """JANコードをもとに商品情報を取得"""
    try:
        # JANコードで商品を検索
        search_result = search_product_by_jan_code(jan_code)
        
        # 基本的なエラーチェック
        if not search_result or "Items" not in search_result or len(search_result["Items"]) == 0:
            return create_empty_product_info(jan_code)
            
        # 検索結果から新品商品を選択
        selected_product = select_best_product(search_result, jan_code)
        
        if not selected_product:
            # 新品商品が見つからない場合は「新品なし」状態を返す
            log_message("商品選択", jan_code, "情報", "新品商品がないため、在庫なし状態を返します")
            return {
                "jan_code": str(jan_code),
                "item_name": f"{jan_code}（新品なし）",
                "item_price": 0,
                "shop_name": "",
                "availability": "在庫なし",
                "item_url": "",
                "affiliate_url": "",
                "image_url": "",
                "is_new_item": False
            }
            
        # 商品情報を整形して返す
        product_info = create_product_info(jan_code, selected_product)
        
        log_message("商品情報取得", jan_code, "成功", 
                    f"新品商品: {product_info['item_name']}, "
                    f"価格: {product_info['item_price']}円, "
                    f"在庫: {product_info['availability']}")
                    
        return product_info
        
    except Exception as e:
        log_message("商品情報取得", jan_code, "失敗", f"エラー: {str(e)}")
        return create_empty_product_info(jan_code)

# ======= 通知フィルタリング =======
            
# 通知すべき商品をフィルタリング
def filter_notifiable_products(changed_products, product_df, threshold=5):
    """価格変動が閾値を超えた商品の中から通知すべきものをフィルタリング"""
    notifiable = []
    notification_history = get_notification_history()
    current_time = datetime.now()
    
    for product in changed_products:
        jan_code = str(product["jan_code"])
        
        # ステップ1: 最小変動チェック
        if abs(product["price_change_rate"]) < CONFIG["min_price_change_percentage"]:
            log_message("通知フィルタ", jan_code, "スキップ", 
                      f"変動率が小さすぎます: {product['price_change_rate']:.2f}%")
            continue
            
        # ステップ2: 絶対額チェック
        price_change_amount = abs(product["current_price"] - product["previous_price"])
        if price_change_amount < CONFIG["min_price_change_amount"]:
            log_message("通知フィルタ", jan_code, "スキップ", 
                      f"価格変動額が小さすぎます: {price_change_amount}円")
            continue
        
        # ステップ3: 在庫チェック
        has_stock = product["current_availability"] == "在庫あり"
        if not has_stock:
            log_message("通知フィルタ", jan_code, "スキップ", "在庫がないため通知しません")
            continue
        
        # ステップ4: 通知履歴チェック
        if jan_code in notification_history:
            try:
                history = notification_history[jan_code]
                
                # 前回通知からの時間経過チェック
                last_time = datetime.strptime(history["last_notified_time"], "%Y-%m-%d %H:%M:%S")
                hours_since_last = (current_time - last_time).total_seconds() / 3600
                
                if hours_since_last < CONFIG["min_notification_interval_hours"]:
                    log_message("通知フィルタ", jan_code, "スキップ", 
                              f"前回通知から{hours_since_last:.1f}時間しか経過していません（最低{CONFIG['min_notification_interval_hours']}時間必要）")
                    continue
                    
                # 前回通知時の価格との比較
                last_price = history["price"]
                price_diff_percent = abs((product["current_price"] - last_price) / last_price * 100) if last_price > 0 else 100
                
                if price_diff_percent < threshold:
                    log_message("通知フィルタ", jan_code, "スキップ", 
                              f"前回通知時価格({last_price}円)から変動が小さいため通知しません({price_diff_percent:.2f}%)")
                    continue
            except Exception as e:
                log_message("通知フィルタ", jan_code, "警告", f"履歴解析エラー: {str(e)}")
        
        # 商品リストから該当商品の行を取得（データフレームへの登録チェック用）
        product_row = product_df[product_df["jan_code"].astype(str) == jan_code]
        
        if product_row.empty:
            log_message("通知フィルタ", jan_code, "警告", "商品リストに該当商品が見つかりません")
            continue
            
        # 価格下落の判定（変動率が負の値かつ閾値以上）
        price_reduced = (product["price_change_rate"] < 0 and 
                        abs(product["price_change_rate"]) >= threshold)
        
        # 在庫が復活した場合の判定
        stock_restored = (product["previous_availability"] == "在庫なし" and 
                         product["current_availability"] == "在庫あり")

        # 条件に合致し、かつ在庫があり、大きな価格変動がある場合に通知対象とする
        if (price_reduced or stock_restored) and has_stock:
            notifiable.append(product)
            log_message("通知フィルタ", jan_code, "通知対象", 
                      f"価格: {product['current_price']}円, 変動率: {product['price_change_rate']:.2f}%, 在庫: {product['current_availability']}")
           
    return notifiable

# ======= 投稿処理 =======

# 投稿スクリプトを実行する関数
def run_posting_scripts():
    """通知対象商品をSNSに投稿するスクリプトを実行"""
    try:
        log_message("投稿実行", "システム", "開始", "投稿スクリプトを実行します")
        
        # スレッズに投稿
        if os.path.exists("threads_poster.py"):
            log_message("投稿実行", "Threads", "開始", "スレッズへの投稿を開始します")
            try:
                subprocess.run(["python", "threads_poster.py"], check=True)
                log_message("投稿実行", "Threads", "完了", "スレッズへの投稿が完了しました")
            except subprocess.CalledProcessError as e:
                log_message("投稿実行", "Threads", "失敗", f"エラー: {str(e)}")
        
        # Twitterに投稿 (環境変数のチェック)
        if os.path.exists("twitter_poster.py") and "TWITTER_API_KEY" in os.environ:
            log_message("投稿実行", "Twitter", "開始", "Twitterへの投稿を開始します")
            try:
                subprocess.run(["python", "twitter_poster.py"], check=True)
                log_message("投稿実行", "Twitter", "完了", "Twitterへの投稿が完了しました")
            except subprocess.CalledProcessError as e:
                log_message("投稿実行", "Twitter", "失敗", f"エラー: {str(e)}")
        
        log_message("投稿実行", "システム", "完了", "投稿スクリプトの実行が完了しました")
        
    except Exception as e:
        log_message("投稿実行", "システム", "失敗", f"エラー: {str(e)}")

# ======= メイン処理 =======

# 直近の通知と重複していないか確認
def is_recently_notified(jan_code, current_price, hours=24):
   """直近の指定時間内に同じJANコードで同じ価格の通知があるか確認"""
   try:
       notification_history = get_notification_history()
       if jan_code not in notification_history:
           return False
           
       # 履歴エントリを取得
       history = notification_history[jan_code]
       last_notified_time = datetime.strptime(history["last_notified_time"], "%Y-%m-%d %H:%M:%S")
       last_price = history["price"]
       
       # 時間チェック
       time_diff = (datetime.now() - last_notified_time).total_seconds() / 3600
       if time_diff < hours:
           # 価格チェック
           if abs(current_price - last_price) < 10:  # 10円未満の差は同一価格とみなす
               log_message("重複チェック", jan_code, "検出", 
                         f"{time_diff:.1f}時間前に同価格で通知済み: {last_price}円")
               return True
               
       return False
       
   except Exception as e:
       log_message("重複チェック", jan_code, "エラー", f"エラー詳細: {str(e)}")
       # エラー発生時は安全のため重複とみなさない
       return False

# 重複するJANコードを削除する
def remove_duplicate_jan_codes():
   """product_list.csvから重複するJANコードを削除する"""
   try:
       # 商品リストを読み込む
       product_df = load_product_list()
       
       # 重複前の行数を記録
       original_count = len(product_df)
       
       # 重複を確認
       duplicates = product_df[product_df.duplicated(subset=['jan_code'], keep=False)]
       
       if not duplicates.empty:
           log_message("重複JANコード", "システム", "検出", f"{len(duplicates)}件の重複JANコードが見つかりました")
           
           # 重複を表示（デバッグ用）
           for jan_code, group in duplicates.groupby('jan_code'):
               log_message("重複JANコード", jan_code, "詳細", f"{len(group)}件の重複があります")
           
           # 各グループの最初の行を保持し、残りを削除
           product_df = product_df.drop_duplicates(subset=['jan_code'], keep='first')
           
           # 重複削除後のサイズを記録
           new_count = len(product_df)
           log_message("重複JANコード", "システム", "削除", f"{original_count - new_count}件の重複エントリを削除しました")
           
           # 更新されたDataFrameを保存
           save_product_list(product_df)
           
       else:
           log_message("重複JANコード", "システム", "確認", "重複するJANコードはありません")
           
       return product_df
       
   except Exception as e:
       log_message("重複JANコード", "システム", "エラー", f"重複削除中にエラーが発生しました: {str(e)}")
       # エラーが発生した場合は元のDataFrameを返す
       return load_product_list()

# 監視対象商品の変動を監視するメイン関数
def monitor_products():
   """商品の価格変動を監視し、通知すべき商品を検出する"""
   try:
       # 商品リストを読み込む
       product_df = load_product_list()
       
       if len(product_df) == 0:
           log_message("メイン処理", "システム", "警告", "商品リストが空です")
           return []
       
       # 監視対象の商品のみを抽出
       active_products = product_df[product_df["monitor_flag"] == True]
       
       if len(active_products) == 0:
           log_message("メイン処理", "システム", "警告", "監視対象の商品がありません")
           return []
           
       log_message("メイン処理", "システム", "開始", f"合計{len(active_products)}件の商品を監視します")
       
       threshold = CONFIG["price_change_threshold"]  # 通知する価格変動閾値
       changed_products = []
       products_updated = False  # 商品情報が更新されたかを追跡するフラグ
       
       # APIレート制限対策のため、処理間隔を設定
       api_request_interval = 1  # 秒
       
       # すべての監視対象商品を処理
       for index, row in active_products.iterrows():
           jan_code = str(row["jan_code"]).strip()
           
           try:
               # 処理中であることをログに記録
               product_name = str(row["product_name"]) if not pd.isna(row["product_name"]) else "未取得"
               log_message("価格監視", jan_code, "処理中", f"商品名: {product_name}, 処理を開始します")
               
               # JANコードで最新の商品情報を取得
               product_info = get_product_info_by_jan_code(jan_code)
               
               if not product_info or product_info["availability"] == "不明":
                   log_message("価格監視", jan_code, "失敗", "商品情報が取得できませんでした")
                   continue
                   
               # 前回データとの比較
               current_price = product_info["item_price"]
               previous_price = row["last_price"] if not pd.isna(row["last_price"]) else 0
               current_availability = product_info["availability"]
               previous_availability = row["last_availability"] if not pd.isna(row["last_availability"]) else "不明"
               
               # 初回の場合は変動なしとする
               if previous_price == 0 or previous_availability == "不明":
                   # 商品リストを更新
                   product_df = update_product_info(product_df, jan_code, product_info)
                   products_updated = True  # 更新フラグをセット
                   log_message("価格監視", jan_code, "初回取得", 
                              f"商品名: {product_info['item_name']}, 価格: {current_price}円, 在庫: {current_availability}")
                   continue
               
               # 価格または在庫に変動があるか確認
               price_changed = current_price != previous_price
               availability_changed = current_availability != previous_availability
               
               if price_changed or availability_changed:
                   # 価格変動率を計算
                   price_change_rate = 0
                   if previous_price > 0:
                       price_change_rate = ((current_price - previous_price) / previous_price) * 100
                   
                   # 重複チェック - 直近の通知と同一ならスキップ
                   if is_recently_notified(jan_code, current_price):
                       log_message("価格監視", jan_code, "通知スキップ", 
                                 f"直近で同価格({current_price}円)の通知があるためスキップします")
                       # 商品情報は更新するが、通知はしない
                       product_df = update_product_info(product_df, jan_code, product_info, price_change_rate)
                       products_updated = True  # 更新フラグをセット
                       continue
                   
                   # 商品リストを更新
                   product_df = update_product_info(product_df, jan_code, product_info, price_change_rate)
                   products_updated = True  # 更新フラグをセット
                   
                   # 変動があった商品情報を配列に追加
                   changed_products.append({
                       "jan_code": jan_code,
                       "product_name": product_info["item_name"],
                       "current_price": current_price,
                       "previous_price": previous_price,
                       "price_change_rate": price_change_rate,
                       "current_availability": current_availability,
                       "previous_availability": previous_availability,
                       "shop_name": product_info["shop_name"],
                       "item_url": product_info["item_url"],
                       "affiliate_url": product_info["affiliate_url"],
                       "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                   })
                   
                   log_message("価格監視", jan_code, "変動検知", 
                              f"商品名: {product_info['item_name']}, "
                              f"価格変動: {previous_price}円→{current_price}円 ({price_change_rate:.2f}%), "
                              f"在庫: {previous_availability}→{current_availability}")
               else:
                   log_message("価格監視", jan_code, "変動なし", 
                              f"商品名: {product_info['item_name']}, 価格: {current_price}円, 在庫: {current_availability}")
               
               # API呼び出しの間に短い遅延を挿入（レート制限対策）
               time.sleep(api_request_interval)
               
           except Exception as e:
               log_message("価格監視", jan_code, "失敗", f"商品名: {row['product_name'] if not pd.isna(row['product_name']) else '未取得'}, エラー: {str(e)}")
       
       # 変動があった商品数をログに記録
       log_message("メイン処理", "システム", "情報", f"{len(changed_products)}件の商品に変動がありました")
       
       # 商品情報に更新があった場合のみ保存
       if products_updated:
           # 商品リストの変更を保存
           save_result = save_product_list(product_df)
           log_message("メイン処理", "システム", "保存", 
                     f"商品リストの保存: {'成功' if save_result else '失敗'}")
       else:
           log_message("メイン処理", "システム", "情報", "商品情報に更新がなかったため、保存をスキップします")
       
       # 通知すべき変動商品をフィルタリング
       notifiable_products = filter_notifiable_products(changed_products, product_df, threshold)
       
       # 重複排除（JAN コードベース）
       unique_products = []
       jan_codes_seen = set()
       
       for product in notifiable_products:
           jan_code = str(product["jan_code"])
           if jan_code not in jan_codes_seen:
               jan_codes_seen.add(jan_code)
               unique_products.append(product)
       
       # 通知すべき商品数をログに記録
       if unique_products:
           log_message("メイン処理", "システム", "通知", 
                      f"重複を除外して{len(unique_products)}件の商品を通知します (元は{len(notifiable_products)}件)")
       
       # 通知対象商品をJSONファイルに保存
       if unique_products:
           with open("notifiable_products.json", "w", encoding="utf-8") as f:
               json.dump(unique_products, f, ensure_ascii=False, indent=2)
           log_message("メイン処理", "システム", "情報", f"通知対象商品をJSONファイルに保存しました")
           
           # 通知履歴を更新
           update_notification_history(unique_products)
           
           # 投稿スクリプトを実行
           run_posting_scripts()
           
           # 実際に投稿された商品だけを「通知済み」としてマークする
           posted_jan_codes = set()
           current_time = datetime.now()
           time_threshold = (current_time - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
           
           # Threadsの投稿ログをチェック
           if os.path.exists("threads_posting_log.csv"):
               try:
                   posted_df = pd.read_csv("threads_posting_log.csv")
                   recent_posts = posted_df[posted_df["timestamp"] > time_threshold]
                   
                   # 投稿に成功した商品のJANコードを取得
                   for jan_code in recent_posts[recent_posts["success"] == True]["jan_code"]:
                       posted_jan_codes.add(str(jan_code))
                       log_message("投稿確認", jan_code, "成功", "Threadsへの投稿を確認")
               except Exception as e:
                   log_message("投稿確認", "Threads", "エラー", f"ログ解析エラー: {str(e)}")

           # Twitterの投稿ログをチェック（ある場合）
           if os.path.exists("twitter_posting_log.csv"):
               try:
                   twitter_df = pd.read_csv("twitter_posting_log.csv")
                   recent_twitter = twitter_df[twitter_df["timestamp"] > time_threshold]
                   for jan_code in recent_twitter[recent_twitter["success"] == True]["jan_code"]:
                       posted_jan_codes.add(str(jan_code))
                       log_message("投稿確認", jan_code, "成功", "Twitterへの投稿を確認")
               except Exception as e:
                   log_message("投稿確認", "Twitter", "エラー", f"ログ解析エラー: {str(e)}")

           # 投稿に成功した商品だけをマークする
           for jan_code in posted_jan_codes:
               product_info = next((p for p in unique_products if str(p["jan_code"]) == jan_code), None)
               if product_info:
                   mask = product_df["jan_code"].astype(str) == jan_code
                   product_df.loc[mask, "notified_flag"] = True
                   product_df.loc[mask, "last_notified_price"] = product_info["current_price"]
                   product_df.loc[mask, "last_notified_time"] = current_time.strftime("%Y-%m-%d %H:%M:%S")
                   
                   log_message("通知状態更新", jan_code, "更新", 
                             f"投稿確認済み: notified_flag = True, last_notified_price = {product_info['current_price']}円")
           
           # 投稿に成功した件数をログに記録
           log_message("メイン処理", "システム", "完了", f"{len(posted_jan_codes)}件の商品が実際に投稿されました")
                   
           # 通知フラグが更新された場合は商品リストを再度保存
           if posted_jan_codes:
               save_result = save_product_list(product_df)
               log_message("メイン処理", "システム", "保存", 
                         f"通知フラグ更新後の商品リスト保存: {'成功' if save_result else '失敗'}")
       else:
           log_message("メイン処理", "システム", "情報", "通知対象商品がありません")
       
       return unique_products
       
   except Exception as e:
       log_message("メイン処理", "システム", "失敗", str(e))
       return []

# メイン実行関数
if __name__ == "__main__":
   try:
       # コマンドライン引数の解析
       import argparse
       parser = argparse.ArgumentParser(description="楽天商品価格監視システム")
       parser.add_argument("--dry-run", action="store_true", help="通知はスキップしてテスト実行します")
       parser.add_argument("--debug", action="store_true", help="デバッグモードで実行します")
       args = parser.parse_args()
       
       # 実行開始ログ
       if args.dry_run:
           log_message("メイン処理", "システム", "開始", "楽天商品価格監視システムをドライランモードで実行開始します（通知処理はスキップ）")
       else:
           log_message("メイン処理", "システム", "開始", "楽天商品価格監視システムの実行を開始します")
       
       # 重複するJANコードを削除
       log_message("メイン処理", "システム", "準備", "重複するJANコードを確認・削除します")
       product_df = remove_duplicate_jan_codes()
       
       # 商品監視を実行
       notified_products = monitor_products()
       
       # 処理完了をログに記録
       log_message("メイン処理", "システム", "完了", f"楽天商品価格監視システムの実行が完了しました（通知商品数: {len(notified_products)}）")
       
   except Exception as e:
       log_message("メイン処理", "システム", "失敗", f"エラー: {str(e)}")
       # スタックトレースをログに出力（デバッグ用）
       import traceback
       traceback.print_exc()
