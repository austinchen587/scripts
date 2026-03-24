# data_loader.py
import json
from db_manager import get_connection
from config import TABLES
from logger import logger

def fetch_single_task(brand_id):
    """
    👉 [新架构] 核心数据加载器
    不再查旧的 sku 列表表，直接去云端对应的 JSONB 搜索结果表拉取原始数据并解析为候选池。
    """
    conn = get_connection()
    if not conn: return None
    
    group = None
    try:
        with conn.cursor() as cur:
            # 1. 查询基础需求信息及搜索平台 (用于确定去哪张搜索表查数据)
            sql_demand = f"""
                SELECT procurement_id, item_name, specifications, search_platform 
                FROM {TABLES['brand']}
                WHERE id = %s
            """
            cur.execute(sql_demand, (brand_id,))
            d = cur.fetchone()
            
            if not d:
                logger.warning(f"云端找不到 brand_id={brand_id} 的需求记录。")
                return None
                
            pid = str(d[0])  # 确保 procurement_id 为字符串
            item_name = str(d[1])
            specs = str(d[2]) if d[2] else ""
            raw_platform = str(d[3]) if d[3] else "淘宝"

            # 2. 映射平台名称到云端对应的 Search 表名后缀
            plat_map = {"京东": "jd", "淘宝": "taobao", "1688": "1688"}
            plat_code = plat_map.get(raw_platform, "taobao")
            table_search = f"procurement_commodity_{plat_code}_search"

            # 3. 从对应的 JSONB 搜索结果表中拉取最新的原始数据
            # 配合您刚才建立的复合索引 (procurement_id, brand_id) 进行极速查询
            cur.execute(f"""
                SELECT raw_data 
                FROM {table_search} 
                WHERE procurement_id = %s AND brand_id = %s 
                ORDER BY id DESC LIMIT 1
            """, (pid, brand_id))
            
            s_row = cur.fetchone()
            cands = []

            if s_row and s_row[0]:
                raw_data = s_row[0]
                # 兼容处理：如果是字符串格式则解析为字典
                if isinstance(raw_data, str):
                    raw_data = json.loads(raw_data)
                
                # 解析 OneBound 搜索接口的标准返回结构: items -> item 列表
                items = raw_data.get("items", {}).get("item", [])
                for item in items:
                    # 提取 AI 选品引擎需要的核心字段
                    cands.append({
                        'sku': str(item.get('num_iid')),       # 键名保持 'sku' 以兼容您原有的过滤逻辑
                        'num_iid': str(item.get('num_iid')),   # 同时也存一份标准的 num_iid
                        'title': str(item.get('title', '')),
                        'price': float(item.get('price') or item.get('promotion_price') or 0.0),
                        'shop_name': str(item.get('nick') or item.get('seller', '未知店铺')),
                        'sales': int(item.get('sales', 0)),
                        'detail_url': str(item.get('detail_url', '')),
                        'platform': plat_code
                    })

            # 4. 封装成 llm_service.py 需要的 group 结构
            group = {
                'brand_id': brand_id,
                'procurement_id': pid,
                'platform': plat_code,
                'demand': {
                    'item_name': item_name,
                    'specifications': specs
                },
                'candidates': cands
            }
            logger.info(f"✅ 数据加载成功: ID:{brand_id} | 平台:{raw_platform} | 候选商品:{len(cands)}家")
                
    except Exception as e:
        logger.error(f"❌ 数据加载流程发生异常 [BrandID:{brand_id}]: {e}")
    finally:
        if conn: conn.close()
        
    return group