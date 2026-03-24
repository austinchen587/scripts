import statistics
import re
from logger import logger

def clean_and_filter_candidates(candidates, demand):
    logger.info(f"开始清洗候选池: 初始 {len(candidates)} 家")
    
    brand_req = demand.get('brand', '') or demand.get('suggested_brand', '')
    specs_req = demand.get('specifications', '')
    item_name = demand.get('item_name', '')
    
    # 【新增】智能提取规格中的核心数字（如“24盘”中的“24”）
    # 修改后：提取数字+紧跟其后的一个中文单位（如 "24盘", "150抽", "304不"会忽略）
    key_numbers = re.findall(r'\d+[\u4e00-\u9fa5]?', specs_req)
    # 过滤掉无意义的常见数字组合
    key_numbers = [n for n in key_numbers if n not in ['304', '201', '220V', '50Hz']]
    
    valid = []
    for c in candidates:
        try:
            p = float(c.get('price', 0))
            sku = str(c.get('sku', ''))
            shop = str(c.get('shop_name', ''))
            title = c.get('title', '').upper()
            
            if p <= 0.01 or 'NO_RESULT' in sku or 'System_Auto' in shop: 
                continue
                
            c['price'] = p
            c['score'] = 0  
            
            # A. 品牌强制加分
            if brand_req and brand_req.upper() in title:
                c['score'] += 100
            elif brand_req and brand_req.upper() in shop.upper():
                c['score'] += 50
                
            # B. 规格命中加分
            specs_words = [w for w in re.split(r'[,;，；\s]+', specs_req) if len(w) > 1]
            for word in specs_words:
                if word.upper() in title:
                    c['score'] += 20
                    
            # 【新增】C. 核心数字暴击加分（防止24盘被误杀）
            for num in key_numbers:
                # 确保是独立数字，比如 24盘，防误伤
                if num in title:
                    c['score'] += 80  
                    
            # D. 降权排雷词
            bad_words = ["配件", "支架", "定金", "尾款", "适用", "兼容", "专用液", "耗材", "维修", "以旧换新", "起步"]
            is_buying_accessory = any(bw in item_name or bw in specs_req for bw in ["配件", "耗材", "液", "支架"])
            
            if not is_buying_accessory:
                if any(bw in title for bw in bad_words):
                    c['score'] -= 200  
            
            valid.append(c)
        except Exception as e:
            logger.error(f"解析 SKU 异常: {e}")
            continue

    positive_candidates = [x for x in valid if x['score'] >= 0]
    if positive_candidates:
        valid = positive_candidates
        logger.info(f"经过硬性引流排雷，剩余 {len(valid)} 家高质量商品")
    else:
        logger.warning("未发现完美匹配的商品，保留全部数据进行 AI 兜底评估")

    if not valid: return {}

    # 【优化】先按分数排序，让好商品排在前面
    valid.sort(key=lambda x: (-x['score'], x['price']))

    # 【核心优化】只用前 50% 的高分商品来计算中位数，防止被底层垃圾配件拉低！
    # 【核心优化】只用前 50% 的高分商品来计算中位数，防止被底层垃圾配件拉低！
    top_half = valid[:max(1, len(valid)//2)]
    prices = [x['price'] for x in top_half]
    median_price = statistics.median(prices)
    logger.info(f"当前池内(高分段)价格中位数为: ￥{median_price:.2f}")

    # 👉 【核心修复】动态安全上限：即便中位数被垃圾拉低，也至少给足 8000 元的安全空间！
    upper_bound = max(median_price * 6.0, 8000.0) 
    lower_bound = median_price * 0.2 

    final_pool = []
    for x in valid:
        is_price_ok = (x['price'] >= lower_bound and x['price'] <= upper_bound)
        # 👉 降低 VIP 门槛：只要命中了任何规格词/数字/品牌（分数>=20），直接无视价格限制！
        has_vip_pass = (x['score'] >= 20) 
        
        if is_price_ok or has_vip_pass:
            final_pool.append(x)
        else:
            logger.info(f"  - [价格异常剥离] 剔除: ￥{x['price']} - {x.get('title')[:30]} (分数:{x['score']})")

    if not final_pool:
        final_pool = valid

    final_pool.sort(key=lambda x: (-x['score'], x['price']))
    logger.info(f"🎯 清洗完成，最终保留 {len(final_pool)} 家高匹配度商品直接进入淘汰赛")

    return {'default': final_pool[:30]}