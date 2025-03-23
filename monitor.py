import os
import csv
import json
import time
import pandas as pd
import requests
import subprocess
from datetime import datetime, timedelta

# ログ出力関数
def log_message(message_type, target, status, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{message_type}] [{target}] [{status}] {message}")

# 楽天APIの設定を取得
def get_rakuten_api_settings():
    return {
        "app_id": os.environ.get("RAKUTEN_APP_ID"),
        "affiliate_id": os.environ.get("RAKUTEN_AFFILIATE_ID", "")
    }

# 直近の記録と重複していないか確認
def is_duplicate_record(jan_code, current_price):
    try:
        if not os.path.exists("price_history.csv"):
            return False
            
        # 直近の履歴を10件だけ読み込む（効率化）
        last_records = pd.read_csv("price_history.csv", nrows=10, encoding="utf-8")
        
        # 同じJANコードで価格も同じレコードを検索
        matching_records = last_records[
            (last_records["jan_code"] == jan_code) & 
            (last_records["price"] == current_price)
        ]
        
        if matching_records.empty:
            return False
            
        # 最新の記録の時刻を取得
        latest_record_time = datetime.strptime(
            matching_records["timestamp"].iloc[0], 
            "%Y-%m-%d %H:%M:%S"
        )
        
        # 現在時刻との差を計算
        time_diff = datetime.now() - latest_record_time
        
        # 1時間以内の同一商品・同一価格の記録は重複とみなす
        return time_diff.total_seconds() < 3600
        
    except Exception as e:
        log_message("重複チェック", jan_code, "エラー", str(e))
        return False

# 通知履歴の取得
def get_notification_history():
    if os.path.exists("notification_history.json"):
        try:
            with open("notification_history.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log_message("通知履歴", "システム", "読込エラー", str(e))
            return {}
    return {}

# 通知履歴の保存
def save_notification_history(history):
    try:
        with open("notification_history.json", "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        log_message("通知履歴", "システム", "保存", f"{len(history)}件の履歴を保存しました")
    except Exception as e:
        log_message("通知履歴", "システム", "保存エラー", str(e))

# JANコードで商品を検索
def search_product_by_jan_code(jan_code):
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
        
        # デバッグ用にURLを出力
        print(f"DEBUG - リクエストURL: {request_url}")
        
        # APIリクエスト実行
        response = requests.get(request_url, timeout=10)
        
        # レスポンスステータスの確認
        if response.status_code != 200:
            raise ValueError(f"API応答エラー：ステータスコード {response.status_code}")
            
        # レスポンスをJSONに変換
        result = response.json()
        
        # エラーレスポンスのチェック
        if "error" in result:
            error_msg = f"楽天API エラー: {result['error']}: {result.get('error_description', '')}"
            raise ValueError(error_msg)
            
        # 検索結果の詳細を出力（デバッグ用）
        if result.get("count", 0) > 0:
            first_item = result["Items"][0]["Item"]
            log_message("楽天API詳細", f"JANコード: {jan_code}", "情報", 
                       f"最初の商品: {first_item.get('itemName')}, "
                       f"商品コード: {first_item.get('itemCode')}, "
                       f"カテゴリ: {first_item.get('genreName')}")
        
        # 実行ログに記録
        log_message("楽天API検索", f"JANコード: {jan_code}", "成功", 
                    f"検索結果: {result.get('count', 0)}件")
        
        return result
        
    except Exception as e:
        # エラーが発生した場合は実行ログに記録
        log_message("楽天API検索", f"JANコード: {jan_code}", "失敗", str(e))
        return None

# 検索結果から最適な商品を選択する
def select_best_product(search_result, jan_code):
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
            if jan_code.lower() in item_name or jan_code.lower() in item_caption:
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

# 新品商品のみをフィルタリングする
def filter_new_items(items):
    # 明確に「中古」を表すキーワード
    used_keywords = ["中古", "used", "ユーズド", "中古品"]
    
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

# JANコードから商品情報を取得する
def get_product_info_by_jan_code(jan_code):
    try:
        # JANコードで商品を検索
        search_result = search_product_by_jan_code(jan_code)
        
        if not search_result:
            raise ValueError("検索結果が取得できませんでした")
            
        if not search_result.get("Items") or len(search_result["Items"]) == 0:
            raise ValueError(f"JANコード {jan_code} に一致する商品が見つかりませんでした")
            
        # 検索結果から新品商品を選択
        selected_product = select_best_product(search_result, jan_code)
        
        # 新品商品が見つからない場合は「新品なし」状態を返す
        if not selected_product:
            log_message("商品選択", jan_code, "情報", "新品商品がないため、在庫なし状態を返します")
            return {
                "jan_code": jan_code,
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
        product_info = {
            "jan_code": jan_code,
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
        
        log_message("商品情報取得", jan_code, "成功", 
                    f"新品商品: {product_info['item_name']}, "
                    f"価格: {product_info['item_price']}円, "
                    f"在庫: {product_info['availability']}")
                    
        return product_info
        
    except Exception as e:
        log_message("商品情報取得", jan_code or "なし", "失敗", f"エラー: {str(e)}")
        
        # エラー発生時にダミー商品情報を返す
        return {
            "jan_code": jan_code or "",
            "item_name": f"取得できませんでした（{jan_code}）",
            "item_price": 0,
            "shop_name": "不明",
            "availability": "不明",
            "item_url": "",
            "affiliate_url": "",
            "image_url": "",
            "is_new_item": False
        }

# 価格履歴に記録する
def record_price_history(jan_code, product_name, price, availability, shop_name, price_change_rate=0, notified=False):
    try:
        # 重複チェック - 1時間以内に同じ商品・同じ価格の記録があれば記録しない
        if is_duplicate_record(jan_code, price):
            log_message("価格履歴記録", jan_code, "スキップ", "1時間以内に同じ価格の記録があるため重複を省略します")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return {"timestamp": timestamp}
            
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open("price_history.csv", mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                timestamp,
                jan_code,
                product_name,
                price,
                availability,
                shop_name,
                price_change_rate,
                "TRUE" if notified else "FALSE"
            ])
            
        return {"timestamp": timestamp}
        
    except Exception as e:
        log_message("価格履歴記録", jan_code, "失敗", str(e))
        return None

# 通知すべき商品をフィルタリング
def filter_notifiable_products(changed_products, product_df, threshold=5):
    notifiable = []
    
    # 通知履歴を読み込む
    notification_history = get_notification_history()
    
    # 絶対額での最小変動額
    min_price_change_amount = 500
    
    # 変動率の最小閾値（1%未満の変動は無視）
    min_rate_threshold = 1.0
    
    # 現在の時刻
    current_time = datetime.now()
    
    # 通知間隔（最低72時間＝3日間は同じ商品を再通知しない）
    min_hours_between_notifications = 72
    
    for product in changed_products:
        jan_code = product["jan_code"]
        
        # 変動率が非常に小さい場合はスキップ
        if abs(product["price_change_rate"]) < min_rate_threshold:
            log_message("通知フィルタ", jan_code, "スキップ", 
                      f"変動率が小さすぎます: {product['price_change_rate']:.2f}%")
            continue
            
        # 絶対額での変動が小さい場合はスキップ
        price_change_amount = abs(product["current_price"] - product["previous_price"])
        if price_change_amount < min_price_change_amount:
            log_message("通知フィルタ", jan_code, "スキップ", 
                      f"価格変動額が小さすぎます: {price_change_amount}円")
            continue
        
        # 通知履歴を確認
        if jan_code in notification_history:
            last_time_str = notification_history[jan_code]["last_notified_time"]
            last_time = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
            
            # 前回の通知からの経過時間を計算
            time_diff = current_time - last_time
            hours_since_last_notification = time_diff.total_seconds() / 3600
            
            # 通知間隔が短すぎる場合はスキップ
            if hours_since_last_notification < min_hours_between_notifications:
                log_message("通知フィルタ", jan_code, "スキップ", 
                          f"前回通知から{hours_since_last_notification:.1f}時間しか経過していません（最低{min_hours_between_notifications}時間必要）")
                continue
                
            # 前回通知時の価格と比較
            last_price = notification_history[jan_code]["last_price"]
            price_diff_percent = abs((product["current_price"] - last_price) / last_price * 100) if last_price > 0 else 100
            
            # 価格差が小さい場合はスキップ
            if price_diff_percent < threshold:
                log_message("通知フィルタ", jan_code, "スキップ", 
                          f"前回通知時価格({last_price}円)から変動が小さいため通知しません({price_diff_percent:.2f}%)")
                continue
        
        # 商品リストから該当商品の行を取得
        product_row = product_df[product_df["jan_code"] == jan_code]
        
        if product_row.empty:
            log_message("通知フィルタ", jan_code, "警告", "商品リストに該当商品が見つかりません")
            continue
            
        # 価格下落の判定（変動率が負の値かつ閾値以上）
        price_reduced = (product["price_change_rate"] < 0 and 
                        abs(product["price_change_rate"]) >= threshold)
        
        # 在庫が復活した場合の判定
        stock_restored = (product["previous_availability"] == "在庫なし" and 
                         product["current_availability"] == "在庫あり")
        
        # 現在在庫があるかどうかを確認
        has_stock = product["current_availability"] == "在庫あり"
        
        # 条件に合致し、かつ在庫がある場合のみ通知対象とする
        if (price_reduced or stock_restored) and has_stock:
            notifiable.append(product)
            log_message("通知フィルタ", jan_code, "通知対象", 
                      f"価格: {product['current_price']}円, 変動率: {product['price_change_rate']:.2f}%, 在庫: {product['current_availability']}")
            
    return notifiable

# 通知履歴を更新
def update_notification_history(notifiable_products):
    try:
        history = get_notification_history()
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 新しい通知を履歴に追加
        for product in notifiable_products:
            jan_code = product["jan_code"]
            history[jan_code] = {
                "product_name": product["product_name"],
                "last_price": product["current_price"],
                "last_notified_time": current_time_str
            }
        
        # 履歴を保存
        save_notification_history(history)
        log_message("通知履歴", "システム", "更新", f"{len(notifiable_products)}件の通知履歴を更新しました")
    except Exception as e:
        log_message("通知履歴", "システム", "更新失敗", str(e))

# 投稿スクリプトを実行する関数
def run_posting_scripts():
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
        
        # Twitterに投稿 (コメントアウトされているかチェック)
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

# 監視対象商品の変動を監視するメイン関数（一括処理）
def monitor_products():
    try:
        # 価格履歴ファイルが存在しない、または空の場合は新規作成
        is_file_empty = False
        if os.path.exists("price_history.csv"):
            # ファイルサイズをチェック
            is_file_empty = os.path.getsize("price_history.csv") == 0
        
        if not os.path.exists("price_history.csv") or is_file_empty:
            with open("price_history.csv", mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow([
                    "timestamp", "jan_code", "product_name", "price", 
                    "availability", "shop_name", "price_change_rate", "notified"
                ])

        # 商品リストを読み込む
        product_df = pd.read_csv("product_list.csv")
        
        # 商品リストに必要な列が存在するか確認し、なければ追加
        if "last_notified_price" not in product_df.columns:
            product_df["last_notified_price"] = float('nan')
            log_message("メイン処理", "システム", "情報", "last_notified_price 列を追加しました")
            
        if "last_notified_time" not in product_df.columns:
            product_df["last_notified_time"] = None
            log_message("メイン処理", "システム", "情報", "last_notified_time 列を追加しました")
        
        # 監視対象の商品のみを抽出
        active_products = product_df[product_df["monitor_flag"] == True]
        
        if len(active_products) == 0:
            log_message("メイン処理", "システム", "警告", "監視対象の商品がありません")
            return []
            
        log_message("メイン処理", "システム", "開始", f"合計{len(active_products)}件の商品を監視します")
        
        threshold = float(os.environ.get("PRICE_CHANGE_THRESHOLD", "5"))  # 通知する価格変動閾値
        changed_products = []
        
        # すべての監視対象商品を処理
        for index, row in active_products.iterrows():
            jan_code = str(row["jan_code"]).strip()
            
            try:
                # 処理中であることをログに記録
                log_message("価格監視", jan_code, "処理中", f"商品名: {row['product_name'] if not pd.isna(row['product_name']) else '未取得'}, 処理を開始します")
                
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
                if previous_price == 0:
                    # 商品リストを更新
                    product_df.loc[product_df["jan_code"] == jan_code, "product_name"] = product_info["item_name"]
                    product_df.loc[product_df["jan_code"] == jan_code, "last_price"] = current_price
                    product_df.loc[product_df["jan_code"] == jan_code, "last_availability"] = current_availability
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
                    
                    # 重複チェック - 直近の記録と価格が同じなら記録しない
                    if is_duplicate_record(jan_code, current_price):
                        log_message("価格監視", jan_code, "重複スキップ", 
                                  f"1時間以内に同じ価格({current_price}円)の記録があるためスキップします")
                        continue
                    
                    # 商品リストを更新
                    product_df.loc[product_df["jan_code"] == jan_code, "product_name"] = product_info["item_name"]
                    product_df.loc[product_df["jan_code"] == jan_code, "last_price"] = current_price
                    product_df.loc[product_df["jan_code"] == jan_code, "last_availability"] = current_availability
                    
                    # 変動情報を価格履歴に記録
                    history_info = record_price_history(
                        jan_code,
                        product_info["item_name"],
                        current_price,
                        current_availability,
                        product_info["shop_name"],
                        price_change_rate
                    )
                    
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
                        "timestamp": history_info["timestamp"] if history_info else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
                    log_message("価格監視", jan_code, "変動検知", 
                               f"商品名: {product_info['item_name']}, "
                               f"価格変動: {previous_price}円→{current_price}円 ({price_change_rate:.2f}%), "
                               f"在庫: {previous_availability}→{current_availability}")
                else:
                    log_message("価格監視", jan_code, "変動なし", 
                               f"商品名: {product_info['item_name']}, 価格: {current_price}円, 在庫: {current_availability}")
                
                # API呼び出しの間に短い遅延を挿入（レート制限対策）
                time.sleep(1)
                
            except Exception as e:
                log_message("価格監視", jan_code, "失敗", f"商品名: {row['product_name'] if not pd.isna(row['product_name']) else '未取得'}, エラー: {str(e)}")
        
        # 変動があった商品数をログに記録
        log_message("メイン処理", "システム", "情報", f"{len(changed_products)}件の商品に変動がありました")
        
        # 通知すべき変動商品をフィルタリング
        notifiable_products = filter_notifiable_products(changed_products, product_df, threshold)
        
        # 重複排除（JAN コードベース）
        unique_products = []
        jan_codes_seen = set()
        
        for product in notifiable_products:
            jan_code = product["jan_code"]
            if jan_code not in jan_codes_seen:
                jan_codes_seen.add(jan_code)
                unique_products.append(product)
        
        # 通知すべき商品数をログに記録
        if notifiable_products:
            log_message("メイン処理", "システム", "通知", 
                       f"重複を除外して{len(unique_products)}件の商品を通知します (元は{len(notifiable_products)}件)")
        
        # 通知対象商品をJSONファイルに保存
        if unique_products:
            with open("notifiable_products.json", "w", encoding="utf-8") as f:
                json.dump(unique_products, f, ensure_ascii=False, indent=2)
            log_message("メイン処理", "システム", "情報", f"通知対象商品をJSONファイルに保存しました")
            
            # 通知履歴を更新
            update_notification_history(unique_products)
            
            # 通知対象商品の notified_flag と last_notified_price を更新
            for product in unique_products:
                jan_code = product["jan_code"]
                current_price = product["current_price"]
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # 通知フラグを更新
                product_df.loc[product_df["jan_code"] == jan_code, "notified_flag"] = True
                
                # 最後に通知した価格を更新
                product_df.loc[product_df["jan_code"] == jan_code, "last_notified_price"] = current_price
                
                # 最後に通知した時刻を更新
                product_df.loc[product_df["jan_code"] == jan_code, "last_notified_time"] = current_time
                
                log_message("通知状態更新", jan_code, "更新", 
                           f"notified_flag = True, last_notified_price = {current_price}円, last_notified_time = {current_time}")
            
            # 商品リストの変更を保存
            product_df.to_csv("product_list.csv", index=False)
            
            # 投稿スクリプトを実行
            run_posting_scripts()
        else:
            log_message("メイン処理", "システム", "情報", "通知対象商品がありません")
            
            # 商品リストの変更を保存（通知対象でなくても更新内容は保存）
            product_df.to_csv("product_list.csv", index=False)
        
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
        args = parser.parse_args()
        
        # 実行開始ログ
        if args.dry_run:
            log_message("メイン処理", "システム", "開始", "楽天商品価格監視システムをドライランモードで実行開始します（通知処理はスキップ）")
        else:
            log_message("メイン処理", "システム", "開始", "楽天商品価格監視システムの実行を開始します")
        
        # 商品監視を実行
        notified_products = monitor_products()
        
        # 処理完了をログに記録
        log_message("メイン処理", "システム", "完了", f"楽天商品価格監視システムの実行が完了しました（通知商品数: {len(notified_products)}）")
        
    except Exception as e:
        log_message("メイン処理", "システム", "失敗", f"エラー: {str(e)}")
