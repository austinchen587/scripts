# db_helper.py
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from config import DB_CONFIG
from logger_helper import logger

def get_pending_tasks():
    """
    获取任务逻辑：
    1. 筛选出符合条件的前 3 个项目 (procurement_id)
    2. 获取这 3 个项目下所有未爬取的商品 (item_name)
    """
    sql = """
    WITH sample_projects AS (
        SELECT sp.*, pp.selected_at
        FROM procurement_commodity_category sp
        JOIN procurement_purchasing pp ON sp.procurement_id = pp.procurement_id
        JOIN procurement_emall pe ON sp.procurement_id = pe.id
        WHERE jsonb_array_length(sp.items_data) > 0
          AND pp.is_selected = TRUE
          AND TO_TIMESTAMP(pe.quote_end_time, 'YYYY-MM-DD HH24:MI:SS') > CURRENT_TIMESTAMP
    ),
    -- 1. 找出所有待爬取的任务明细
    all_pending_tasks AS (
        SELECT 
            pcb.key_word, 
            pcb.search_platform, 
            sp.procurement_id,
            pcb.item_name,
            sp.selected_at
        FROM sample_projects sp
        CROSS JOIN LATERAL jsonb_array_elements(sp.items_data) as item
        LEFT JOIN procurement_commodity_brand pcb ON 
            pcb.procurement_id = sp.procurement_id AND 
            pcb.item_name = TRIM(BOTH '''' FROM TRIM(BOTH '[]' FROM COALESCE(item->>'商品名称', '')))
        WHERE NOT EXISTS (
            SELECT 1 FROM procurement_commodity_sku pcs 
            WHERE pcs.procurement_id = sp.procurement_id 
              AND pcs.item_name = pcb.item_name
        )
    ),
    -- 2. 锁定前 3 个项目
    target_projects AS (
        SELECT DISTINCT procurement_id, selected_at
        FROM all_pending_tasks
        ORDER BY selected_at DESC
        LIMIT 3
    )
    -- 3. 输出这 3 个项目下的所有商品
    SELECT t.key_word, t.search_platform, t.procurement_id, t.item_name
    FROM all_pending_tasks t
    JOIN target_projects tp ON t.procurement_id = tp.procurement_id
    ORDER BY t.selected_at DESC, t.procurement_id;
    """
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            return cur.fetchall()
    except Exception as e:
        print(f"DB Error in get_pending_tasks: {e}")
        return []
    finally:
        if conn: conn.close()

def save_skus_to_db(records):
    """Batch insert SKUs with item_name (Fixed Version)"""
    if not records:
        logger.info("--- [数据库] 没有数据需要入库 ---")
        return
    
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)

        # [新增] 打印正在入库
        logger.info(f"--- [数据库] 正在写入 {len(records)} 条数据... ---")
        
        sql = """
            INSERT INTO procurement_commodity_sku 
            (procurement_id, sku, platform, title, price, shop_name, sales, detail_url, hot_info, item_name)
            VALUES %s
            ON CONFLICT (procurement_id, title, platform) 
            DO UPDATE SET 
                price = EXCLUDED.price,
                sales = EXCLUDED.sales,
                updated_at = CURRENT_TIMESTAMP;
        """
        
        with conn.cursor() as cur:
            data = [(
                r['procurement_id'], r['sku'], r['platform'], r['title'],
                r['price'], r['shop_name'], r['sales'], r['detail_url'], r['hot_info'],
                r['item_name']
            ) for r in records]
            execute_values(cur, sql, data)
            conn.commit()

            # [新增] 打印成功
            logger.info("--- [数据库] 写入成功! ---")
            
    except Exception as e:
        if conn: conn.rollback()
        # 抛出异常以便 main.py 记录日志
        # 出错也要打印出来
        logger.error(f"--- [数据库] 写入失败: {e} ---")
        raise e
    finally:
        if conn: conn.close()