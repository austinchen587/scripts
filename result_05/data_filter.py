# data_loader.py
from db_manager import get_connection
from config import TABLES
from logger import logger

def clean_and_filter_candidates(candidates):
    """
    高级预筛选逻辑：
    1. 基础清洗（去0元、脏数据）
    2. 价格三级分组 (Low, Mid, High)
    3. 组内离散度过滤 (组内均值偏差 > 50% 剔除)
    返回：{'low': [...], 'mid': [...], 'high': [...]} 
    """
    logger.info(f"开始清洗候选池: 初始 {len(candidates)} 家")
    
    # 1. 基础清洗
    valid = []
    for c in candidates:
        try:
            p = float(c.get('price', 0))
            sku = str(c.get('sku', ''))
            shop = str(c.get('shop_name', ''))
            
            if p <= 0.01: continue
            if 'NO_RESULT' in sku: continue
            if 'System_Auto' in shop: continue
                
            c['price'] = p
            valid.append(c)
        except: continue

    if not valid:
        logger.warning("所有候选商品均因数据无效被剔除！")
        return []

    # 如果数量太少，不分组，直接返回单组
    if len(valid) < 9:
        logger.info(f"有效商品仅 {len(valid)} 家，不进行分层，直接作为单一分组。")
        # 简单过滤离散度
        avg = sum(x['price'] for x in valid) / len(valid)
        final = [x for x in valid if abs(x['price'] - avg)/avg <= 0.8] # 宽松一点
        if not final: final = valid
        return {'default': final}

    # 2. 排序
    valid.sort(key=lambda x: x['price'])

    # 3. 三分位分组
    # 使用 numpy.array_split 模拟或简单切片
    n = len(valid)
    k, m = divmod(n, 3)
    # 计算切分点
    # split into 3 parts
    # part 1: 0 -> k + (1 if m>0 else 0)
    # part 2: ... -> ... + k + (1 if m>1 else 0)
    # part 3: ...
    
    p1 = k + (1 if m>0 else 0)
    p2 = p1 + k + (1 if m>1 else 0)
    
    low_group = valid[:p1]
    mid_group = valid[p1:p2]
    high_group = valid[p2:]
    
    logger.info(f"价格分层: 低价组({len(low_group)}) | 中价组({len(mid_group)}) | 高价组({len(high_group)})")

    # 4. 组内离散度过滤函数
    def filter_group(group, group_name):
        if not group: return []
        prices = [x['price'] for x in group]
        
        # 去掉组内最高和最低（如果组够大），防止组内均值被边界值拉偏
        if len(group) > 5:
            core_prices = sorted(prices)[1:-1]
        else:
            core_prices = prices
            
        if not core_prices: core_prices = prices # 兜底
            
        avg = sum(core_prices) / len(core_prices)
        logger.info(f"  > [{group_name}] 均价基准: ￥{avg:.2f}")
        
        cleaned = []
        for x in group:
            if abs(x['price'] - avg) / avg <= 0.5: # 50% 偏差阈值
                cleaned.append(x)
            else:
                logger.info(f"    - [剔除] 组内离散: ￥{x['price']} (偏离 {group_name} 均价 {abs(x['price'] - avg)/avg*100:.0f}%)")
        
        # 兜底：如果过滤完了，就只保留核心均价附近的
        if not cleaned:
            logger.warning(f"    ! [{group_name}] 过滤后为空，回退保留组内数据")
            return group
        return cleaned

    # 执行组内过滤
    filtered_tiers = {
        'low': filter_group(low_group, "低价组"),
        'mid': filter_group(mid_group, "中价组"),
        'high': filter_group(high_group, "高价组")
    }
    
    return filtered_tiers