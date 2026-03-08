import psycopg2
import json
from psycopg2.extras import RealDictCursor, execute_values
from config import DB_CONFIG
from logger_helper import logger

def _ensure_column_exists(conn, table_name, column_name, column_type):
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='{table_name}' AND column_name='{column_name}';
            """)
            if not cur.fetchone():
                logger.info(f"🔄 [数据库] 表 {table_name} 缺少 {column_name} 列，正在自动添加...")
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type};")
                conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"⚠️ 添加列失败: {e}")

def get_pending_tasks():
    # 修复说明：
    # 1. 严格使用你提供的 CTE 结构，保留 LIMIT 3 以确保只处理最新的 3 个项目。
    # 2. 使用 COALESCE(NULLIF(TRIM(pcb.key_word), ''), pcb.item_name) 确保优先提取最新关键词。
    
    sql = """
    WITH valid_projects AS (
        SELECT 
            sp.procurement_id, 
            sp.items_data, 
            pp.selected_at
        FROM procurement_commodity_category sp
        JOIN procurement_purchasing pp ON sp.procurement_id = pp.procurement_id
        JOIN procurement_emall pe ON sp.procurement_id = pe.id
        WHERE 
            pp.is_selected = TRUE
            AND TO_TIMESTAMP(pe.quote_end_time, 'YYYY-MM-DD HH24:MI:SS') > CURRENT_TIMESTAMP
            AND jsonb_array_length(sp.items_data) > 0
    ),
    all_pending_items AS (
        SELECT 
            pcb.id AS brand_id,
            -- 【核心修复】优先使用 pcb 表中人工修改后的最新关键词，若为空则用商品原名
            COALESCE(NULLIF(TRIM(pcb.key_word), ''), pcb.item_name) as key_word, 
            pcb.search_platform, 
            vp.procurement_id,
            pcb.item_name,
            vp.selected_at
        FROM valid_projects vp
        CROSS JOIN LATERAL jsonb_array_elements(vp.items_data) as item
        LEFT JOIN procurement_commodity_brand pcb ON 
            pcb.procurement_id = vp.procurement_id AND 
            pcb.item_name = BTRIM(COALESCE(item->>'商品名称', ''), '[]''" ')
        WHERE 
            (pcb.key_word IS NOT NULL OR pcb.item_name IS NOT NULL)
            -- [判定 1] 排除非 retry 状态的已处理结果
            AND NOT EXISTS (
                SELECT 1 
                FROM procurement_commodity_result pcr 
                WHERE pcr.brand_id = pcb.id
                  AND (pcr.status IS NULL OR pcr.status != 'retry')
            )
            -- [判定 2] 排除已抓取过 SKU 的任务（除非已在 Retry-Cleanup 中被物理删除）
            AND NOT EXISTS (
                SELECT 1
                FROM procurement_commodity_sku pcs
                WHERE pcs.brand_id = pcb.id
            )
    ),
    target_projects AS (
        SELECT DISTINCT procurement_id, selected_at
        FROM all_pending_items
        ORDER BY selected_at DESC
        LIMIT 3
    )
    SELECT t.brand_id, t.key_word, t.search_platform, t.procurement_id, t.item_name
    FROM all_pending_items t
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
        logger.error(f"获取任务失败: {e}")
        return []
    finally:
        if conn: conn.close()

def save_skus_to_db(records):
    """保存抓取成功的商品数据 (保持不变)"""
    if not records:
        return
    
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logger.info(f"--- [数据库] 正在写入 {len(records)} 条 SKU 数据... ---")
        
        create_sql = """
            CREATE TABLE IF NOT EXISTS procurement_commodity_sku (
                id SERIAL PRIMARY KEY,
                brand_id INTEGER,
                procurement_id TEXT,
                sku TEXT,
                platform TEXT,
                title TEXT,
                price NUMERIC,
                shop_name TEXT,
                sales TEXT,
                detail_url TEXT,
                hot_info TEXT,
                item_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT unique_sku_record UNIQUE (procurement_id, title, platform)
            );
        """
        
        with conn.cursor() as cur:
            cur.execute(create_sql)
            _ensure_column_exists(conn, 'procurement_commodity_sku', 'brand_id', 'INTEGER')
            # 👉 [新增] 确保存在详情页参数列和状态列
            _ensure_column_exists(conn, 'procurement_commodity_sku', 'detail_specs', 'TEXT')
            _ensure_column_exists(conn, 'procurement_commodity_sku', 'fetch_status', 'INTEGER DEFAULT 0')
            
            insert_sql = """
                INSERT INTO procurement_commodity_sku 
                (brand_id, procurement_id, sku, platform, title, price, shop_name, sales, detail_url, hot_info, item_name)
                VALUES %s
                ON CONFLICT (procurement_id, title, platform) 
                DO UPDATE SET 
                    brand_id = EXCLUDED.brand_id,
                    price = EXCLUDED.price,
                    sales = EXCLUDED.sales,
                    updated_at = CURRENT_TIMESTAMP;
            """
            
            data = [(
                r.get('brand_id'), r['procurement_id'], r['sku'], r['platform'], r['title'],
                r['price'], r['shop_name'], r['sales'], r['detail_url'], r['hot_info'],
                r['item_name']
            ) for r in records]
            
            execute_values(cur, insert_sql, data)
            conn.commit()
            logger.info(f"--- [数据库] SKU 写入完成 ---")
            
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"--- [数据库] SKU 写入失败: {e} ---")
        raise e
    finally:
        if conn: conn.close()

# [新增功能] 成功后清理重试占位符
def clear_retry_placeholder(brand_id):
    """如果抓取成功，清理 Result 表中的 retry 占位，让 AI 能够重新生成推荐"""
    if not brand_id: return
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM procurement_commodity_result WHERE brand_id = %s;", (brand_id,))
            conn.commit()
    except Exception as e:
        logger.error(f"清理占位符失败: {e}")
    finally:
        if conn: conn.close()

def save_failed_task(task_info):
    """记录抓取失败或被风控拦截的任务，支持动态 status 更新"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        brand_id = task_info.get('brand_id')
        item_name = task_info['item_name']
        
        # 👉 [核心修改 1] 动态获取状态，默认是 failed，但如果是风控拦截传过来的就是 retry
        status = task_info.get('status', 'failed')
        
        # 根据状态定制提示信息
        if status == 'retry':
            logger.warning(f"🛡️ [数据库] 记录风控拦截，挂起重试: Item={item_name}, BrandID={brand_id}")
            reason_text = "系统提示：遭遇平台风控拦截，已加入重试队列等待重新抓取"
            model_used = "System_Crawler_Blocked"
            spec_text = "风控拦截延后抓取"
        else:
            logger.warning(f"🚫 [数据库] 全网无结果，写入占位: Item={item_name}, BrandID={brand_id}")
            reason_text = "系统提示：未找到匹配的商品价格，请手工审核"
            model_used = "System_Crawler_Fail"
            spec_text = "自动抓取无结果"
            
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS procurement_commodity_result (
                    id SERIAL PRIMARY KEY,
                    brand_id INTEGER,
                    procurement_id VARCHAR(50),
                    item_name VARCHAR(255),
                    specifications TEXT,
                    selected_suppliers JSONB,
                    selection_reason TEXT,
                    model_used VARCHAR(100),
                    status VARCHAR(20) DEFAULT 'completed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            _ensure_column_exists(conn, 'procurement_commodity_result', 'status', "VARCHAR(20) DEFAULT 'completed'")
            
            try:
                cur.execute("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'unique_result_brand_id') THEN
                            ALTER TABLE procurement_commodity_result ADD CONSTRAINT unique_result_brand_id UNIQUE (brand_id);
                        END IF;
                    END
                    $$;
                """)
            except:
                conn.rollback() 
            
            error_data = [{
                "rank": 0,
                "sku": "NO_RESULT",
                "shop": "系统自动",
                "price": 0,
                "reason": reason_text,
                "platform": "SYSTEM"
            }]
            
            # 👉 [核心修改 2] 确保这里插入的是动态传入的 status
            sql = """
                INSERT INTO procurement_commodity_result 
                (brand_id, procurement_id, item_name, specifications, selected_suppliers, selection_reason, model_used, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (brand_id) DO UPDATE SET 
                    specifications = EXCLUDED.specifications,
                    selected_suppliers = EXCLUDED.selected_suppliers,
                    selection_reason = EXCLUDED.selection_reason,
                    model_used = EXCLUDED.model_used,
                    status = EXCLUDED.status;
            """
            
            cur.execute(sql, (
                brand_id,
                task_info['procurement_id'],
                item_name,
                spec_text, 
                json.dumps(error_data, ensure_ascii=False), 
                reason_text,     
                model_used,
                status # <--- 这里非常关键，将状态准确写入数据库
            ))
            conn.commit()
            
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"记录失败/重试Result出错: {e}")
    finally:
        if conn: conn.close()

def get_pending_detail_tasks():
    """[新增] 获取 AI 指定要回采详情的 SKU（包含需求规格，用于匹配点击）"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 联合查询，把 result 表里的 specifications 拿出来给爬虫做匹配参考
            cur.execute("""
                SELECT s.procurement_id, s.sku, s.platform, s.detail_url, s.item_name, s.brand_id, r.specifications
                FROM procurement_commodity_sku s
                JOIN procurement_commodity_result r ON s.brand_id = r.brand_id
                WHERE s.fetch_status = 1 
                LIMIT 5;
            """)
            return cur.fetchall()
    except Exception as e:
        logger.error(f"获取详情页任务失败: {e}")
        return []
    finally:
        if conn: conn.close()

def update_sku_detail(procurement_id, sku, platform, specs_data):
    """[新增] 保存详情数据，并敲钟唤醒 AI"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        specs_json_str = json.dumps(specs_data, ensure_ascii=False)
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE procurement_commodity_sku 
                SET detail_specs = %s, fetch_status = 2, updated_at = CURRENT_TIMESTAMP
                WHERE procurement_id = %s AND sku = %s AND platform = %s;
            """, (specs_json_str, procurement_id, sku, platform))
            
            # 👉 [核心] 敲钟！唤醒 result_05 端的 AI
            cur.execute("NOTIFY local_sku_channel, 'detail_ready';")
            conn.commit()
    except Exception as e:
        logger.error(f"更新 SKU 详情失败: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()