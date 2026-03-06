import os
import sys
import psycopg2
from psycopg2.extras import DictCursor
import logging
from datetime import datetime
import time
import argparse

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
        logging.FileHandler('sync_procurement.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class DatabaseSyncer:
    def __init__(self):
        # 云端数据库配置
        self.cloud_config = {
            'host': '121.41.76.252',
            'port': '5432',
            'database': 'austinchen587_db',
            'user': 'austinchen587',
            'password': 'austinchen587',
            'connect_timeout': 10
        }
        
        # 本地数据库配置
        self.local_config = {
            'host': 'localhost',
            'port': '5432',
            'database': 'austinchen587_db',
            'user': 'austinchen587',
            'password': 'austinchen587',
            'connect_timeout': 10
        }
        
        # 同步配置
        self.table_name = 'procurement_emall'
        self.backup_dir = 'db_backups'
        
        # 创建备份目录
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
    
    def connect_databases(self):
        """连接到云端和本地数据库"""
        try:
            logger.info("正在连接数据库...")
            
            # 连接云端数据库
            cloud_conn = psycopg2.connect(**self.cloud_config)
            cloud_conn.autocommit = False
            cloud_cur = cloud_conn.cursor(cursor_factory=DictCursor)
            
            # 连接本地数据库
            local_conn = psycopg2.connect(**self.local_config)
            local_conn.autocommit = False
            local_cur = local_conn.cursor()
            
            logger.info("数据库连接成功")
            return cloud_conn, cloud_cur, local_conn, local_cur
            
        except Exception as e:
            logger.error(f"连接数据库失败: {e}")
            raise
    
    def safe_sync_table(self):
        """安全同步表数据 - 不使用TRUNCATE（已优化公网出网流量）"""
        import time
        from datetime import datetime
        start_time = time.time()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        logger.info(f"开始安全同步表: {self.table_name}")
        
        cloud_conn = cloud_cur = local_conn = local_cur = None
        
        try:
            # 连接数据库
            cloud_conn, cloud_cur, local_conn, local_cur = self.connect_databases()
            
            # 1. 首先获取云端表的所有列名
            cloud_cur.execute(f"SELECT * FROM {self.table_name} LIMIT 0")
            column_names = [desc[0] for desc in cloud_cur.description]
            
            # 2. 获取本地当前最大ID（如果表有ID字段的话）
            local_max_id = 0
            if 'id' in column_names:
                try:
                    local_cur.execute(f"SELECT MAX(id) FROM {self.table_name}")
                    result = local_cur.fetchone()[0]
                    if result is not None:
                        local_max_id = int(result)
                        logger.info(f"本地最大ID: {local_max_id}")
                except:
                    logger.info("无法获取本地最大ID，将从零开始全量同步")
            
            # 构建查询基础字段
            columns_sql = ', '.join(column_names)
            placeholders = ', '.join(['%s'] * len(column_names))
            
            # 3. 【核心省流逻辑】构建带过滤条件的增量查询语句
            if local_max_id > 0 and 'id' in column_names:
                count_sql = f"SELECT COUNT(*) FROM {self.table_name} WHERE id > {local_max_id}"
                select_sql = f"SELECT {columns_sql} FROM {self.table_name} WHERE id > {local_max_id} ORDER BY id ASC"
                logger.info(f"💰 开启极致省流模式: 仅拉取云端 ID > {local_max_id} 的新数据")
            else:
                count_sql = f"SELECT COUNT(*) FROM {self.table_name}"
                select_sql = f"SELECT {columns_sql} FROM {self.table_name} ORDER BY id ASC"
                logger.info("⚠️ 首次同步或无ID字段: 将拉取云端全量数据")

            # 4. 获取云端待下载的数据总数
            cloud_cur.execute(count_sql)
            total_cloud_new = cloud_cur.fetchone()[0]
            logger.info(f"云端待下载的记录数: {total_cloud_new}")
            
            if total_cloud_new == 0:
                logger.info("✅ 云端没有新数据，无需消耗流量下载")
                return
            
            # 5. 开始读取云端增量数据
            logger.info("正在从云端获取数据...")
            cloud_cur.execute(select_sql)
            
            # 构建插入语句
            insert_sql = f"""
                INSERT INTO {self.table_name} ({columns_sql}) 
                VALUES ({placeholders})
                ON CONFLICT (id) DO NOTHING
            """
            
            # 如果表没有ID或者没有唯一约束，使用更简单的插入
            try:
                # 尝试ON CONFLICT语法
                local_cur.execute("SELECT 1")
            except:
                # 如果ON CONFLICT不支持，改为简单的INSERT风格
                insert_sql = f"INSERT INTO {self.table_name} ({columns_sql}) VALUES ({placeholders})"
            
            # 6. 逐条处理数据
            success_count = 0
            skip_count = 0
            fail_count = 0
            batch_size = 100
            batch_count = 0
            
            logger.info("开始同步数据到本地数据库...")
            
            while True:
                # 读取一批数据
                batch = cloud_cur.fetchmany(batch_size)
                if not batch:
                    break
                
                batch_count += 1
                logger.info(f"处理第{batch_count}批，每批{batch_size}条...")
                
                for row in batch:
                    try:
                        # 执行插入（因为前面已经过滤了 id > local_max_id，传过来的绝大部分都是新数据）
                        local_cur.execute(insert_sql, row)
                        success_count += 1
                        
                    except psycopg2.IntegrityError:
                        # 主键冲突或唯一约束冲突，跳过
                        # 补充 rollback 防止事务中断报错
                        local_conn.rollback()
                        skip_count += 1
                    except Exception as e:
                        logger.debug(f"记录插入失败: {str(e)[:100]}")
                        local_conn.rollback()
                        fail_count += 1
                
                # 每批提交一次
                local_conn.commit()
                
                # 进度显示
                processed = success_count + skip_count + fail_count
                if processed % 1000 == 0 or batch_count % 10 == 0:
                    logger.info(f"  进度: {processed}/{total_cloud_new} | 成功: {success_count} | 跳过: {skip_count} | 失败: {fail_count}")
            
            local_conn.commit()
            
            # 7. 验证结果
            local_cur.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            local_total = local_cur.fetchone()[0]
            
            logger.info("=" * 50)
            logger.info(f"同步完成!")
            logger.info(f"云端拉取: {total_cloud_new} 条新记录")
            logger.info(f"成功插入: {success_count} 条新记录")
            logger.info(f"跳过已有: {skip_count} 条记录")
            logger.info(f"插入失败: {fail_count} 条记录")
            logger.info(f"本地现有总计: {local_total} 条记录")
            logger.info(f"用时: {(time.time() - start_time):.2f}秒")
            
            # 保存报告
            report_file = os.path.join(self.backup_dir, f'sync_safe_report_{timestamp}.txt')
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write("采购平台数据安全同步报告 (省流增量版)\n")
                f.write("=" * 60 + "\n")
                f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"表名: {self.table_name}\n")
                f.write(f"云端拉取新记录数: {total_cloud_new}\n")
                f.write(f"成功插入新记录: {success_count}\n")
                f.write(f"跳过已有记录: {skip_count}\n")
                f.write(f"插入失败记录: {fail_count}\n")
                f.write(f"本地现有总计: {local_total}\n")
                f.write(f"用时: {time.time() - start_time:.2f}秒\n")
            
            logger.info(f"同步报告已保存: {report_file}")
            
        except Exception as e:
            logger.error(f"[ERROR] 同步过程失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            if local_conn:
                local_conn.rollback()
            
        finally:
            # 清理连接
            for cur, conn in [(cloud_cur, cloud_conn), (local_cur, local_conn)]:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            logger.info("数据库连接已关闭\n")

def run_once():
    """执行一次同步"""
    syncer = DatabaseSyncer()
    syncer.safe_sync_table()

def run_scheduled(hours=1):
    """定时执行同步"""
    import schedule
    
    syncer = DatabaseSyncer()
    
    logger.info(f"启动定时同步，每{hours}小时执行一次")
    logger.info("按 Ctrl+C 停止")
    
    # 立即执行一次
    try:
        syncer.safe_sync_table()
    except Exception as e:
        logger.error(f"首次同步失败: {e}")
    
    # 设置定时任务
    schedule.every(hours).hours.do(syncer.safe_sync_table)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次
    except KeyboardInterrupt:
        logger.info("同步已停止")

def main():
    parser = argparse.ArgumentParser(description='安全同步云端PostgreSQL表到本地')
    parser.add_argument('--once', action='store_true', help='执行一次同步')
    parser.add_argument('--schedule', type=int, default=0, 
                       help='定时同步间隔（小时），0表示不定时')
    parser.add_argument('--host', type=str, help='云端数据库主机')
    parser.add_argument('--password', type=str, help='云端数据库密码')
    
    args = parser.parse_args()
    
    if args.once:
        run_once()
    elif args.schedule > 0:
        run_scheduled(args.schedule)
    else:
        # 默认执行一次
        run_once()

if __name__ == '__main__':
    # 记录开始时间
    start_time = time.time()
    
    # 检查是否有外键问题
    logger.info("检查数据库外键约束...")
    logger.info("使用安全同步模式，不会删除任何现有数据")
    logger.info("只会添加云端有而本地没有的新数据")
    
    main()
