# D:\code\project\scripts\20251227\20251227_version_1\db_connector.py
"""
数据库连接器（从您提供的 classify_procurement.py 复制修改）
"""

import psycopg2
from pathlib import Path

class DatabaseConnector:
    """数据库连接器"""
    
    def __init__(self, db_config=None):
        if db_config is None:
            # 从您的现有配置复制
            self.db_config = {
                "host": "localhost",
                "port": 5432,
                "database": "austinchen587_db",  # 请修改为您的数据库名
                "user": "austinchen587",         # 请修改为您的用户名
                "password": "austinchen587"  # 请修改为您的密码
            }
        else:
            self.db_config = db_config
    
    def get_connection(self):
        """获取数据库连接"""
        try:
            conn = psycopg2.connect(
                host=self.db_config["host"],
                port=self.db_config["port"],
                database=self.db_config["database"],
                user=self.db_config["user"],
                password=self.db_config["password"]
            )
            return conn
        except Exception as e:
            print(f" 数据库连接失败: {e}")
            return None
    
    def fetch_random_samples(self, sample_size=100):
        """
        从 procurement_emall 表随机获取样本
        
        Args:
            sample_size: 样本数量
        
        Returns:
            list: 样本列表，每个元素是字典
        """
        conn = self.get_connection()
        if conn is None:
            print("  无法连接数据库，返回空样本列表")
            return []
        
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        id, 
                        project_name,
                        COALESCE(commodity_names, ARRAY[]::text[]) as commodity_names,
                        created_at
                    FROM procurement_emall
                    WHERE project_name IS NOT NULL 
                      AND TRIM(project_name) != ''
                    ORDER BY RANDOM() 
                    LIMIT %s
                """, (sample_size,))
                
                rows = cur.fetchall()
                samples = []
                
                for row in rows:
                    samples.append({
                        'id': row[0],
                        'project_name': row[1],
                        'commodity_names': row[2],
                        'created_at': row[3]
                    })
                
                print(f" 成功获取 {len(samples)} 个随机样本")
                return samples
                
        except Exception as e:
            print(f" 查询数据库失败: {e}")
            return []
        finally:
            conn.close()
    
    def fetch_recent_records(self, hours=3):
        """
        获取最近 N 小时的新增记录
        
        Args:
            hours: 小时数
        
        Returns:
            list: 记录列表
        """
        conn = self.get_connection()
        if conn is None:
            return []
        
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        id, 
                        project_name,
                        COALESCE(commodity_names, ARRAY[]::text[]) as commodity_names,
                        created_at
                    FROM procurement_emall
                    WHERE created_at > NOW() - INTERVAL '%s hours'
                      AND project_name IS NOT NULL
                      AND TRIM(project_name) != ''
                    ORDER BY created_at DESC
                """, (hours,))
                
                rows = cur.fetchall()
                return [{'id': r[0], 'project_name': r[1], 
                         'commodity_names': r[2], 'created_at': r[3]} 
                        for r in rows]
                
        except Exception as e:
            print(f" 获取最近记录失败: {e}")
            return []
        finally:
            conn.close()
