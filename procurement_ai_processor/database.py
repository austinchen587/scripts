import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2 import pool
import logging
from typing import List, Dict
from config import DB_CONFIG

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.connection_pool = None
        self.initialize_pool()
    
    def initialize_pool(self):
        try:
            self.connection_pool = pool.SimpleConnectionPool(1, 10, **DB_CONFIG)
            logger.info("数据库连接池初始化成功")
        except Exception as e:
            logger.error(f"数据库连接池初始化失败: {e}")
            raise
    
    def get_connection(self):
        if self.connection_pool: return self.connection_pool.getconn()
        return None
    
    def return_connection(self, connection):
        if self.connection_pool and connection: self.connection_pool.putconn(connection)

    def execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params) if params else cursor.execute(query)
            results = cursor.fetchall()
            conn.commit()
            return results
        except Exception as e:
            logger.error(f"查询执行失败: {e}")
            if conn: conn.rollback()
            raise
        finally:
            if cursor: cursor.close()
            if conn: self.return_connection(conn)

    # --- [修改点 1] 升级为检查“ID+商品名”组合 ---
    def check_existing_items(self) -> set:
        """
        获取已存在的 (procurement_id, item_name) 集合
        用于精准过滤，防止同一订单下多个商品被误判为已处理
        """
        query = "SELECT procurement_id, item_name FROM procurement_commodity_brand"
        try:
            results = self.execute_query(query)
            # 返回元组集合: {(1001, '电脑'), (1001, '鼠标'), ...}
            return {(row['procurement_id'], row['item_name']) for row in results}
        except Exception as e:
            logger.error(f"检查已存在项目失败: {e}")
            return set()

    def get_source_data(self) -> List[Dict]:
        # SQL 保持不变，负责展开 JSON 数组
        query = """
        SELECT 
            pcc.procurement_id,
            pcc.project_number,
            pcc.project_name,
            pcc.procurement_type,
            pcc.commodity_category,
            COALESCE(item->>'单位', '') as unit,
            COALESCE(item->>'备注', '') as notes,
            TRIM(BOTH '''' FROM TRIM(BOTH '[]' FROM COALESCE(item->>'商品名称', ''))) as item_name,
            TRIM(BOTH '''' FROM TRIM(BOTH '[]' FROM COALESCE(item->>'建议品牌', ''))) as suggested_brand,
            TRIM(BOTH '''' FROM TRIM(BOTH '[]' FROM REGEXP_REPLACE(REGEXP_REPLACE(COALESCE(item->>'规格型号', ''),'核心参数要求:商品类目:[^;]*;?', '', 'g'),'次要参数要求:?', '', 'g'))) as specifications,
            
            -- [修复] 增加长度限制，防止超大脏数据撑爆 BIGINT
            CASE 
                WHEN item->>'采购数量' ~ '^[0-9]+$' AND length(item->>'采购数量') <= 18 
                THEN (item->>'采购数量')::BIGINT 
                ELSE NULL 
            END as quantity,
            
            pe.quote_start_time
        FROM procurement_commodity_category pcc
        INNER JOIN procurement_emall pe ON pcc.procurement_id = pe.id
        CROSS JOIN LATERAL jsonb_array_elements(pcc.items_data) as item
        WHERE jsonb_array_length(pcc.items_data) > 0
        ORDER BY pe.quote_start_time DESC NULLS LAST, pcc.procurement_id DESC
        """
        return self.execute_query(query)

    def batch_insert_brand_data(self, data_list: List[Dict]) -> int:
        if not data_list: return 0
        query = """
        INSERT INTO procurement_commodity_brand (
            procurement_id, project_number, project_name, 
            procurement_type, commodity_category, unit,
            notes, item_name, suggested_brand, 
            specifications, quantity, key_word, search_platform,
            created_at, updated_at
        ) VALUES %s
        """
        values = [
            (
                item['procurement_id'], item['project_number'], item['project_name'],
                item['procurement_type'], item['commodity_category'], item['unit'],
                item['notes'], item['item_name'], item['suggested_brand'],
                item['specifications'], item['quantity'], 
                item['key_word'], 
                item.get('search_platform', ''),
                'NOW()', 'NOW()'
            ) for item in data_list
        ]
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            execute_values(cursor, query, values, page_size=100)
            conn.commit()
            return len(values)
        except Exception as e:
            logger.error(f"批量插入失败: {e}")
            if conn: conn.rollback()
            raise
        finally:
            if cursor: cursor.close()
            if conn: self.return_connection(conn)

    def close_all(self):
        if self.connection_pool: self.connection_pool.closeall()