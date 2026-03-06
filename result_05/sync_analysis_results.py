import sys
import psycopg2
from psycopg2.extras import DictCursor, execute_values
import logging
import time
import io
import json

# ================= 配置区域 =================

# 1. 云端数据库 (目标)
CLOUD_DB_CONFIG = {
    'host': '121.41.128.53',
    'port': '5432',
    'database': 'austinchen587_db',
    'user': 'austinchen587',
    'password': 'austinchen587',
    'connect_timeout': 10
}

# 2. 本地数据库 (源)
LOCAL_DB_CONFIG = {
    'host': 'localhost',
    'port': '5432',
    'database': 'austinchen587_db',
    'user': 'austinchen587',
    'password': 'austinchen587',
}

# 3. 目标表名
TABLE_NAME = 'procurement_commodity_result'
# 用于去重的唯一键 (逻辑上一个 brand_id 对应一个选品结果)
UNIQUE_KEY = 'brand_id'

# ===========================================

# 强制标准输出使用 UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [SYNC] - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AnalysisSync")

class AnalysisResultSyncer:
    def __init__(self):
        self.local_config = LOCAL_DB_CONFIG
        self.cloud_config = CLOUD_DB_CONFIG

    def get_connection(self, config, name="DB"):
        try:
            conn = psycopg2.connect(**config)
            return conn
        except Exception as e:
            logger.error(f"❌ {name} 连接失败: {e}")
            raise

    def ensure_cloud_table_exists(self, cloud_conn):
        """
        在云端初始化表结构，并确保 brand_id 有唯一约束以便 Upsert
        """
        logger.info("🛠️  检查云端表结构...")
        create_sql = f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id SERIAL PRIMARY KEY,
                brand_id INTEGER,
                procurement_id VARCHAR(50) NOT NULL,
                item_name VARCHAR(255),
                specifications TEXT,
                selected_suppliers JSONB,
                selection_reason TEXT,
                model_used VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """
        
        # 必须确保 brand_id 是唯一的，才能使用 ON CONFLICT (brand_id)
        # 尝试添加唯一约束，如果已存在则忽略
        add_constraint_sql = f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'unique_brand_id_constraint'
                ) THEN
                    ALTER TABLE {TABLE_NAME} ADD CONSTRAINT unique_brand_id_constraint UNIQUE ({UNIQUE_KEY});
                END IF;
            END
            $$;
        """

        with cloud_conn.cursor() as cur:
            # 1. 建表
            cur.execute(create_sql)
            # 2. 加约束
            cur.execute(add_constraint_sql)
        cloud_conn.commit()
        logger.info("✅ 云端表结构验证完成 (已确保唯一约束)")

    def prepare_data_for_upload(self, row, columns):
        """
        将 Python 对象转换为 SQL 兼容格式，特别是 JSON 处理
        """
        values = []
        for col in columns:
            val = row[col]
            # 如果是字典或列表，序列化为 JSON 字符串
            if isinstance(val, (dict, list)):
                values.append(json.dumps(val, ensure_ascii=False))
            else:
                values.append(val)
        return tuple(values)

    def run(self):
        logger.info(f"🚀 [开始同步] {TABLE_NAME}")
        local_conn = None
        cloud_conn = None

        try:
            local_conn = self.get_connection(self.local_config, "本地")
            cloud_conn = self.get_connection(self.cloud_config, "云端")
            self.ensure_cloud_table_exists(cloud_conn)

            local_cur = local_conn.cursor(cursor_factory=DictCursor)
            cloud_cur = cloud_conn.cursor()

            # 【核心修改】：只读取 sync_status = 0 的全新结果
            logger.info("📦 正在读取未同步的本地分析结果...")
            local_cur.execute(f"SELECT * FROM {TABLE_NAME} WHERE sync_status = 0")
            rows = local_cur.fetchall()
            total_rows = len(rows)

            if total_rows == 0:
                logger.info("⚠️ 本地暂无需要同步的新数据")
                return
                
            logger.info(f"📊 发现 {total_rows} 条新纪录，准备上传...")

            # 动态构建 Upsert SQL，【必须排除 sync_status】，因为云端表没有这个字段
            columns = [desc[0] for desc in local_cur.description if desc[0] != 'sync_status']
            columns_str = ', '.join(columns)
            
            exclude_update = ['id', 'created_at', UNIQUE_KEY]
            update_assignments = [f"{col} = EXCLUDED.{col}" for col in columns if col not in exclude_update]
            update_stmt = ', '.join(update_assignments)

            insert_sql = f"""
                INSERT INTO {TABLE_NAME} ({columns_str}) 
                VALUES %s
                ON CONFLICT ({UNIQUE_KEY}) 
                DO UPDATE SET {update_stmt};
            """

            data_values = [self.prepare_data_for_upload(row, columns) for row in rows]

            # 执行批量上传
            logger.info("☁️  正在上传到云端...")
            start_time = time.time()
            execute_values(cloud_cur, insert_sql, data_values, page_size=50)
            cloud_conn.commit()
            
            # 【完美闭环】：上传成功后，将这批数据的 sync_status 改为 1，永久封印，绝不倒灌！
            uploaded_ids = tuple(row['brand_id'] for row in rows)
            if uploaded_ids:
                with local_conn.cursor() as l_cur:
                    l_cur.execute(f"UPDATE {TABLE_NAME} SET sync_status = 1 WHERE brand_id IN %s", (uploaded_ids,))
                local_conn.commit()
            
            duration = time.time() - start_time
            logger.info(f"✅ 同步成功并已锁定本地缓存！耗时: {duration:.2f}秒")

        except Exception as e:
            logger.error(f"❌ 同步过程中发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            if cloud_conn: cloud_conn.rollback()
        finally:
            if local_conn: local_conn.close()
            if cloud_conn: cloud_conn.close()

if __name__ == '__main__':
    syncer = AnalysisResultSyncer()
    syncer.run()