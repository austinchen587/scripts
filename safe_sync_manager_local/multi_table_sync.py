import os
import sys
import psycopg2
from psycopg2.extras import DictCursor
import logging
from datetime import datetime
import time

# 修复Windows控制台编码问题
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('multi_table_sync.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class MultiTableSyncer:
    def __init__(self):
        # 🎯 云端数据库配置 (只读提取)
        self.cloud_config = {
            'host': '121.41.128.53',  # 更新为你指定的云端IP
            'port': '5432',
            'database': 'austinchen587_db',
            'user': 'austinchen587',
            'password': 'austinchen587',
            'connect_timeout': 10
        }
        
        # 🎯 本地数据库配置 (安全写入)
        self.local_config = {
            'host': 'localhost',
            'port': '5432',
            'database': 'austinchen587_db',
            'user': 'austinchen587',
            'password': 'austinchen587',
            'connect_timeout': 10
        }
        
        # 🎯 需要同步的表单矩阵
        self.target_tables = [
            'procurement_emall',
            'procurement_emall_category',
            'procurement_commodity_category'
        ]
        
    def connect_databases(self):
        """建立双向连接"""
        cloud_conn = psycopg2.connect(**self.cloud_config)
        cloud_conn.autocommit = False
        cloud_cur = cloud_conn.cursor(cursor_factory=DictCursor)
        
        local_conn = psycopg2.connect(**self.local_config)
        local_conn.autocommit = False
        local_cur = local_conn.cursor()
        
        return cloud_conn, cloud_cur, local_conn, local_cur

    def sync_single_table(self, table_name, cloud_conn, cloud_cur, local_conn, local_cur):
        """同步单张表的核心逻辑 (滑动窗口安全模式)"""
        start_time = time.time()
        logger.info(f"\n" + "="*50)
        logger.info(f"🚀 正在处理表格: {table_name}")
        logger.info("="*50)

        try:
            # 1. 获取表结构 (字段名)
            cloud_cur.execute(f"SELECT * FROM {table_name} LIMIT 0")
            column_names = [desc[0] for desc in cloud_cur.description]
            columns_sql = ', '.join(column_names)
            placeholders = ', '.join(['%s'] * len(column_names))

            # 2. 构建滑动窗口查询 (强力比对模式)
            # 不再单纯依赖 ID 大小过滤，而是拉取云端最近 5000 条数据
            # 这样即便本地 ID 虚高，也能把漏掉的数据“捞”回来
            window_size = 5000
            count_sql = f"SELECT COUNT(*) FROM (SELECT id FROM {table_name} ORDER BY id DESC LIMIT {window_size}) as recent"
            select_sql = f"SELECT {columns_sql} FROM {table_name} ORDER BY id DESC LIMIT {window_size}"
            
            logger.info(f"🔍 强力同步模式：检查云端最近 {window_size} 条数据进行本地补齐...")

            # 3. 统计待拉取数量
            cloud_cur.execute(count_sql)
            total_to_check = cloud_cur.fetchone()[0]
            
            if total_to_check == 0:
                logger.info("✅ 云端没有任何数据，跳过！")
                return
            
            logger.info(f"📥 准备从云端拉取 {total_to_check} 条数据进行增量对比...")

            # 4. 执行云端查询
            cloud_cur.execute(select_sql)
            
            # 构建本地插入语句 (依靠主键冲突自动过滤老数据)
            insert_sql = f"""
                INSERT INTO {table_name} ({columns_sql}) 
                VALUES ({placeholders})
                ON CONFLICT (id) DO NOTHING
            """
            
            # 5. 分批次处理
            success_count = 0
            skip_count = 0
            batch_size = 500
            
            while True:
                batch = cloud_cur.fetchmany(batch_size)
                if not batch:
                    break
                
                for row in batch:
                    try:
                        local_cur.execute(insert_sql, row)
                        if local_cur.rowcount > 0:
                            success_count += 1
                        else:
                            skip_count += 1
                    except psycopg2.IntegrityError:
                        local_conn.rollback()
                        skip_count += 1
                    except Exception as e:
                        local_conn.rollback()
                        skip_count += 1
                
                # 提交批次
                local_conn.commit()

            # 6. 汇报战果
            logger.info(f"🏁 [{table_name}] 同步完成!")
            logger.info(f"   -> 精准补齐新记录: {success_count} 条")
            logger.info(f"   -> 识别并跳过已存在记录: {skip_count} 条")
            logger.info(f"   -> 耗时: {(time.time() - start_time):.2f} 秒")

        except Exception as e:
            logger.error(f"❌ 同步表 {table_name} 时发生严重错误: {e}")
            local_conn.rollback()

    def run_all(self):
        """执行所有表的同步流"""
        logger.info("🌟 启动多表批量安全同步协议 (滑动窗口补齐版)...")
        cloud_conn = cloud_cur = local_conn = local_cur = None
        
        try:
            cloud_conn, cloud_cur, local_conn, local_cur = self.connect_databases()
            logger.info("🔗 数据库双向连接建立成功！")
            
            # 依次轮询目标表单
            for table in self.target_tables:
                self.sync_single_table(table, cloud_conn, cloud_cur, local_conn, local_cur)
                
            logger.info("\n🎉 所有目标表格同步协议执行完毕！")
            
        except Exception as e:
            logger.error(f"💥 核心同步调度崩溃: {e}")
        finally:
            # 释放连接池
            for cur, conn in [(cloud_cur, cloud_conn), (local_cur, local_conn)]:
                if cur: cur.close()
                if conn: conn.close()
            logger.info("🔒 数据库连接已安全关闭。")

if __name__ == '__main__':
    syncer = MultiTableSyncer()
    syncer.run_all()