# data_loader.py
from db_manager import get_connection
from config import TABLES
from logger import logger

def fetch_single_task(brand_id):
    """
    👉 [正规军架构] 根据 Redis 传来的 brand_id，查询云端已同步的 brand 表和 sku 表
    """
    conn = get_connection()
    if not conn: return None
    
    group = None
    try:
        with conn.cursor() as cur:
            # 1. 放心大胆地查 demand 表 (Django 已经帮我们把规格同步过来了)
            sql_demand = f"""
                SELECT procurement_id, item_name, specifications 
                FROM {TABLES['brand']}
                WHERE id = %s
            """
            cur.execute(sql_demand, (brand_id,))
            d = cur.fetchone()
            
            if not d:
                logger.warning(f"云端找不到 brand_id={brand_id} 的需求记录。")
                return None
                
            pid = str(d[0])
            demand_item_name = str(d[1])
            specs = str(d[2]) if d[2] else ""

            # 2. 查询对应的 SKU
            sql_sku = f"""
                SELECT procurement_id, sku, title, price, shop_name, sales, hot_info, detail_url, platform
                FROM {TABLES['sku']}
                WHERE brand_id = %s
            """
            cur.execute(sql_sku, (brand_id,))
            all_skus = cur.fetchall()

            cands = []
            for row in all_skus:
                cands.append({
                    'sku': row[1], 'title': row[2], 
                    'price': float(row[3]) if row[3] else 0.0,
                    'shop_name': row[4], 'sales': row[5], 'hot_info': row[6],
                    'detail_url': row[7], 'platform': row[8]
                })

            group = {
                'brand_id': brand_id,
                'procurement_id': pid,
                'demand': {
                    'item_name': demand_item_name,
                    'specifications': specs
                },
                'candidates': cands
            }
                
    except Exception as e:
        logger.error(f"数据加载出错: {e}")
    finally:
        if conn: conn.close()
        
    return group