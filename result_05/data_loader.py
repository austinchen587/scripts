# data_loader.py
from db_manager import get_connection
from config import TABLES
from logger import logger

def fetch_single_task(brand_id):
    """
    👉 获取全量字段数据，为 AI 提供充足的算账依据和商务风险评估依据
    """
    conn = get_connection()
    if not conn: return None
    
    group = None
    try:
        with conn.cursor() as cur:
            # 动态获取全量列数据
            sql_demand = f"SELECT * FROM {TABLES['brand']} WHERE id = %s"
            cur.execute(sql_demand, (brand_id,))
            d_row = cur.fetchone()
            
            if not d_row:
                logger.warning(f"云端找不到 brand_id={brand_id} 的需求记录。")
                return None
                
            # 组合成字典，包含所有的 notes, business_reqs, price_display 等
            columns = [col[0] for col in cur.description]
            demand_data = dict(zip(columns, d_row))
            
            pid = str(demand_data.get('procurement_id', ''))
            
            # 查询对应的 SKU
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
                'demand': demand_data,
                'candidates': cands
            }

    except Exception as e:
        logger.error(f"数据加载出错: {e}")
    finally:
        if conn: conn.close()
        
    return group