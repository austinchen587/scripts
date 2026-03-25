# data_filter.py
import statistics
import re
from logger import logger

def clean_and_filter_candidates(candidates, demand):
    logger.info(f"开始全品类通用评分清洗: 初始 {len(candidates)} 家")
    
    brand_req = demand.get('brand', '') or demand.get('suggested_brand', '')
    item_name = demand.get('item_name', '')
    key_word = demand.get('keyword', '')
    
    # 动态准备匹配库
    brands = [b.upper().strip() for b in re.split(r'[/、,，]', brand_req) if b.strip() and b.strip() != '-']
    name_chars = set(item_name.upper()) if item_name else set()

    valid = []
    for c in candidates:
        try:
            p = float(c.get('price', 0))
            sku = str(c.get('sku', ''))
            shop = str(c.get('shop_name', ''))
            title = c.get('title', '').upper()
            
            if p <= 0.01 or 'NO_RESULT' in sku or 'System_Auto' in shop: continue
                
            c['price'] = p
            score = 0  
            
            # 1. 🛡️ 黑名单严扣分 (配件/二手/定金)
            spam = ['壳', '套', '膜', '配件', '线', '二手', '维修', '出租', '定金', '补差价', '模型']
            if any(k in title for k in spam): score -= 20
                
            # 2. 🏷️ 品牌加分 (+10)
            if brands and any(b in title for b in brands): score += 10

            # 3. 📦 品名加分 (+10)
            if item_name and item_name.upper() in title:
                score += 10
            elif name_chars:
                match_rate = sum(1 for char in name_chars if char in title) / len(name_chars)
                if match_rate < 0.4: score -= 10
                elif match_rate > 0.8: score += 5

            # 4. 🔍 关键词评分 (+10) [核心优化]
            if key_word:
                if key_word.upper() in title:
                    score += 10
                else:
                    # 细分关键词片段匹配
                    kw_parts = [k for k in re.split(r'\s+', key_word) if len(k) > 1]
                    match_count = sum(1 for kp in kw_parts if kp.upper() in title)
                    score += (match_count * 2)

            # 5. 🏪 店铺资质 (+2)
            if '旗舰店' in shop or '专卖店' in shop: score += 2

            c['score'] = score
            valid.append(c)
        except Exception: continue

    # 剔除负分不合格品
    valid = [x for x in valid if x['score'] >= 0]
    if not valid: return {}

    # 🔥 核心排序：高分优先，同分低价
    valid.sort(key=lambda x: (-x['score'], x['price']))
    logger.info(f"清洗完成，剩余 {len(valid)} 家高质量商品，最高得分: {valid[0]['score']}")

    # 安全价格区间过滤
    top_half = valid[:max(1, len(valid)//2)]
    prices = [x['price'] for x in top_half]
    median_price = statistics.median(prices)
    upper_bound = max(median_price * 6.0, 8000.0) 
    lower_bound = median_price * 0.2 

    final_pool = [c for c in valid if lower_bound <= c['price'] <= upper_bound]
    return {'default': final_pool}