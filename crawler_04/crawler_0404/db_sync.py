# db_sync.py
import psycopg2
from psycopg2 import extras, sql
from psycopg2.extras import Json
from config import DB_CONFIG as LOCAL_DB_CONFIG
from logger_helper import logger

# ================= 配置区域 =================

# 1. 下载任务源 (云端)
CLOUD_DB_CONFIG = {
    "host": "127.0.0.1",
    "port": "5432",
    "dbname": "austinchen587_db",
    "user": "austinchen587",
    "password": "austinchen587"
}

# 2. 回传目标 (内网)
UPLOAD_DB_CONFIG = {
    "host": "localhost",
    "port": "5432",
    "dbname": "austinchen587_db",
    "user": "austinchen587",
    "password": "austinchen587"
}

# 下载表清单
DOWNLOAD_TABLES = [
    "procurement_emall",
    "procurement_emall_category",
    "procurement_commodity_category",
    "procurement_commodity_brand",
    "procurement_purchasing",
    "procurement_commodity_result"  # 👈 新增这一行，用于同步 status='retry' 的状态
]

# 上传表
UPLOAD_TABLE_NAME = "procurement_commodity_sku"

# ================= 工具函数 =================

def get_connection(config):
    return psycopg2.connect(**config)

def get_local_column_types(conn, table_name):
    query = """
        SELECT column_name, udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
    """
    types_map = {}
    with conn.cursor() as cur:
        cur.execute(query, (table_name,))
        results = cur.fetchall()
        for col, udt in results:
            types_map[col] = udt
    return types_map

def preprocess_data(rows, columns, type_map):
    processed_rows = []
    for row in rows:
        new_row = []
        for i, val in enumerate(row):
            col_name = columns[i]
            target_type = type_map.get(col_name, '')
            if isinstance(val, (list, dict)):
                if target_type in ('json', 'jsonb'):
                    new_row.append(Json(val))
                else:
                    new_row.append(val)
            else:
                new_row.append(val)
        processed_rows.append(tuple(new_row))
    return processed_rows

def ensure_primary_key(conn, table_name, pk_column='id'):
    """
    【安全核心】检查本地表是否有主键，如果没有，安全地添加主键。
    这是为了让 ON CONFLICT 指令生效，避免报错。
    """
    check_pk_sql = """
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_name = %s AND constraint_type = 'PRIMARY KEY';
    """
    with conn.cursor() as cur:
        cur.execute(check_pk_sql, (table_name,))
        if not cur.fetchone():
            logger.info(f"🛠️ [Safe] 检测到本地表 {table_name} 缺少主键，正在安全修复...")
            try:
                # 尝试将 id 设为主键
                cur.execute(sql.SQL("ALTER TABLE {} ADD PRIMARY KEY ({})").format(
                    sql.Identifier(table_name),
                    sql.Identifier(pk_column)
                ))
                conn.commit()
                logger.info(f"✅ [Safe] 表 {table_name} 主键修复成功！")
            except Exception as e:
                conn.rollback()
                logger.warning(f"⚠️ [Safe] 无法自动添加主键 (可能是重复数据导致): {e}")
                logger.warning("   -> 将尝试使用普通插入模式，可能会略慢但在安全范围内。")

# ================= 核心功能 1: 安全下载 (Safe Sync) =================

def sync_table_download(table_name):
    """
    爬虫系统专用下载逻辑：基于 3 天时间窗口增量同步
    """
    cloud_conn = None
    local_conn = None
    try:
        cloud_conn = get_connection(CLOUD_DB_CONFIG)
        local_conn = get_connection(LOCAL_DB_CONFIG)
        
        # 1. 确定业务主键 
        PK_MAP = {
            "procurement_commodity_category": "procurement_id", 
            "procurement_commodity_result": "brand_id",         
            "procurement_purchasing": "procurement_id"
        }
        pk_col = PK_MAP.get(table_name)
        
        with cloud_conn.cursor() as cur:
            # 获取云端表结构，探测可用字段
            cur.execute(sql.SQL("SELECT * FROM {} LIMIT 0").format(sql.Identifier(table_name)))
            columns = [desc[0] for desc in cur.description]
            
            if not pk_col:
                pk_col = 'id' if 'id' in columns else columns[0]
            
            # 2. 【核心省流逻辑】只抓取近 3 天有变动的数据
            time_condition = ""
            if 'updated_at' in columns:
                time_condition = "WHERE updated_at >= NOW() - INTERVAL '3 days'"
                logger.info(f"💰 [省流模式] 爬虫仅拉取表 {table_name} 近 3 天内变动的数据")
            elif 'created_at' in columns:
                time_condition = "WHERE created_at >= NOW() - INTERVAL '3 days'"
                logger.info(f"💰 [省流模式] 爬虫仅拉取表 {table_name} 近 3 天内新增的数据")
            
            query_str = f"SELECT * FROM {table_name} {time_condition}"
            cur.execute(query_str)
            rows = cur.fetchall()
            
            if not rows:
                logger.info(f"✅ [Sync] 表 {table_name} 无新任务下发，跳过")
                return

        # 3. 数据类型预处理
        local_types = get_local_column_types(local_conn, table_name)
        rows = preprocess_data(rows, columns, local_types)

        if pk_col not in columns:
            pk_col = columns[0]
        pk_idx = columns.index(pk_col)
        cloud_pk_values = tuple(row[pk_idx] for row in rows)

        # 4. 手动执行 Upsert (覆盖本地旧数据)
        with local_conn.cursor() as cur:
            if cloud_pk_values:
                delete_query = sql.SQL("DELETE FROM {} WHERE {} IN %s").format(
                    sql.Identifier(table_name),
                    sql.Identifier(pk_col)
                )
                cur.execute(delete_query, (cloud_pk_values,))
            
            insert_query = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
                sql.Identifier(table_name),
                sql.SQL(', ').join(map(sql.Identifier, columns))
            )
            from psycopg2 import extras
            extras.execute_values(cur, insert_query, rows, page_size=100)
            
            local_conn.commit()
            logger.info(f"⬇️ [Sync] 爬虫更新本地表 {table_name} 成功 (同步了 {len(rows)} 条近期数据)")

    except Exception as e:
        logger.error(f"❌ [Sync] 爬虫下载失败 {table_name}: {e}")
        if local_conn: local_conn.rollback()
    finally:
        if cloud_conn: cloud_conn.close()
        if local_conn: local_conn.close()

# ================= 核心功能 2: 回传 (保持不变) =================

def upload_sku_table():
    local_conn = None
    upload_conn = None
    try:
        local_conn = get_connection(LOCAL_DB_CONFIG)
        upload_conn = get_connection(UPLOAD_DB_CONFIG)

        # 0. 确保远程表存在
        create_sql = sql.SQL("""
            CREATE TABLE IF NOT EXISTS {} (
                id SERIAL PRIMARY KEY,
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
                CONSTRAINT {} UNIQUE (procurement_id, title, platform)
            );
        """).format(
            sql.Identifier(UPLOAD_TABLE_NAME),
            sql.Identifier(f"unique_{UPLOAD_TABLE_NAME}_constraint")
        )

        with upload_conn.cursor() as cur:
            cur.execute(create_sql)
            upload_conn.commit()

        # 1. 读取本地数据
        with local_conn.cursor() as cur:
            try:
                cur.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(UPLOAD_TABLE_NAME)))
            except psycopg2.errors.UndefinedTable:
                logger.warning(f"🏠 [Upload] 本地结果表 {UPLOAD_TABLE_NAME} 尚未创建，跳过回传。")
                local_conn.rollback()
                return

            rows = cur.fetchall()
            if not rows: return
            columns = [desc[0] for desc in cur.description]

        # 2. 上传数据
        server_types = get_local_column_types(upload_conn, UPLOAD_TABLE_NAME)
        rows = preprocess_data(rows, columns, server_types)

        conflict_target = sql.SQL("procurement_id, title, platform")
        exclude_cols = {'id', 'created_at'}
        update_cols = [c for c in columns if c not in exclude_cols]

        query = sql.SQL("INSERT INTO {} ({}) VALUES %s ON CONFLICT ({}) DO UPDATE SET {}").format(
            sql.Identifier(UPLOAD_TABLE_NAME),
            sql.SQL(', ').join(map(sql.Identifier, columns)),
            conflict_target,
            sql.SQL(', ').join([sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c)) for c in update_cols])
        )

        with upload_conn.cursor() as cur:
            extras.execute_values(cur, query, rows, page_size=100)
            upload_conn.commit()
        
        logger.info(f"⬆️ [Sync] 结果回传成功 ({len(rows)}条)")

    except Exception as e:
        logger.error(f"❌ [Sync] 回传失败: {e}")
    finally:
        if local_conn: local_conn.close()
        if upload_conn: upload_conn.close()

# ================= 入口函数 =================

def run_sync_download():
    logger.info("--- [同步] 开始下载任务配置 (安全增量模式) ---")
    for table in DOWNLOAD_TABLES:
        sync_table_download(table)
    logger.info("--- [同步] 下载完成 ---")

def run_sync_upload():
    logger.info("--- [同步] 开始回传爬取结果 ---")
    upload_sku_table()


def cleanup_local_retry_cache():
    """
    [新增] 清理本地重试任务的缓存
    逻辑：查找本地 Result 表中 status='retry' 的任务，并删除对应的 SKU 数据
    """
    local_conn = None
    try:
        local_conn = get_connection(LOCAL_DB_CONFIG)
        with local_conn.cursor() as cur:
            # 1. 查找所有标记为 retry 的 brand_id 及其对应的 procurement_id
            query = """
                SELECT r.brand_id, b.procurement_id 
                FROM procurement_commodity_result r
                JOIN procurement_commodity_brand b ON r.brand_id = b.id
                WHERE r.status = 'retry'
            """
            cur.execute(query)
            retry_tasks = cur.fetchall()

            if not retry_tasks:
                return

            logger.info(f"🔄 [Retry-Cleanup] 发现 {len(retry_tasks)} 个重试任务，正在清理本地旧数据...")

            for b_id, p_id in retry_tasks:
                # 2. 删除本地对应的 SKU 数据 (删除后，db_helper.py 的 NOT EXISTS 逻辑才会让任务重新出现)
                cur.execute("DELETE FROM procurement_commodity_sku WHERE procurement_id = %s", (str(p_id),))
                # 3. 删除本地结果表中的 retry 记录，防止 AI 引擎跳过
                cur.execute("DELETE FROM procurement_commodity_result WHERE brand_id = %s", (b_id,))
            
            local_conn.commit()
            logger.info(f"✅ [Retry-Cleanup] 清理完成，{len(retry_tasks)} 个任务已重置为待抓取状态。")

    except Exception as e:
        logger.error(f"❌ [Retry-Cleanup] 清理失败: {e}")
        if local_conn: local_conn.rollback()
    finally:
        if local_conn: local_conn.close()