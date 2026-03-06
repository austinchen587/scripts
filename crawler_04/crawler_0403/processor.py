# processor.py
import re
from logger_helper import logger

def process_and_map(raw_results, procurement_id, item_name):
    """
    清洗 raw_data，映射字段，并去重
    """
    mapped_data = []
    seen_keys = set() # 内存级去重

    for item in raw_results:
        # 1. 价格清洗 (提取数字)
        price_str = str(item.get('价格', '0'))
        # 匹配浮点数
        price_match = re.search(r'\d+\.?\d*', price_str)
        try:
            price_clean = float(price_match.group()) if price_match else 0.0
        except:
            price_clean = 0.0
        
        # 2. 基础字段
        title = item.get('标题', 'N/A')
        platform = item.get('平台', '未知')
        
        # 3. 内存去重 (防止同一页抓取到重复商品)
        unique_key = (procurement_id, title, platform)
        if unique_key in seen_keys:
            continue
        seen_keys.add(unique_key)

        # 4. 构建标准记录
        record = {
            'procurement_id': procurement_id,
            'sku': item.get('sku'),
            'platform': platform,
            'title': title,
            'price': price_clean,
            'shop_name': item.get('店铺', '未知'),
            'sales': item.get('销量', '0'),
            'detail_url': item.get('详细链接', ''),
            'hot_info': item.get('评价热度', ''),
            'item_name': item_name
        }
        mapped_data.append(record)

    logger.info(f"✨ [Processor] 清洗前: {len(raw_results)} -> 清洗后: {len(mapped_data)}")
    return mapped_data