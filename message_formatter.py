# message_formatter.py という新しいファイルを作成

def format_price_change_message(product, platform="common"):
    """共通の価格変動メッセージフォーマット関数"""
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
    
    # プラットフォーム別のフォーマット
    if platform == "twitter":
        # Twitter用（280文字制限あり）
        max_product_name_length = 50
        product_name = product["product_name"]
        if len(product_name) > max_product_name_length:
            product_name = product_name[:max_product_name_length-3] + "..."
            
        message = (
            f"【価格変動】\n"
            f"商品名：{product_name}\n"
            f"価格：{product['current_price']:,}円（{change_rate_str}%）\n"
            f"在庫：{availability_status}\n"
            f"販売：{product['shop_name']}\n"
            f"{product['affiliate_url']}"
        )
    
    elif platform == "threads":
        # スレッズ用（文字数制限なし）
        message = (
            f"【価格変動】\n"
            f"商品名：{product['product_name']}\n"
            f"価格：{product['current_price']:,}円（{change_rate_str}%）\n"
            f"前回：{product['previous_price']:,}円\n"
            f"在庫：{availability_status}\n"
            f"販売：{product['shop_name']}\n"
            f"{product['affiliate_url']}"
        )
    
    else:
        # 共通フォーマット
        message = (
            f"【価格変動】\n"
            f"商品名：{product['product_name']}\n"
            f"価格：{product['current_price']:,}円（{change_rate_str}%）\n"
            f"在庫：{availability_status}\n"
            f"販売：{product['shop_name']}\n"
            f"{product['affiliate_url']}"
        )
    
    return message
