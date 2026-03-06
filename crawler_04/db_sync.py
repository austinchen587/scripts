# db_sync.py
import psycopg2
from psycopg2 import extras, sql
from psycopg2.extras import Json
from config import DB_CONFIG as LOCAL_DB_CONFIG
from logger_helper import logger

# ==========================================
# 配置区域
# ==========================================

# 1. 下载任务源 (云端: 用于获取任务、配置、商品分类等)
CLOUD_DB_CONFIG = {
    "host": "121.41.76.252",
    "port": "5432",
    "dbname": "austinchen587_db",
    "user": "austinchen587",
    "password": "austinchen587"
}

# 2. [新增] 回传目标源 (内网服务器: 用于汇聚爬取结果)
UPLOAD_DB_CONFIG = {
    "host": "192.168.10.24",
    "port": "5432",
    "dbname": "austinchen587_db",
    "user": "austinchen587",
    "password": "austinchen587"
}

# 需要下载同步的表
DOWNLOAD_TABLES = [
    "procurement_emall",
    "procurement_emall_category",
    "procurement_commodity_category",
    "procurement_commodity_brand",
    "procurement_purchasing" 
]

# 需要回传的表
UPLOAD_TABLE_NAME = "procurement_commodity_sku"

# ==========================================
# 工具函数
# ==========================================

def get_connection(config):
    return psycopg2.connect(**config)

def get_table_primary_key(conn, table_name):
    """获取表的主键字段名"""
    query = """
        SELECT a.attname
        FROM   pg_index i
        JOIN   pg_attribute a ON a.attrelid = i.indrelid
                             AND a.attnum = ANY(i.indkey)
        WHERE  i.indrelid = %s::regclass
        AND    i.indisprimary;
    """
    with conn.cursor() as cur:
        try:
            cur.execute(query, (table_name,))
            result = cur.fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"⚠️ 无法获取表 {table_name} 的主键: {e}")
            return None

def get_local_column_types(conn, table_name):
    """获取表字段类型，用于判断是否需要 JSON 转换"""
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
    """智能数据预处理：处理 JSON/Array 类型不匹配问题"""
    processed_rows = []
    for row in rows:
        new_row = []
        for i, val in enumerate(row):
            col_name = columns[i]
            target_type = type_map.get(col_name, '')

            if isinstance(val, list):
                if target_type in ('json', 'jsonb'):
                    new_row.append(Json(val))
                else:
                    new_row.append(val) 
            elif isinstance(val, dict):
                new_row.append(Json(val))
            else:
                new_row.append(val)
        processed_rows.append(tuple(new_row))
    return processed_rows

# ==========================================
# 功能 1: 下载同步 (Cloud -> Local)
# ==========================================
def sync_table_download(table_name):
    cloud_conn = None
    local_conn = None
    try:
        logger.info(f"⏳ [Download] 正在同步表: {table_name} ...")
        
        cloud_conn = get_connection(CLOUD_DB_CONFIG)
        local_conn = get_connection(LOCAL_DB_CONFIG)
        
        # 读取云端
        with cloud_conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(table_name)))
            rows = cur.fetchall()
            if not rows:
                logger.info(f"☁️ [Download] 云端表 {table_name} 无数据，跳过。")
                return
            columns = [desc[0] for desc in cur.description]
            logger.info(f"📥 [Download] 云端读取到 {len(rows)} 条数据，准备写入...")
        
        pk_column = get_table_primary_key(local_conn, table_name)
        if not pk_column:
            logger.error(f"❌ 本地表 {table_name} 无主键，跳过。")
            return

        local_types = get_local_column_types(local_conn, table_name)
        rows = preprocess_data(rows, columns, local_types)

        # 构建 Upsert SQL
        update_columns = [col for col in columns if col != pk_column]
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES %s ON CONFLICT ({}) DO UPDATE SET {}").format(
            sql.Identifier(table_name),
            sql.SQL(', ').join(map(sql.Identifier, columns)),
            sql.Identifier(pk_column),
            sql.SQL(', ').join([sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c)) for c in update_columns])
        )

        with local_conn.cursor() as cur:
            extras.execute_values(cur, insert_query, rows, page_size=100)
            local_conn.commit()
            
        logger.info(f"✅ [Download] 表 {table_name} 同步成功！记录数: {len(rows)}")

    except Exception as e:
        logger.error(f"💥 [Download] 同步失败: {e}")
        if local_conn: local_conn.rollback()
    finally:
        if cloud_conn: cloud_conn.close()
        if local_conn: local_conn.close()

# ==========================================
# [恢复] 功能 2: 回传同步 (Local -> Upload Server)
# ==========================================
def upload_sku_table():
    """将本地爬取的 SKU 数据回传到指定的内网服务器"""
    table_name = UPLOAD_TABLE_NAME
    local_conn = None
    upload_conn = None
    try:
        logger.info(f"📤 [Upload] 正在回传结果表: {table_name} 到内网服务器...")

        local_conn = get_connection(LOCAL_DB_CONFIG)
        # 使用独立的上传配置
        upload_conn = get_connection(UPLOAD_DB_CONFIG)

        # 1. 读取本地数据
        with local_conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(table_name)))
            rows = cur.fetchall()
            if not rows:
                logger.info(f"🏠 [Upload] 本地表 {table_name} 无数据，无需回传。")
                return
            columns = [desc[0] for desc in cur.description]
            logger.info(f"📦 [Upload] 本地读取到 {len(rows)} 条结果，准备上传...")

        # 2. 预处理数据 (适配上传服务器类型)
        server_types = get_local_column_types(upload_conn, table_name)
        rows = preprocess_data(rows, columns, server_types)

        # 3. 构建 Cloud Upsert SQL
        # 结果表的业务主键: (procurement_id, title, platform)
        conflict_target = sql.SQL("procurement_id, title, platform")
        
        # 排除 id 和 created_at，只更新业务字段
        exclude_cols = {'id', 'created_at'}
        update_columns = [col for col in columns if col not in exclude_cols]

        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES %s ON CONFLICT ({}) DO UPDATE SET {}").format(
            sql.Identifier(table_name),
            sql.SQL(', ').join(map(sql.Identifier, columns)),
            conflict_target,
            sql.SQL(', ').join([sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c)) for c in update_columns])
        )

        # 4. 写入目标服务器
        with upload_conn.cursor() as cur:
            extras.execute_values(cur, insert_query, rows, page_size=100)
            upload_conn.commit()
        
        logger.info(f"✅ [Upload] 结果回传成功！已同步 {len(rows)} 条数据到服务器。")

    except Exception as e:
        logger.error(f"💥 [Upload] 回传失败: {e}")
        if upload_conn: upload_conn.rollback()
    finally:
        if local_conn: local_conn.close()
        if upload_conn: upload_conn.close()

# ==========================================
# 统一入口
# ==========================================
def run_sync_download():
    """执行下载 (启动时调用)"""
    logger.info("============== [SYNC DOWNLOAD: CLOUD -> LOCAL] ==============")
    for table in DOWNLOAD_TABLES:
        sync_table_download(table)
    logger.info("=============================================================")

def run_sync_upload():
    """执行回传 (每轮任务结束后调用)"""
    logger.info("============== [SYNC UPLOAD: LOCAL -> 192.168.10.24] ========")
    upload_sku_table()
    logger.info("=============================================================")

if __name__ == "__main__":
    # 测试用
    run_sync_download()
    run_sync_upload()