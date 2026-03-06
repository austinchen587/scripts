# processor.py
import re
from logger_helper import logger

def process_and_map(raw_results, procurement_id, item_name):
    """
    Clean data, map fields, and deduplicate
    """
    mapped_data = []
    seen_keys = set()

    for item in raw_results:
        # Basic cleaning
        price_str = item.get('价格', '0')
        price_match = re.search(r'\d+\.?\d*', price_str)
        price_clean = float(price_match.group()) if price_match else 0.0
        
        title = item.get('标题', 'N/A')
        platform = item.get('平台', '未知')

        # Deduplication key
        unique_key = (procurement_id, title, platform)
        if unique_key in seen_keys:
            continue
        seen_keys.add(unique_key)

        # Construct record
        record = {
            'procurement_id': procurement_id,
            'sku': item.get('sku'),
            'platform': platform,
            'title': title,
            'price': price_clean,
            'shop_name': item.get('店铺'),
            'sales': item.get('销量'),
            'detail_url': item.get('详细链接'),
            'hot_info': item.get('评价热度'),
            'item_name': item_name # Added field
        }
        mapped_data.append(record)

    # [新增] 打印最终保留多少条
    logger.info(f"--- [清洗结束] 去重后保留: {len(mapped_data)} 条 (过滤掉 {len(raw_results) - len(mapped_data)} 条) ---")
        
    return mapped_data