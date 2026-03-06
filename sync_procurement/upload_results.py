# D:\code\project\scripts\sync_procurement\upload_results.py
import os
import sys
import psycopg2
from psycopg2.extras import DictCursor, execute_values
import logging
import time
import io
import json

# 【关键修复】强制标准输出使用 UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [UPLOAD] - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Uploader")

class ResultUploader:
    def __init__(self):
        # [核心修改] 将单个云端配置改为配置列表，支持多服务器同步
        self.cloud_configs = [
            {
                'name': '服务器A (76.252)',
                'host': '121.41.76.252',
                'port': '5432',
                'database': 'austinchen587_db',
                'user': 'austinchen587',
                'password': 'austinchen587',
                'connect_timeout': 10
            },
            {
                'name': '服务器B (128.53)',
                'host': '121.41.128.53',
                'port': '5432',
                'database': 'austinchen587_db',
                'user': 'austinchen587',
                'password': 'austinchen587',
                'connect_timeout': 10
            }
        ]
        
        # 本地数据库配置 (源)
        self.local_config = {
            'host': 'localhost',
            'port': '5432',
            'database': 'austinchen587_db',
            'user': 'austinchen587',
            'password': 'austinchen587',
        }

    def get_connection(self, config, name="DB"):
        """获取数据库连接并测试"""
        try:
            conn = psycopg2.connect(
                host=config['host'],
                port=config['port'],
                database=config['database'],
                user=config['user'],
                password=config['password'],
                connect_timeout=config.get('connect_timeout', 10)
            )
            logger.info(f"✅ {name} 连接成功 ({config['host']})")
            return conn
        except Exception as e:
            logger.error(f"❌ {name} 连接失败: {e}")
            raise

    def prepare_data_for_upload(self, row, columns):
        """将 Python 的 dict 和 list 转换为 JSON 字符串"""
        values = []
        for col in columns:
            val = row[col]
            if isinstance(val, (dict, list)):
                values.append(json.dumps(val, ensure_ascii=False))
            else:
                values.append(val)
        return tuple(values)

    # [核心修改] 接收特定的 cloud_config 作为参数
    # [核心修改] 接收特定的 cloud_config 作为参数，加入增量上传逻辑
    def upload_table(self, cloud_config, table_name, unique_key):
        """修复版表同步函数 (加入时间窗口极致省流模式)"""
        logger.info(f"\n🚀 [开始同步表] {table_name} -> {cloud_config['name']}")
        local_conn = None
        cloud_conn = None
        
        try:
            # 1. 建立连接
            local_conn = self.get_connection(self.local_config, "本地")
            cloud_conn = self.get_connection(cloud_config, f"云端 ({cloud_config['name']})")
            
            local_cur = local_conn.cursor(cursor_factory=DictCursor)
            cloud_cur = cloud_conn.cursor()

            # 2. 【核心省流优化】探测可用字段，仅读取近期数据
            local_cur.execute(f"SELECT * FROM {table_name} LIMIT 0")
            columns = [desc[0] for desc in local_cur.description]
            
            time_condition = ""
            if 'updated_at' in columns:
                time_condition = "WHERE updated_at >= NOW() - INTERVAL '3 days'"
                logger.info(f"  - 💰 [省流模式] 仅读取近 3 天内变动的数据...")
            elif 'created_at' in columns:
                time_condition = "WHERE created_at >= NOW() - INTERVAL '3 days'"
                logger.info(f"  - 💰 [省流模式] 仅读取近 3 天内新增的数据...")
            
            # 读取增量数据
            local_cur.execute(f"SELECT * FROM {table_name} {time_condition}")
            rows = local_cur.fetchall()
            
            total_rows = len(rows)
            if total_rows == 0:
                logger.info("  - ✅ 本地近期无数据变动，跳过上传，节省 IO")
                return
            else:
                logger.info(f"  - 📊 准备上传 {total_rows} 条增量记录...")

            # 3. 动态构建 SQL
            columns_str = ', '.join(columns)
            
            # 针对 brand 表，剔除人工可修改的字段，防止本地旧数据覆盖云端人工修改
            exclude_update = [unique_key, 'created_at']
            if table_name == 'procurement_commodity_brand':
                exclude_update.extend(['key_word', 'search_platform'])
                
            update_assignments = [f"{col} = EXCLUDED.{col}" for col in columns if col not in exclude_update]
            update_stmt = ', '.join(update_assignments)
            
            insert_sql = f"""
                INSERT INTO {table_name} ({columns_str}) 
                VALUES %s
                ON CONFLICT ({unique_key}) 
                DO UPDATE SET {update_stmt};
            """

            # 4. 转换数据格式
            data_values = [self.prepare_data_for_upload(row, columns) for row in rows]
            
            # 5. 执行批量上传
            start_time = time.time()
            execute_values(cloud_cur, insert_sql, data_values, page_size=100)
            cloud_conn.commit()
            
            duration = time.time() - start_time
            logger.info(f"✅ {table_name} -> {cloud_config['name']} 同步完成！")
            logger.info(f"  - 耗时: {duration:.2f}秒 (增量推送 {total_rows} 条)")

            # 6. 验证云端数量
            try:
                cloud_cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                cloud_count = cloud_cur.fetchone()[0]
                logger.info(f"  - {cloud_config['name']} 当前总记录数: {cloud_count}")
            except Exception as e:
                pass

        except Exception as e:
            logger.error(f"❌ 同步 {table_name} 到 {cloud_config['name']} 发生严重错误: {e}")
            if cloud_conn: cloud_conn.rollback()
        finally:
            if local_conn: local_conn.close()
            if cloud_conn: cloud_conn.close()

    def run(self):
        print("=" * 60)
        print("☁️  启动结果数据回传 (Local -> Multiple Clouds) - 修复Json版")
        print("=" * 60)
        
        try:
            # [核心修改] 循环遍历所有配置的目标服务器
            for cloud_config in self.cloud_configs:
                print(f"\n{'='*20} 正在处理 {cloud_config['name']} {'='*20}")
                
                # 1. 同步 Step 1 的分类结果
                self.upload_table(cloud_config, 'procurement_emall_category', 'record_id')
                
                # 2. 同步 Step 2 的商品解析中间结果
                self.upload_table(cloud_config, 'procurement_commodity_category', 'id')
                
                # 3. 同步 Step 3 的品牌/平台最终结果
                self.upload_table(cloud_config, 'procurement_commodity_brand', 'id')
            
            print("\n🎉 所有服务器回传任务执行完毕")
            
        except KeyboardInterrupt:
            print("\n⚠️ 用户中断上传")
        except Exception as e:
            print(f"\n❌ 发生未知错误: {e}")

if __name__ == '__main__':
    uploader = ResultUploader()
    uploader.run()