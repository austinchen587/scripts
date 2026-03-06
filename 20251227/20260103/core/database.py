# database.py
import psycopg2
import logging
from config import DATABASE_CONFIG

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.config = DATABASE_CONFIG
        self.connection = None
    
    def connect(self):
        """连接数据库"""
        try:
            self.connection = psycopg2.connect(**self.config)
            logger.info("数据库连接成功")
            return True
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            return False
    
    def get_procurement_data(self, record_id):
        """根据record_id获取采购数据"""
        query = """
        SELECT 
            commodity_names,
            parameter_requirements,
            purchase_quantities,
            control_amounts,
            suggested_brands,
            business_items,
            business_requirements
        FROM procurement_emall 
        WHERE id = %s
        """
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (record_id,))
                result = cursor.fetchone()
                
                if result:
                    data = {
                        'commodity_names': result[0] or [],
                        'parameter_requirements': result[1] or [],
                        'purchase_quantities': result[2] or [],
                        'control_amounts': result[3] or [],
                        'suggested_brands': result[4] or [],
                        'business_items': result[5] or [],
                        'business_requirements': result[6] or []
                    }
                    logger.info(f"获取到采购数据 record_id={record_id}")
                    return data
                else:
                    logger.warning(f"未找到采购数据 record_id={record_id}")
                    return None
                    
        except Exception as e:
            logger.error(f"查询采购数据失败 record_id={record_id}: {e}")
            return None
    
    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            logger.info("数据库连接已关闭")
