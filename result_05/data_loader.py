from db_manager import get_connection, get_processed_brand_ids
from config import TABLES
from logger import logger

def fetch_procurement_groups():
    conn = get_connection()
    if not conn: return []
    
    processed_ids = get_processed_brand_ids()
    if processed_ids:
        logger.info(f"数据库中已有 {len(processed_ids)} 条已完成记录，将自动跳过。")

    groups = []
    seen_in_this_run = set()

    try:
        with conn.cursor() as cur:
            logger.info("正在读取采购需求数据...")
            sql_demand = f"""
                SELECT id, procurement_id, item_name, suggested_brand, specifications, notes 
                FROM {TABLES['brand']}
                WHERE item_name IS NOT NULL
            """
            cur.execute(sql_demand)
            demands = cur.fetchall()

            logger.info("正在读取候选商品数据...")
            # 👉 [修改] 增加 detail_specs 和 fetch_status
            sql_sku = f"""
                SELECT procurement_id, sku, title, price, shop_name, sales, hot_info, detail_url, platform, item_name, detail_specs, fetch_status
                FROM {TABLES['sku']}
            """
            cur.execute(sql_sku)
            all_skus = cur.fetchall()
            logger.info(f"原始SKU数据加载完成: {len(all_skus)} 条")

        # 内存分组
        sku_map = {}
        for row in all_skus:
            pid = str(row[0])
            sku_item_name = str(row[9]) if row[9] else "未知"
            map_key = f"{pid}_{sku_item_name}"
            
            item = {
                'sku': row[1], 'title': row[2], 
                'price': float(row[3]) if row[3] else 0.0,
                'shop_name': row[4], 'sales': row[5], 'hot_info': row[6],
                'detail_url': row[7], 'platform': row[8],
                # 👉 [新增] 以下两行：
                'detail_specs': row[10] if len(row) > 10 and row[10] else None,
                'fetch_status': row[11] if len(row) > 11 and row[11] else 0
            }
            if map_key not in sku_map: sku_map[map_key] = []
            sku_map[map_key].append(item)

        # 组装任务
        for d in demands:
            brand_id = d[0]
            pid = str(d[1])
            demand_item_name = str(d[2])
            specs = str(d[4]) if d[4] else ""
            
            if brand_id in processed_ids: continue
            if brand_id in seen_in_this_run: continue
            seen_in_this_run.add(brand_id)
            
            unique_key = f"{pid}_{demand_item_name}"
            cands = sku_map.get(unique_key, [])
            
            if cands:
                groups.append({
                    'brand_id': brand_id,
                    'procurement_id': pid,
                    'demand': {
                        'item_name': demand_item_name,
                        'suggested_brand': d[3],
                        'specifications': specs,
                        'notes': d[5]
                    },
                    'candidates': cands
                })
        
        logger.info(f"任务组装完成，共生成 {len(groups)} 个待处理任务")
                
    except Exception as e:
        logger.error(f"数据加载出错: {e}")
    finally:
        if conn: conn.close()
        
    return groups