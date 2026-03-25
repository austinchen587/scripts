# data_loader.py
import json
from db_manager import get_connection
from config import TABLES
from logger import logger

def fetch_single_task(brand_id):
    """
    👉 [评分制优化版] 核心数据加载器
    """
    conn = get_connection()
    if not conn: return None
    
    group = None
    try:
        with conn.cursor() as cur:
            # 👉 修复：将 keyword 改为数据库中真实的字段名 key_word
            sql_demand = f"""
                SELECT procurement_id, item_name, specifications, search_platform, key_word 
                FROM {TABLES['brand']}
                WHERE id = %s
            """
            cur.execute(sql_demand, (brand_id,))
            d = cur.fetchone()
            
            if not d:
                logger.warning(f"云端找不到 brand_id={brand_id} 的需求记录。")
                return None
                
            pid = str(d[0])
            item_name = str(d[1])
            specs = str(d[2]) if d[2] else ""
            raw_platform = str(d[3]) if d[3] else "淘宝"
            kw_req = str(d[4]) if d[4] else "" # 获取 key_word 数据

            # 2. 映射表名
            plat_map = {"京东": "jd", "淘宝": "taobao", "1688": "1688"}
            plat_code = plat_map.get(raw_platform, "taobao")
            table_search = f"procurement_commodity_{plat_code}_search"

            # 3. 拉取 Search 原始数据
            cur.execute(f"SELECT raw_data FROM {table_search} WHERE brand_id = %s ORDER BY id DESC LIMIT 1", (brand_id,))
            row = cur.fetchone()
            
            cands = []
            if row and row[0]:
                raw_data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                items = raw_data.get("items", {}).get("item", [])
                for item in items:
                    cands.append({
                        'sku': str(item.get('num_iid')),
                        'num_iid': str(item.get('num_iid')),
                        'title': str(item.get('title', '')),
                        'price': float(item.get('price') or item.get('promotion_price') or 0.0),
                        'shop_name': str(item.get('nick') or item.get('seller', '未知店铺')),
                        'sales': int(item.get('sales', 0)),
                        'detail_url': str(item.get('detail_url', '')),
                        'platform': plat_code
                    })

            group = {
                'brand_id': brand_id,
                'procurement_id': pid,
                'platform': plat_code,
                'demand': {
                    'item_name': item_name,
                    'specifications': specs,
                    'keyword': kw_req # 传递给 data_filter 评分用
                },
                'candidates': cands
            }
            logger.info(f"✅ 数据加载成功: ID:{brand_id} | 平台:{raw_platform} | 候选商品:{len(cands)}家")

    except Exception as e:
        logger.error(f"加载任务失败: {e}", exc_info=True)
    finally:
        if conn: conn.close()
    return group