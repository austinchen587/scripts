# main_pipeline/database_writer.py
import psycopg2
import json
from datetime import datetime

class DatabaseWriter:
    def __init__(self):
        self.conn = None
        self.connect()
    
    def connect(self):
        """连接数据库"""
        try:
            # 移除 charset 参数，psycopg2 不支持
            self.conn = psycopg2.connect(
                host="localhost",
                database="austinchen587_db",
                user="austinchen587",
                password="austinchen587",
                port=5432
            )
            print(f"[DB] ✅ 数据库连接成功")
            return True
        except Exception as e:
            print(f"[DB] ❌ 数据库连接失败: {e}")
            return False
    
    def is_connected(self):
        """检查连接状态"""
        return self.conn is not None and not self.conn.closed
    
    def check_record_exists(self, procurement_id):
        """检查记录是否存在"""
        if not self.is_connected():
            return False
        
        try:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM procurement_commodity_category WHERE procurement_id = %s",
                (procurement_id,)
            )
            count = cur.fetchone()[0]
            cur.close()
            return count > 0
        except Exception as e:
            print(f"[DB] ⚠️ 检查记录存在失败: {e}")
            return False
    
    def insert_procurement_record(self, record: dict):
        """
        插入新记录到 procurement_commodity_category
        每个项目一条记录，所有商品存在 items_data 字段中
        """
        if not self.is_connected():
            return False
        
        try:
            cur = self.conn.cursor()
            
            # 准备数据
            procurement_id = record.get("procurement_id")
            project_number = record.get("project_number", "")
            project_name = record.get("project_name", "")
            procurement_type = record.get("procurement_type", "goods")
            commodity_category = record.get("commodity_category", "其他")
            items_data = record.get("items_data", [])
            raw_llm_output = record.get("raw_llm_output", "")
            processing_log = record.get("processing_log", {})
            data_source = record.get("data_source", "llm")
            created_at = record.get("created_at", datetime.now())
            
            # 确保items_data是JSON字符串
            if isinstance(items_data, (list, dict)):
                items_data_json = json.dumps(items_data, ensure_ascii=False)
            else:
                items_data_json = json.dumps([], ensure_ascii=False)
            
            # 确保processing_log是JSON字符串
            if isinstance(processing_log, dict):
                processing_log_json = json.dumps(processing_log, ensure_ascii=False)
            else:
                processing_log_json = json.dumps({}, ensure_ascii=False)
            
            # 插入记录 - 每个项目一条记录
            query = """
            INSERT INTO procurement_commodity_category 
            (procurement_id, project_number, project_name, procurement_type, 
             commodity_category, items_data, raw_llm_output, processing_log, 
             data_source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s)
            ON CONFLICT (procurement_id) DO UPDATE
            SET project_number = EXCLUDED.project_number,
                project_name = EXCLUDED.project_name,
                procurement_type = EXCLUDED.procurement_type,
                commodity_category = EXCLUDED.commodity_category,
                items_data = EXCLUDED.items_data,
                raw_llm_output = EXCLUDED.raw_llm_output,
                processing_log = EXCLUDED.processing_log,
                data_source = EXCLUDED.data_source,
                updated_at = CURRENT_TIMESTAMP
            """
            
            cur.execute(query, (
                procurement_id,
                project_number,
                project_name,
                procurement_type,
                commodity_category,
                items_data_json,
                raw_llm_output[:2000],  # 限制长度
                processing_log_json,
                data_source,
                created_at
            ))
            
            self.conn.commit()
            cur.close()
            print(f"[DB] ✅ 已成功插入/更新记录: {project_number}")
            return True
            
        except Exception as e:
            print(f"[DB] ❌ 插入记录失败: {e}")
            if self.conn:
                self.conn.rollback()
            return False
    
    def close(self):
        """关闭连接"""
        if self.conn and not self.conn.closed:
            self.conn.close()
            print(f"[DB] 🔒 数据库连接已关闭")
