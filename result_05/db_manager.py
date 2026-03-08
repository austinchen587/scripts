import psycopg2
import json
from datetime import datetime
from config import DB_CONFIG, TABLES
from logger import logger  # 引入日志

def get_connection():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return None

def init_result_table():
    conn = get_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLES['result']} (
                id SERIAL PRIMARY KEY,
                brand_id INTEGER,
                procurement_id VARCHAR(50) NOT NULL,
                item_name VARCHAR(255),
                specifications TEXT,
                selected_suppliers JSONB,
                selection_reason TEXT,
                model_used VARCHAR(100),
                status VARCHAR(20) DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_res_brand_id ON {TABLES['result']} (brand_id);
            CREATE INDEX IF NOT EXISTS idx_res_proc_id ON {TABLES['result']} (procurement_id);
            """)
            try:
                # 动态追加必要字段，并设置 sync_status=1 锁定老数据防止倒灌
                cur.execute(f"ALTER TABLE {TABLES['result']} ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'completed'")
                cur.execute(f"ALTER TABLE {TABLES['result']} ADD COLUMN IF NOT EXISTS sync_status INTEGER DEFAULT 0")
                cur.execute(f"UPDATE {TABLES['result']} SET sync_status = 1 WHERE sync_status IS NULL")
            except: pass
        conn.commit()
    except Exception as e:
        logger.error(f"初始化表结构失败: {e}")
    finally:
        conn.close()

# 修改原有函数：增加 waiting_detail 的排除
def get_processed_brand_ids():
    conn = get_connection()
    if not conn: return set()
    try:
        with conn.cursor() as cur:
            # 👉 [重点修改]: 原本是 status != 'retry'，现在加上 waiting_detail
            cur.execute(f"SELECT brand_id FROM {TABLES['result']} WHERE brand_id IS NOT NULL AND status NOT IN ('retry', 'waiting_detail')")
            return {row[0] for row in cur.fetchall()}
    except Exception as e:
        logger.error(f"查询已处理ID失败: {e}")
        return set()
    finally:
        conn.close()

def save_analysis_result(data):
    conn = get_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            status = data.get('status', 'completed')
            
            # 插入或更新，并将 sync_status 设为 0，代表这是一条【需要上传的新数据】
            sql = f"""
            INSERT INTO {TABLES['result']} 
            (brand_id, procurement_id, item_name, specifications, selected_suppliers, selection_reason, model_used, status, created_at, sync_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
            ON CONFLICT (brand_id) DO UPDATE SET 
                specifications = EXCLUDED.specifications,
                selected_suppliers = EXCLUDED.selected_suppliers,
                selection_reason = EXCLUDED.selection_reason,
                model_used = EXCLUDED.model_used,
                status = EXCLUDED.status,
                created_at = EXCLUDED.created_at,
                sync_status = 0;
            """
            
            cur.execute(sql, (
                data['brand_id'],
                str(data['procurement_id']), 
                data['item_name'], 
                data.get('specifications', ''),
                json.dumps(data['selected_suppliers'], ensure_ascii=False),
                data['reason'], 
                data['model'], 
                status,
                datetime.now()
            ))
        conn.commit()
        logger.info(f"✅ 结果已入库 (状态: {status}): 需求ID {data['brand_id']}")
    except Exception as e:
        logger.error(f"保存结果失败 [BrandID: {data.get('brand_id')}]: {e}")
        if conn: conn.rollback()
    finally:
        conn.close()

# 👉 [新增] 标记商品需要爬虫去看详情
def mark_skus_for_detail(procurement_id, skus_list):
    conn = get_connection()
    if not conn or not skus_list: return
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE {TABLES['sku']} SET fetch_status = 1 WHERE procurement_id = %s AND sku = ANY(%s)", (str(procurement_id), list(skus_list)))
        conn.commit()
    except Exception as e:
        logger.error(f"更新 SKU 详情状态失败: {e}")
    finally:
        conn.close()