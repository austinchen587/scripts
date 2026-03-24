# data_filter.py
import statistics
import re
from logger import logger

def clean_and_filter_candidates(candidates, demand):
    logger.info(f"开始通用清洗候选池: 初始 {len(candidates)} 家")
    
    # 动态提取甲方的基础要求
    brand_req = demand.get('brand', '') or demand.get('suggested_brand', '')
    item_name = demand.get('item_name', '')
    
    # 1. 动态拆分品牌别名 (例如 "联想/lenovo" -> ['联想', 'LENOVO'])
    brands = [b.upper().strip() for b in re.split(r'[/、,，]', brand_req) if b.strip() and b.strip() != '-']
    
    # 2. 提取品名核心字符集 (用于算重合度)
    name_chars = set(item_name.upper()) if item_name else set()

    valid = []
    for c in candidates:
        try:
            p = float(c.get('price', 0))
            sku = str(c.get('sku', ''))
            shop = str(c.get('shop_name', ''))
            title = c.get('title', '').upper()
            
            # 剔除无效数据
            if p <= 0.01 or 'NO_RESULT' in sku or 'System_Auto' in shop: 
                continue
                
            c['price'] = p
            c['score'] = 0  
            
            # ---------------------------------------------------------
            # 🛡️ 通用规则 1：全品类电商垃圾词过滤
            # ---------------------------------------------------------
            spam_keywords = ['壳', '套', '膜', '配件', '线', '二手', '维修', '出租', '租赁', '体验', '试用', '补差价', '定金', '专修', '同款', '模型']
            if any(k in title for k in spam_keywords):
                c['score'] -= 20 # 只要命中，直接判负分淘汰
                
            # ---------------------------------------------------------
            # 🛡️ 通用规则 2：动态品牌匹配
            # ---------------------------------------------------------
            if brands:
                if any(b in title for b in brands):
                    c['score'] += 10 # 命中甲方要求的品牌，加分保送
                elif p < 200: 
                    # 如果没命中品牌，且价格很低，极大概率是杂牌配件
                    c['score'] -= 5

            # ---------------------------------------------------------
            # 🛡️ 通用规则 3：品类名纯文本相关性校验 (防跨类目蹭流量)
            # ---------------------------------------------------------
            if item_name:
                if item_name.upper() in title:
                    c['score'] += 10 # 品名完全包含，加分
                else:
                    # 如果品名没完整出现，算一下字符重叠率
                    match_chars = sum(1 for char in name_chars if char in title)
                    if len(name_chars) > 0 and (match_chars / len(name_chars)) < 0.4:
                        # 连品名里 40% 的字都没在标题里出现，大概率是毫不相干的商品
                        c['score'] -= 10 

            # 店铺资质加权 (全网通用)
            if '旗舰店' in shop or '专卖店' in shop: 
                c['score'] += 2

            valid.append(c)
        except Exception as e:
            logger.error(f"解析 SKU 异常: {e}")
            continue

    # 剔除所有负分商品 (被通用规则判死的垃圾数据)
    positive_candidates = [x for x in valid if x['score'] >= 0]
    if positive_candidates:
        valid = positive_candidates
        logger.info(f"经过全品类通用排雷，剩余 {len(valid)} 家高质量商品")
    else:
        logger.warning("未发现完美匹配的商品，执行强制降级保留，交由 AI 兜底")
        valid = sorted(valid, key=lambda x: x['score'], reverse=True)[:max(5, len(valid)//3)]

    if not valid: return {}

    # 按分数从高到低排序，分数相同看价格
    valid.sort(key=lambda x: (-x['score'], x['price']))

    # 动态安全上限计算 (防超高价干扰)
    top_half = valid[:max(1, len(valid)//2)]
    prices = [x['price'] for x in top_half]
    median_price = statistics.median(prices)
    logger.info(f"当前池内(高分段)价格中位数为: ￥{median_price:.2f}")

    upper_bound = max(median_price * 6.0, 8000.0) 
    lower_bound = median_price * 0.2 

    final_pool = []
    for c in valid:
        if lower_bound <= c['price'] <= upper_bound:
            final_pool.append(c)
            
    return {'default': final_pool}