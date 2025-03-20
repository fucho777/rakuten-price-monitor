import os
import csv
import json
import time
import pandas as pd
import requests
from datetime import datetime

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
            "keyword": jan_code,
            "hits": 30,
            "sort": "+itemPrice",
            "availability": 1,
            "format": "json"
        }
        
        # URLパラメータ構築
        query_string = "&".join([f"{key}={value}" for key, value in params.items()])
        request_url = f"{base_url}?{query_string}"
        
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
            
        # 実行ログに記録
        log_message("楽天API検索", f"JANコード: {jan_code}", "成功", 
                    f"検索結果: {result.get('count', 0)}件")
        
        return result
        
    except Exception as e:
        # エラーが発生した場合は実行ログに記録
        log_message("楽天API検索", f"JANコード: {jan_code}", "失敗", str(e))
        return None

# 検索結果から最適な商品を選択する
def select_best_product(search_result):
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
            
        # 価格の安い順にソート
        valid_items.sort(key=lambda x: int(x["itemPrice"]))
        
        # 最安値の商品を選択
        selected_item = valid_items[0]
        
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
        selected_product = select_best_product(search_result)
        
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
def filter_notifiable_products(changed_products, threshold=5):
    notifiable = []
    
    for product in changed_products:
        # 価格下落の判定（変動率が負の値かつ閾値以上）
        price_reduced = (product["price_change_rate"] < 0 and 
                        abs(product["price_change_rate"]) >= threshold)
        
        # 在庫が復活した場合の判定
        stock_restored = (product["previous_availability"] == "在庫なし" and 
                         product["current_availability"] == "在庫あり")
        
        if price_reduced or stock_restored:
            notifiable.append(product)
            
    return notifiable

# 監視対象商品の変動を監視するメイン関数
def monitor_products():
    try:
        # 商品リストを読み込む
        product_df = pd.read_csv("product_list.csv")
        
        # 監視対象の商品のみを抽出
        active_products = product_df[product_df["monitor_flag"] == True]
        
        if len(active_products) == 0:
            log_message("メイン処理", "システム", "警告", "監視対象の商品がありません")
            return []
            
        log_message("メイン処理", "システム", "開始", f"合計{len(active_products)}件の商品を監視します")
        
        changed_products = []
        
        # 各商品を処理
        for index, row in active_products.iterrows():
            jan_code = str(row["jan_code"]).strip()
            
            try:
                # 処理中であることをログに記録
                log_message("価格監視", jan_code, "処理中", f"商品名: {row['product_name']}, 処理を開始します")
                
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
                    product_df.at[index, "product_name"] = product_info["item_name"]
                    product_df.at[index, "last_price"] = current_price
                    product_df.at[index, "last_availability"] = current_availability
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
                    
                    # 商品リストを更新
                    product_df.at[index, "product_name"] = product_info["item_name"]
                    product_df.at[index, "last_price"] = current_price
                    product_df.at[index, "last_availability"] = current_availability
                    
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
                log_message("価格監視", jan_code, "失敗", f"商品名: {row['product_name']}, エラー: {str(e)}")
        
        # 商品リストの変更を保存
        product_df.to_csv("product_list.csv", index=False)
        
        log_message("メイン処理", "システム", "完了", f"{len(changed_products)}件の商品に変動がありました")
        
        return changed_products
        
    except Exception as e:
        log_message("メイン処理", "システム", "失敗", str(e))
        return []

# メイン実行関数
if __name__ == "__main__":
    try:
        # 実行開始ログ
        log_message("メイン処理", "システム", "開始", "楽天商品価格監視システムの実行を開始します")
        
        # 1. 商品監視を実行
        changed_products = monitor_products()
        
        # 2. 変動があった商品数をログに記録
        log_message("メイン処理", "システム", "進行中", f"変動があった商品数: {len(changed_products)}件")
        
        # 3. 通知すべき変動商品をフィルタリング
        threshold = float(os.environ.get("PRICE_CHANGE_THRESHOLD", "5"))
        notifiable_products = filter_notifiable_products(changed_products, threshold)
        
        # 4. 通知すべき商品数をログに記録
        log_message("メイン処理", "システム", "進行中", f"通知すべき商品数: {len(notifiable_products)}件")
        
        # 5. 通知すべき商品をJSONファイルに保存（social_poster.pyで使用）
        if notifiable_products:
            with open("notifiable_products.json", "w", encoding="utf-8") as f:
                json.dump(notifiable_products, f, ensure_ascii=False, indent=2)
                
        # 6. 処理完了をログに記録
        log_message("メイン処理", "システム", "完了", "楽天商品価格監視システムの実行が完了しました")
        
    except Exception as e:
        log_message("メイン処理", "システム", "失敗", f"エラー: {str(e)}")
