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
            # 👉 确保表结构包含 server_ip
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLES['result']} (
                id SERIAL PRIMARY KEY,
                brand_id INTEGER,
                server_ip VARCHAR(50), 
                procurement_id VARCHAR(50) NOT NULL,
                item_name VARCHAR(255),
                specifications TEXT,
                selected_suppliers JSONB,
                selection_reason TEXT,
                model_used VARCHAR(100),
                status VARCHAR(20) DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # 👉 建立联合唯一约束，保证多服务器不串号
            cur.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'unique_brand_server_ai') THEN
                    ALTER TABLE {TABLES['result']} ADD CONSTRAINT unique_brand_server_ai UNIQUE (brand_id, server_ip);
                END IF;
            END
            $$;
            """)
        conn.commit()
    except Exception as e:
        logger.error(f"初始化表结构失败: {e}")
    finally:
        conn.close()

# 修改原有函数：增加 ai_processing 和 waiting_detail 的排除
def get_processed_brand_ids():
    conn = get_connection()
    if not conn: return set()
    try:
        with conn.cursor() as cur:
            # 👉 [终极修复]: 把 'ai_processing' 也加进来！
            # 意思是：这三种状态都不算“已完成”，AI 都得去接单处理！
            cur.execute(f"SELECT brand_id FROM {TABLES['result']} WHERE brand_id IS NOT NULL AND status NOT IN ('retry', 'waiting_detail', 'ai_processing')")
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
            server_ip = data.get('server_ip', 'unknown')
            
            # 👉 [修改] 插入时带上 server_ip，且不再使用 sync_status
            sql = f"""
            INSERT INTO {TABLES['result']} 
            (brand_id, server_ip, procurement_id, item_name, specifications, selected_suppliers, selection_reason, model_used, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (brand_id, server_ip) DO UPDATE SET 
                specifications = EXCLUDED.specifications,
                selected_suppliers = EXCLUDED.selected_suppliers,
                selection_reason = EXCLUDED.selection_reason,
                model_used = EXCLUDED.model_used,
                status = EXCLUDED.status,
                updated_at = CURRENT_TIMESTAMP;
            """
            
            cur.execute(sql, (
                data['brand_id'],
                server_ip,
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
        logger.info(f"✅ 结果已入库 (状态: {status}): 需求ID {data['brand_id']} (归属: {server_ip})")
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